# Audit note — T310 · M27 Security Review + OWASP + Launch Gate (2026-08-03)

- **By:** Claude Code (Opus 5)
- **Status:** Review complete, fixes landed, **`IN_REVIEW` not `DONE`** — the
  launch gate has 8 blocking items and one critical fix is unverified.
- **Full report:** [docs/13-SECURITY-REVIEW-OWASP.md](../13-SECURITY-REVIEW-OWASP.md)
- **Verdict:** CONDITIONAL GO

---

## What was found

Two critical findings. Both were **fail-open** — the system worked normally
while providing no protection, which is why neither had surfaced.

### C-1 — Publicly known JWT signing secret

`apps/api-gateway/src/config.ts` and `services/auth-service/app/config.py` both
defaulted `JWT_SECRET` to the same literal committed in this repository. I
grepped every service and the gateway for any production-environment check and
found **zero** — several config comments said "every non-local environment MUST
override this", enforced by nothing.

Anyone who can read the repo could sign a token with any `tid` and `roles`. The
gateway verifies it, then injects the forged tenant id downstream as a
**trusted** `x-tenant-id` header, which services trust implicitly because
`check_conventions.py` forbids them from decoding tokens. Full cross-tenant
read/write as an owner.

### C-2 — RLS silently bypassed

All 28 tenant tables use `ENABLE ROW LEVEL SECURITY`. **`ENABLE` does not apply
to the table owner — only `FORCE` does.** Migrations create the tables, so that
role owns them; the services' default `DATABASE_URL` is the same role.

The subtle part: T311 _did_ verify RLS working on live GCP Postgres — but as
`tradequote_app`, a role Agent 3 built by hand that **exists in no migration**.
Its only trace in the repo is a hardcoded default URL in the RLS test. So the
control works exactly where someone remembered to create it, and silently
vanishes in every environment provisioned from this repository.

It stayed hidden because `tests/integration/test_postgres_rls.py` `skipif`s
itself when Postgres is unreachable — the normal local state. The suite reported
green having never evaluated a policy.

---

## What I fixed

| Finding | Fix                                                                                                                                                                           |
| ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| C-1     | Fail-closed startup guards in gateway, auth-service, integration-service. **Throws**, not warns. Runs from `model_post_init` in Python so it can't be skipped at a call site. |
| C-2     | `infra/db/migrations/0015_rls_app_role.sql` — codifies the least-privilege non-owner role, same name as T311's manual one so that environment keeps working.                  |
| M-1     | Committed Fernet key (QuickBooks/Xero tokens at rest) now guarded.                                                                                                            |
| M-2     | Empty `MFA_ENCRYPTION_KEY` now guarded — TOTP seeds are the second factor.                                                                                                    |

**I deliberately did not add `FORCE ROW LEVEL SECURITY`,** despite it being the
textbook answer. Three `SECURITY DEFINER` functions rely on the owner exemption
as a tightly-scoped escape hatch, and `FORCE` would silently break all three:
the notification outbox relay (reintroducing the T205c "logs started, publishes
nothing" bug), public proposal view links, and public e-signature signing links.
Trading a fixable misconfiguration for three silent outages is a bad trade,
especially when I cannot test the result here. The fix is to stop _being_ the
owner, which is what the migration does.

---

## Gates

| Gate                                   | Result                                                       |
| -------------------------------------- | ------------------------------------------------------------ |
| `python -m pytest tests/security -q`   | **27 passed**                                                |
| `apps/api-gateway` · `pnpm vitest run` | **53 passed** (14 new security, 39 pre-existing still green) |
| `python -m pytest tests/infra -q`      | **51 passed**                                                |
| `python scripts/gen_infra.py --check`  | OK — 38 artifacts match the registry                         |
| `python scripts/check_conventions.py`  | OK                                                           |
| `pnpm typecheck` (gateway)             | clean                                                        |

---

## The part worth reading: my first security suite was worthless

I wrote 27 tests, they passed, and I nearly moved on. Mutation testing showed
**3 of 4 deliberate sabotages passed undetected**:

| Mutation                            | Why it slipped through                                                         |
| ----------------------------------- | ------------------------------------------------------------------------------ |
| Comment out the `x-tenant-id` strip | The assertion matched the text **inside the comment**                          |
| Rename/disable the production guard | `assertProductionSecrets` is a substring of `DISABLED_assertProductionSecrets` |
| Grant `BYPASSRLS` to the app role   | The safe string still appeared on a **different line** of the same file        |

Every one of those is a _critical_ protection, and the suite reported green with
it removed. The root cause was the same in all three: **the tests grepped source
text instead of exercising behaviour.**

The rewrite:

- Gateway protections are now tested by driving **real requests through a real
  server** against a fake upstream that echoes back what it actually received —
  cross-tenant spoofing, role escalation, `alg:none`, expired/wrong-secret
  tokens, and the guard wiring in `loadConfig` itself.
- Where a static check is unavoidable (SQL migrations), comments are stripped
  first and **every** matching statement is checked, not just "does the safe
  string appear somewhere".
- The SQL-injection detector has a **self-test** proving it still matches known
  attack patterns — which immediately caught a bug in my own regex (`\b` after
  an alternation ending in `\s` never matches, so `"SELECT * FROM ..."` slipped
  past).

All five mutations are now caught. Recording this because the first version
would have shipped looking green, and a security test that cannot fail is worse
than no test — it manufactures confidence.

---

## What is NOT verified

- **No live system was tested.** No running services, no database, no deployed
  environment.
- **C-2's fix is unproven** — migration `0015` has never been applied. Its
  riskiest side effect (breaking the `SECURITY DEFINER` escape hatches) is
  specifically called out for Antigravity to check.
- **No penetration test.** A checklist is provided for whoever runs one.
- **No container image has ever been built** (inherited from T309).
- **DAST not run** — HawkScan has no API key and needs a running target.
- **`apps/web` / `apps/mobile` not deeply reviewed** — no XSS/CSRF pass on the
  React surface.

---

## Handed to Antigravity

All Docker, deployment, and live-verification work →
[T309/T310 GCP handoff](T309-T310-GCP-deploy-antigravity-handoff.md).

Note the retarget: **T309 was authored against Fly.io; the instruction is now
GCP.** The handoff maps what carries over (all 12 Dockerfiles, the
`infra/services.yml` registry) versus what must be rewritten (`fly.toml` →
Cloud Run, Fly secrets → Secret Manager, Cloudflare WAF → Cloud Armor). I also
made the images `$PORT`-aware with `exec` so they run correctly on Cloud Run,
which injects `$PORT` and ignores `EXPOSE`.

## Recommended next steps

1. **Apply migration 0015 and verify RLS live** — the single highest-value
   remaining check, and the one only Antigravity can do.
2. Confirm the outbox relay and public signing links survive the role change.
3. Build all 12 images.
4. Provision real secrets; confirm services refuse to boot without them.
5. Resolve the CORS decision before launch (allowlist, never `*`).
6. External pen-test using the provided checklist.
7. **T310b** — security observability (auth-failure metrics, cross-tenant-attempt
   alerting). Right now a credential-stuffing run would be invisible.
