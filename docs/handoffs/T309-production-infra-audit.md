# Audit note — T309 · M24 Production infra + monitoring (2026-08-03)

- **By:** Claude Code (Opus 5)
- **Status:** Built; **awaiting CTO sign-off**. Recorded as `IN_REVIEW`, not `DONE` —
  see [What is NOT verified](#what-is-not-verified). Nothing here has been deployed.

---

## Starting state

`T309` was `NOT_STARTED`, and the repo contained **zero Dockerfiles**. Eleven
FastAPI services and a Node gateway existed, were tested, and were signed off —
and none of them could be deployed anywhere. There was no container definition,
no platform config, no edge config, and no monitoring.

## What was built

### A registry, not twelve copies of the same file

The obvious approach — hand-write 12 Dockerfiles and 12 `fly.toml`s — produces
36 files that immediately start drifting from each other and from the gateway's
port map. Instead, `infra/services.yml` is the **single source of truth**
(path, runtime, port, scaling, criticality), and `scripts/gen_infra.py`
generates all 38 artifacts from it.

`gen_infra --check` runs in CI and fails if any committed artifact no longer
matches the registry, so a hand-edited port can't silently desync the
containers, the deploy matrix, and the monitoring targets.

### Container images

Multi-stage; `uv`-based dependency layer separate from the project layer so app
edits don't invalidate the dependency download. Runtime images are non-root
(`USER app`, uid 10001), pin their base image (no `:latest`), carry a
`HEALTHCHECK` against `/health`, and bind uvicorn to `0.0.0.0` — binding
`127.0.0.1` inside a container is the classic "deployed but unreachable" bug.

The gateway's Dockerfile builds from the **repo root**, because it's a pnpm
workspace package whose lockfile and `packages/*` dependencies live above it.
That's documented in the file itself, since a build from the wrong context fails
confusingly.

### Fly.io

Per-unit health checks, rolling deploys, concurrency limits. Two deliberate
asymmetries:

- **`api-gateway` and `payment-service` run `min_machines = 2` and never
  auto-stop.** A cold-starting payment webhook handler drops provider callbacks
  that aren't reliably retried; a cold edge adds latency to every first request.
- **Only the gateway forces HTTPS.** Internal services are reached over Fly's
  private network on plain http — forcing TLS on them breaks gateway→service
  calls.

### Monitoring

Prometheus + Grafana + Loki + Promtail + Alertmanager + blackbox/postgres/redis
exporters, as a separate compose stack from the app's data stack (different
lifecycles — restarting Grafana shouldn't bounce Postgres).

**Availability is measured by blackbox-probing every unit's `/health`.** This
was a deliberate trade: the alternative (a `/metrics` endpoint everywhere) means
editing all 12 units, which is a much larger and riskier change. Probing gives
real up/down and latency signal on day one with **zero application code change**
— and the resulting gap is stated plainly rather than papered over (see below).

Ten alert rules, routed by severity: `page` → PagerDuty, `ticket` → Slack.
Every alert has a `for:` duration (no single-blip pages), a summary, and a
runbook link. Two of them exist specifically to catch _monitoring_ failure —
`NoHealthProbeTargets` fires when Prometheus has zero probe targets, which
would otherwise render every dashboard reassuringly green while watching
nothing.

### Cloudflare

Terraform for DNS, `ssl = strict`, HSTS, WAF, rate limits, and cache policy.
Three decisions worth flagging:

- **Payment webhooks bypass bot challenges.** Stripe and Square are bots by
  definition and cannot solve a JS challenge; without the exemption, real
  webhooks get dropped. Safe because `payment-service` verifies the provider
  HMAC itself and fails closed (per the T303 audit) — authenticity never
  depended on Cloudflare.
- **The API is never cached.** A cached tenant-scoped response served to a
  different tenant is a data breach.
- **No geo-blocking**, deliberately — contractors travel. Recorded so the
  absence reads as a decision, not an oversight.

### Deploy pipeline

`.github/workflows/deploy.yml`: triggers only on a **green** CI run, verifies
artifacts are in sync, deploys **only changed units**, requires manual approval
via the `production` environment, and smoke-tests `/health` after each deploy.
The gateway deploys **last**, in its own job, so the public edge never routes to
backends that haven't rolled yet. `fail-fast: false` — a half-cancelled rollout
is harder to diagnose than a clear list of what succeeded.

---

## Gates run

| Gate                                   | Result                                     |
| -------------------------------------- | ------------------------------------------ |
| `python -m pytest tests/infra -q`      | **51 passed**                              |
| `python scripts/gen_infra.py --check`  | **OK** — 38 artifacts match the registry   |
| `python scripts/check_conventions.py`  | **OK**                                     |
| `scripts/deploy_matrix.py` (all paths) | OK — correct split, exit 1 on unknown unit |
| Prettier on all files authored here    | Clean                                      |

### The test suite was mutation-tested

51 passing tests prove nothing until you check they can fail. Three deliberate
breakages:

| Mutation                             | Caught by                                                                                               |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| Registry port `8010` → `8099`        | **6 tests**, incl. gateway-port alignment, fly `internal_port`, Dockerfile `EXPOSE`/`CMD`, probe target |
| Removed `USER app` from a Dockerfile | 2 tests (`test_runs_as_non_root`, sync check)                                                           |
| Alert runbook anchor → nonexistent   | `test_runbook_links_resolve`                                                                            |

The port-drift case is the one that matters most: if the registry and the
gateway's `config.ts` disagree, the gateway proxies to a port nothing listens
on and every request 502s **while all 12 services report perfectly healthy**.
That failure is now impossible to commit.

### Bugs found by actually running things

- `deploy_matrix.py` crashed with `UnicodeEncodeError` on a Windows cp1252
  console (a `→` in output). Fixed to ASCII; `gen_infra.py` had the same issue.
- Prettier and the JSON generator disagreed on array formatting, which would
  have made `format:check` and `gen_infra --check` mutually unsatisfiable
  forever. Resolved by adding generated targets to `.prettierignore`.

---

## What is NOT verified

Stated explicitly rather than left for someone to discover in production:

- **No image has ever been built.** There is no Docker daemon in this
  environment (`docker ps` fails to connect; Docker Desktop was launched and
  polled for ~4 minutes without the daemon coming up). The Dockerfiles are
  _structurally_ validated — non-root, pinned bases, correct ports, healthcheck
  present, correct uvicorn target — but a real `docker build` may still surface
  a missing system library. **Build all 12 before the first production deploy.**
- **Nothing has been deployed.** No Fly app exists; the deploy workflow has
  never run.
- **Terraform was never `plan`ned** against a real Cloudflare zone.
- **No in-application observability.** No request rate, error rate, or
  per-endpoint latency — only external `/health` probing. `SENTRY_DSN` and
  `OTEL_EXPORTER_OTLP_ENDPOINT` exist in `.env.example` but nothing emits to
  them. Tracked as **T309b**; not silently assumed to work.
- **5 services have no `uv.lock`** (`analytics`, `auth`, `customer`, `esign`,
  `pricebook`), so their builds resolve at build time and aren't byte-reproducible.

## Pre-existing issue found (not caused here, not fixed here)

`pnpm format:check` was **already failing on committed code** before this task —
75 files, including `TASKS.md`, `docs/modules/*`, and five `services/*/README.md`.
Verified by running prettier against the committed (`git show HEAD:`) versions.
Every file authored in this task is prettier-clean; the pre-existing failures
were left alone rather than swept into an unrelated infra commit. Worth its own
cleanup task.

## Recommended next steps

1. `docker build` all 12 images locally — the single highest-value remaining check.
2. Commit `uv.lock` for the 5 services missing one.
3. `terraform plan` against the real zone.
4. Provision Fly apps + secrets per the runbook, then deploy to staging first.
5. **T309b** for real application observability.
