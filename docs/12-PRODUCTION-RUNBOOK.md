# 12 — Production Runbook (T309 / M24)

Operational guide for the TradeQuote AI platform: how it's deployed, how to
respond when an alert fires, and how to roll back.

Every alert in `infra/monitoring/prometheus/rules/` links to a section here.
`tests/infra` asserts those links resolve, so an alert can never point at a
heading that doesn't exist.

---

## Topology

| Layer              | Runs on                            | Public?                             |
| ------------------ | ---------------------------------- | ----------------------------------- |
| `apps/web`         | Vercel                             | ✅ `app.<domain>`                   |
| `apps/api-gateway` | Fly.io                             | ✅ `api.<domain>` (via Cloudflare)  |
| 11 domain services | Fly.io                             | ❌ private `.internal` network only |
| PostgreSQL / Redis | Managed (Fly Postgres or provider) | ❌                                  |
| Monitoring         | `infra/monitoring/` compose stack  | ❌ (SSO in production)              |

`infra/services.yml` is the **single source of truth** for the port map, scaling,
and criticality. Dockerfiles, `fly.toml`s, and Prometheus targets are generated
from it by `scripts/gen_infra.py`. Never hand-edit a generated file — CI's
`gen_infra --check` will reject it.

Ports: gateway `8000`, services `8001`–`8011`. The gateway's own
`src/config.ts` defaults must agree with the registry; `tests/infra` enforces it.

---

## First-time deploy

### 1. Provision Fly apps

```bash
fly auth login
# One app per unit. Names come from the registry: tradequote-<unit>.
python - <<'PY'
import yaml, subprocess
reg = yaml.safe_load(open("infra/services.yml"))
for u in reg["units"]:
    app = f"{reg['app_prefix']}-{u['name']}"
    subprocess.run(["fly", "apps", "create", app, "--org", reg["org"]], check=False)
PY
```

### 2. Set secrets

Secrets are **per app** and never live in git, `fly.toml`, or a build arg (a
build arg is baked into the image layer and readable by anyone who pulls it).

```bash
# Every service that touches the database:
fly secrets set DATABASE_URL="postgresql+psycopg://..." --app tradequote-auth-service

# Gateway — needs the JWT secret plus every downstream URL:
fly secrets set JWT_SECRET="..." --app tradequote-api-gateway
fly secrets set AUTH_SERVICE_URL="http://tradequote-auth-service.internal:8001" --app tradequote-api-gateway
# ...repeat per service; see infra/services.yml `gateway_env` for the names.
```

Provider keys go only to the service that owns them: Stripe/Square →
`payment-service`, SendGrid/Twilio → `notification-service`, Anthropic/OpenAI →
`ai-service`. See `.env.example` for the full list.

### 3. Database migrations

Run **before** deploying code that depends on them:

```bash
bash infra/db/run-migrations.sh
```

Migrations are expand-only by convention — add columns, don't drop them in the
same release as the code change, or a rollback lands on a schema that no longer
matches.

### 4. Deploy

```bash
# Whole platform, first time:
gh workflow run deploy.yml -f units=all
```

Afterwards deploys are automatic: merge to `main` → CI → `deploy.yml` →
manual approval on the `production` environment → rolling deploy of only the
changed units, gateway last.

### 5. Cloudflare

See `infra/cloudflare/README.md`. Both records must stay **proxied** (orange
cloud) or the WAF and rate limits are bypassed silently.

---

## Deploying

| What        | Command                                                              |
| ----------- | -------------------------------------------------------------------- |
| Everything  | `gh workflow run deploy.yml -f units=all`                            |
| One service | `gh workflow run deploy.yml -f units=payment-service`                |
| Several     | `gh workflow run deploy.yml -f units=quote-service,proposal-service` |
| Manually    | `cd services/<name> && fly deploy --app tradequote-<name>`           |

The workflow refuses to run if `gen_infra --check` fails or if the upstream CI
run was red.

---

## Rollback

Fly keeps previous releases. Rolling back is faster than forward-fixing and is
the correct first move during a customer-visible incident.

```bash
fly releases --app tradequote-<unit>              # find the last good version
fly deploy --image <previous-image-ref> --app tradequote-<unit>
```

**Order matters.** If the gateway and services were deployed together, roll the
gateway back **first** — an old gateway talking to new services is usually
survivable (additive API changes); a new gateway calling endpoints that no
longer exist is not.

**Migrations don't roll back with the image.** If the bad release included a
destructive migration, restore from the database snapshot instead — see
[Database unreachable](#database-unreachable).

---

## Alert response

### ServiceDown

One service has failed `/health` for 2 minutes. The gateway will 502 for routes
that depend on it; everything else keeps working.

1. Confirm scope — one unit or many?
   `curl -fsS https://api.<domain>/health` (is the edge itself up?)
2. `fly status --app tradequote-<unit>`
3. `fly logs --app tradequote-<unit>` — look for a crash loop or an unhandled
   exception at boot (a missing secret is the most common cause after a deploy).
4. Recent deploy? Roll back (above). No recent deploy? Suspect a dependency:
   check the database and Redis first.
5. `fly machine restart <id> --app tradequote-<unit>` as a last resort — it
   clears a wedged process but destroys the evidence, so grab logs first.

### CriticalServiceDown

Same as above, but the unit is the **public edge** or the **money path**, and it
pages immediately.

- **`api-gateway` down = full platform outage.** Every client is affected.
  Check Cloudflare status and the Fly app before anything else.
- **`payment-service` down = lost webhooks.** Stripe retries with backoff for
  up to ~3 days; Square's retry window is shorter. After recovery, **reconcile**:
  compare provider dashboards against local payment records for the outage
  window and replay anything missing. Do not assume the queue drained itself.

### AllServicesDown

Every unit is failing at once. This is almost never twelve simultaneous bugs.

Check, in this order:

1. **Is monitoring itself broken?** Load Grafana and hit one service directly.
   A dead blackbox-exporter looks exactly like a dead platform.
2. **Shared dependency** — database or Redis down takes everything with it.
3. **Fly region/platform incident** — check the Fly status page.
4. **Network/DNS** — did a Cloudflare or DNS change just land?

Do not start restarting individual services until you've ruled these out.

### HealthProbeSlow

`/health` is answering but taking over a second. It's designed to be
dependency-light, so this usually means the process is saturated rather than
that the check itself is slow.

1. `fly status --app tradequote-<unit>` — check memory and CPU.
2. Look for a memory-hungry workload: `proposal-service` (PDF rendering) and
   `ai-service` (model SDKs) are the usual suspects and are provisioned at 1GB.
3. Scale out (`fly scale count 2`) or up (`fly scale memory 1024`).
4. If `/health` itself started touching a database or a downstream service,
   **fix that** — a health check with dependencies turns one slow dependency
   into a platform-wide outage as Fly pulls healthy machines from rotation.

### CriticalServiceSlow

Degradation on the edge or the money path, at a tighter threshold (500ms).
Same triage as above, but act sooner: payment providers time out and may not
retry, so slowness here loses transactions outright rather than deferring them.

### TLSCertExpiringSoon

Cloudflare and Fly both auto-renew, so this firing means renewal is genuinely
stuck rather than merely pending.

1. Check the certificate: `fly certs list --app tradequote-api-gateway`
2. Verify DNS still validates — a record changed to grey-cloud, or a CNAME
   edited by hand, breaks validation.
3. Re-issue: `fly certs create <hostname> --app tradequote-api-gateway`
4. At <3 days this escalates to a page. An expired cert is a total outage for
   every client, including mobile.

### PrometheusTargetMissing

A scrape target is unreachable, so monitoring is partially blind. The platform
may be perfectly healthy — but you can no longer prove it.

1. Which job? Exporters (`postgres-exporter`, `redis-exporter`) fail when the
   app stack in `infra/docker/docker-compose.yml` isn't running — expected
   locally, not in production.
2. `docker compose -f infra/monitoring/docker-compose.monitoring.yml ps`
3. Treat a persistently missing target as an outage of your ability to detect
   outages, and fix it with that urgency.

### NoHealthProbeTargets

Prometheus has **zero** `/health` probe targets. Every availability panel will
read as healthy while nothing is being watched at all — the most dangerous
failure mode in the stack, which is why it pages.

1. Confirm the generated target files aren't empty:
   `cat infra/monitoring/prometheus/targets/services-local.json`
2. Regenerate: `python scripts/gen_infra.py`
3. Confirm the compose mount resolved — a missing bind-mount source becomes an
   empty directory in Docker rather than an error.
4. Reload Prometheus: `curl -X POST http://localhost:9090/-/reload`

### HighErrorRate

A service is returning >5% 5xx responses over a 5-minute window — a T309b
application-metrics alert, distinct from `ServiceDown`. `/health` can still be
green here: a process can answer its own liveness check while the actual
request traffic it serves is failing (a bad deploy, a downstream dependency
returning errors it doesn't retry, a data bug that 500s a specific endpoint).

1. Which endpoints? Check Grafana's request-rate/error-rate panel for the
   service, broken out by route — is it one handler or everything?
2. `fly logs --app tradequote-<unit>` for the actual exception, not just the
   status code.
3. Recent deploy to this service? Roll back first, investigate after.
4. If it's isolated to one downstream call (e.g. a service-to-service HTTP
   call per ADR-0003), check that dependency's own error rate/logs next.

### CriticalHighErrorRate

Same signal as `HighErrorRate`, but on the public edge or the money path, at a
tighter 2% threshold — pages instead of ticketing. Triage the same way, but
for `payment-service` specifically: a burst of 5xx on webhook routes can mean
provider callbacks are failing closed (see `CriticalServiceDown`'s
reconciliation note) even while the process itself stays up and `/health`
stays green.

### HighRequestLatencyP99

The 99th-percentile request latency for a service has been over 2 seconds for
10 minutes, aggregated across its real endpoints — not just `/health`
(`HealthProbeSlow` covers that separately and is usually the earlier signal
for the same root cause).

1. Same first checks as `HealthProbeSlow`: CPU/memory via `fly status`, and
   whether `proposal-service`/`ai-service`'s known-heavy workloads are involved.
2. Check Grafana's per-endpoint latency breakdown (from the same `/metrics`
   histogram) to find which route is slow, rather than assuming the whole
   service is uniformly degraded.
3. If it correlates with a downstream service-to-service call, the slowness
   may not be local — check that dependency's own latency next.

### NoAppMetricsTargets

Prometheus has **zero** `/metrics` scrape targets — the T309b equivalent of
`NoHealthProbeTargets`. Every error-rate/latency panel reads as empty (not
"healthy", just absent) while nothing is actually being measured.

1. Confirm the generated target files aren't empty:
   `cat infra/monitoring/prometheus/targets/app-metrics-local.json`
2. Regenerate: `python scripts/gen_infra.py`
3. Confirm the compose mount resolved (same failure mode as
   `NoHealthProbeTargets` — a missing bind-mount source becomes an empty
   directory in Docker, not an error).
4. Reload Prometheus: `curl -X POST http://localhost:9090/-/reload`

### TokenForgeryAttempt

**Treat as a possible key compromise until proven otherwise.**

The gateway is rejecting tokens whose **signature** or **algorithm** does not
verify (T310b). This is not the same class of event as the alerts above.
A missing or expired token is ordinary traffic; a token with a bad signature
cannot be produced by accident — the caller either has the wrong signing key
and is guessing at it, or is attempting `alg:none` / algorithm confusion.

This is the alert that catches the **C-1** scenario from
[13-SECURITY-REVIEW-OWASP.md](13-SECURITY-REVIEW-OWASP.md): someone minting a
token with the committed dev secret against production. Until T310b that
attempt was rejected silently and reported to nobody.

1. **Has `JWT_SECRET` leaked?** Check it is not the committed dev default in
   any environment (`assertProductionSecrets` refuses to boot on it, so a
   running gateway proves it isn't — but confirm the _value_ hasn't been
   copied into a CI log, a Slack message, or a `.env` in a repo).
2. Source IPs: query Loki for `event="security.auth_failure"` and
   `reason="invalid_signature"`. One IP is a scanner; many is a distributed
   attempt.
3. If a leak is even plausible, **rotate `JWT_SECRET`** — gateway and
   auth-service together, they must match. Every existing access token becomes
   invalid, so users re-authenticate; that is the correct trade.
4. Cross-check `CrossTenantAccessAttempt` — the same actor probing both is a
   deliberate, targeted attempt rather than background internet noise.

**Threshold note:** fires on any sustained rate above zero. Background internet
scanning does produce a trickle of these against any public endpoint; if the
baseline turns out to be persistently non-zero after a month of real traffic,
raise the floor rather than widening the `for:` — a slow forgery attempt is
still a forgery attempt.

### HighAuthFailureRate

More than 5 rejected requests per second at the gateway for 10 minutes, across
all reasons _except_ the forgery ones (those page separately, above).

1. **Break down by `reason` first.** This decides everything:
   - `expired_token` dominant, starting right after a deploy → a client bug
     (tokens not being refreshed), not an attack. Ticket the client team.
   - `missing_token` dominant on one route → a caller that lost its
     credentials, or a misconfigured integration.
   - Mixed and rising → look at source IPs next.
2. Loki: `event="security.auth_failure"`, group by `ip` and `route`.
3. Check whether the gateway's rate limiter is engaging (429s in
   `http_requests_total`). If not, and one IP dominates, consider a Cloudflare
   block for that source.

**Threshold note:** 5/s is a guess made with no production traffic to calibrate
against. Expect to move it after the first month.

### CredentialStuffingSuspected

Over half of all login attempts are failing, at more than 1/s, for 5 minutes.
This signal exists only in auth-service: the gateway never sees a login body,
so every one of these requests looks to it like a perfectly valid, public,
unauthenticated POST.

1. **Split `auth_login_failures_total` by `reason` — this is the whole triage:**
   - Mostly `unknown_user` → **credential stuffing**. A list of stolen
     addresses is being replayed against you; most don't have accounts here.
   - Mostly `bad_password` → **targeted brute force** against accounts that
     really exist. More serious: they know who your users are.
   - Mostly `inactive_user` → someone working a list of suspended accounts.
2. Get the attempted addresses from the tenant's own audit log:
   `GET /v1/auth/audit-log?action=auth.login.failed` (owner/admin only), or
   directly: `SELECT actor_email, count(*) FROM auth_audit_log WHERE action =
'auth.login.failed' AND created_at > now() - interval '1 hour' GROUP BY 1
ORDER BY 2 DESC;`
   Many distinct addresses = stuffing. One address, many rows = brute force.
3. Source IPs from the same rows (`ip_address`) → Cloudflare block if
   concentrated.
4. **Watch for the secondary failure:** PBKDF2 at 600k iterations makes every
   login attempt expensive _server-side_. A large enough stuffing run is also a
   CPU DoS on auth-service — check its latency and CPU, and be ready to scale
   it out. This vector is called out in the T310 review under A07 and has not
   been load-tested.
5. Notify affected tenants if any attempt succeeded (`auth.login.succeeded`
   rows from the same IPs).

### CrossTenantAccessAttempt

**Someone is probing tenant isolation.** A caller supplied `x-tenant-id`,
`x-user-id`, or `x-user-roles` contradicting its own verified token claims.

**First, the reassuring part:** the request was _not_ served with the spoofed
identity. `proxy.ts` strips all three headers and re-derives them from the
verified JWT before forwarding, and that behaviour is locked by
`apps/api-gateway/test/security.test.ts`. This alert reports an **attempt**,
not a breach. What was new in T310b is that anyone finds out about it.

This alert has **no benign cause** and fires on any occurrence — an exact echo
of the caller's _own_ identity is deliberately not counted, so a well-meaning
SDK cannot trigger it. Do not tune it down.

1. Loki: `event="security.cross_tenant_attempt"`. The line carries `supplied`
   (what they asked for), `verifiedTenantId` (who they actually are), `ip`,
   and `route`.
2. **Which header?** `x-user-roles` is privilege escalation _within_ a tenant;
   `x-tenant-id` is a cross-tenant reach. Both matter, differently.
3. **`authenticated="false"`** means the headers were injected on a _public_
   route (proposal view, signing link, payment webhook, OAuth callback) with no
   token at all — anonymous probing, and worth a Cloudflare block.
4. Identify the actor: `verifiedUserId` + `verifiedTenantId` name a real
   account. Is it a customer's own pen-test, a security researcher, or a
   compromised session? Contact the tenant before assuming malice.
5. If the same actor also triggered `TokenForgeryAttempt`, escalate — that
   combination is a deliberate, informed attack, not a scanner.

### AuditLogWriteFailures

auth-service is failing to write audit rows. Logins still work — the write is
swallowed on purpose so that a database problem cannot take down
authentication (the trade is argued in
`services/auth-service/app/application/audit.py`). The cost of that trade is
that privileged actions are currently happening **without being recorded**,
which is precisely the gap T310b closed. Treat this as a control that has
silently switched off.

1. Is the database healthy at all? If Postgres is degraded, this is a symptom,
   not the problem — fix that and this clears.
2. **Check the 0016 grants.** A write rejected by the append-only `REVOKE`
   looks identical to any other failure here:
   `SELECT grantee, privilege_type FROM information_schema.role_table_grants
WHERE table_name = 'auth_audit_log';`
   `tradequote_app` must have `SELECT` and `INSERT` and must **not** have
   `UPDATE` or `DELETE`. If `INSERT` is missing, a migration ordering problem
   revoked too much.
3. auth-service logs: the swallowed exception is logged with
   `logger.exception` at the point of failure — the traceback names the real
   cause (constraint violation, connection pool exhaustion, permission).
4. Rows lost during the outage are **not recoverable**. Note the window in the
   incident record; anyone auditing that period needs to know the log has a
   hole in it.

---

## Monitoring stack

```bash
pnpm monitor:up      # Grafana :3001 · Prometheus :9090 · Alertmanager :9093
pnpm monitor:down
pnpm monitor:logs
```

Alertmanager needs `PAGERDUTY_ROUTING_KEY` and `SLACK_WEBHOOK_URL` in the
environment to actually deliver. Without them the stack still boots and
evaluates rules — it just can't notify anyone, which is worth knowing before
you rely on it.

**Grafana is unauthenticated in the local compose stack.** Put it behind SSO
before exposing it anywhere shared.

---

## Known gaps

Recorded honestly rather than discovered later:

- **Application metrics/tracing/Sentry are wired but never verified against a
  real backend (T309b, done 2026-08-03).** All 12 units now expose `/metrics`,
  propagate a `traceparent` when `OTEL_EXPORTER_OTLP_ENDPOINT` is set, and
  initialize Sentry when `SENTRY_DSN` is set — see
  `app/infrastructure/observability.py` (Python) and
  `apps/api-gateway/src/plugins/observability.ts` (gateway). There is no live
  Sentry project, OTel collector, or running Prometheus in this environment,
  so the wiring is proven correct (unit-tested init paths, a real W3C
  traceparent header on the wire between gateway and service) but never
  proven to actually land in a dashboard. Verify end-to-end before relying on
  an alert to page.
- **Image builds are unverified.** The Dockerfiles have never been built —
  there is no Docker daemon in the environment where they were authored. They
  are structurally validated by `tests/infra` (non-root, pinned bases, correct
  ports, healthchecks) but the first real `docker build` may still surface
  missing system libraries. Build all 12 before the first production deploy.
- **Terraform is unapplied.** The Cloudflare config has never been `plan`ned
  against a real zone.
- **Local Terraform state.** One operator at a time until the S3 backend in
  `infra/cloudflare/main.tf` is enabled.
- **5 services have no `uv.lock`** (`analytics`, `auth`, `customer`, `esign`,
  `pricebook`), so their builds resolve dependencies at build time and are not
  byte-reproducible. Commit locks before relying on rebuild determinism.
