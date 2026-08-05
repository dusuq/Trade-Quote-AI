# M27 — Security observability (T310b)

> **Status:** implemented 2026-08-04 · **Owner:** Agent 1 (CTO) · **Depends on:** T310, T309b
> **Closes:** OWASP **A09 — Logging & Monitoring Failures**, from the
> [T310 security review](../13-SECURITY-REVIEW-OWASP.md).

---

## The problem this solves

T310 established that the platform's authorization boundary is **correct**. The
gateway strips every client-supplied identity header and re-derives it from
verified JWT claims; RLS scopes every query to one tenant; the dev secret fails
closed in production.

All of that was **silent**.

A caller could iterate every tenant id in the platform via `x-tenant-id`, be
correctly refused ten thousand times, and leave no trace in any metric, log, or
table. Someone could replay a stolen credential list against `/v1/auth/login`
all night and the only visible effect would be a slight bump in request rate —
`http_requests_total` counts a failed login and a successful one identically.
Someone could forge tokens with the committed dev secret against production and
the gateway would reject each one without telling anybody.

> **A defence that is working and unobservable is indistinguishable from a
> defence that has been removed.** That is the whole of A09.

T309 answers "is it up". T309b answers "is the traffic healthy". Neither of
them moves during any of the scenarios above. M27 adds the third question:
**"is someone attacking it"**.

---

## What was built

### 1. Auth-failure metrics — the gateway

`apps/api-gateway/src/plugins/security-metrics.ts`

```
auth_failures_total{reason, route}
```

`reason` comes from a closed set in `src/auth.ts` (`AuthFailureReason`). The
split that matters:

| Reason                                   | Meaning                                                      |
| ---------------------------------------- | ------------------------------------------------------------ |
| `missing_token`, `expired_token`         | Ordinary traffic — a logged-out tab, a stale mobile session. |
| `malformed_token`, `not_yet_valid_token` | Broken client, usually.                                      |
| **`invalid_signature`**                  | **Nobody produces this by accident.** Wrong signing key.     |
| **`invalid_algorithm`**                  | **`alg:none` / algorithm confusion.** A forgery attempt.     |

The last two page (`TokenForgeryAttempt`); the rest ticket at volume
(`HighAuthFailureRate`). Collapsing them into one "invalid" bucket — the
obvious simplification — is exactly what would have made the **C-1** scenario
from the T310 review (someone using the committed dev secret against
production) undetectable. They stay separate deliberately.

`route` is the Fastify **route pattern**, never the concrete URL. These
counters are driven by unauthenticated traffic, so a label carrying an object
id would be a remote "allocate unbounded Prometheus series" primitive.

### 2. Cross-tenant-attempt metrics — the gateway

```
cross_tenant_attempts_total{header, route, authenticated}
```

Incremented when a client supplies `x-tenant-id`, `x-user-id`, or
`x-user-roles` that **contradicts** its verified claims — or supplies any of
them on a public route, where no claims exist at all (`authenticated="false"`,
anonymous probing).

Two design decisions worth stating:

- **An exact echo of the caller's own identity is _not_ counted.** An
  over-eager SDK sending back its own tenant id is not an attack; counting it
  would bury the real signal. Roles compare as a **set**, so the same roles in
  a different order is also not counted.
- **The observation must happen _before_ the strip.** `proxy.ts` deletes those
  headers; after the delete there is nothing left to observe. That statement
  ordering is pinned by `tests/security/test_security_invariants.py`, because
  no test of the end state can see it.

Because there is no benign cause, `CrossTenantAccessAttempt` pages on **any**
occurrence. This is not a threshold awaiting calibration.

### 3. Credential-failure metrics — auth-service

`services/auth-service/app/infrastructure/security_metrics.py`

```
auth_login_attempts_total{result}
auth_login_failures_total{reason}
```

The gateway **cannot** produce this signal: `/v1/auth/login` is on its public
allowlist and it never inspects a request body, so every login attempt —
successful, mistyped, or the 40,000th entry in a stolen credential list — looks
identical to it.

The `reason` split is the triage:

- mostly `unknown_user` → **credential stuffing** (many addresses, few real)
- mostly `bad_password` → **targeted brute force** (they know your users)

That distinction never reaches the caller. `/v1/auth/login` answers a flat
`invalid credentials` regardless, or it becomes an account-enumeration oracle —
pinned by a test.

### 4. Privileged-action audit log — auth-service

`services/auth-service/app/application/audit.py` · migration
`infra/db/migrations/0016_security_audit.sql`

`auth_audit_log` has existed since migration **0002** and **nothing had ever
written a row to it** — a control present on the schema diagram and absent in
reality, which is worse than no table at all, because it reads as done.

0016 makes it fit for purpose:

- `outcome`, `target_type`/`target_id`, `request_id` — turns an auth-only log
  into a general privileged-action log. `request_id` ties a row back to the
  gateway log line for the same request (`proxy.ts` sets `x-request-id`).
- `actor_email` — a failed login has no `actor_id` by definition. Without the
  attempted address there is no way to tell one account hit 10,000 times from
  10,000 accounts hit once, and that is the entire investigation.
- **Append-only for `tradequote_app`**: `REVOKE UPDATE, DELETE, TRUNCATE`.
  0015 granted write-everything on all tables; this narrows it back. An audit
  log the application can rewrite is worthless against the one attacker it
  exists to catch — the one who reached the application. TRUNCATE is revoked
  explicitly because it bypasses row-level DELETE policies entirely.

Read it at `GET /v1/auth/audit-log` (owner/admin only — the rows contain every
attempted address for the tenant, which is precisely what an attacker holding
one low-privilege account would want next). Tenant-scoped twice over: the
`x-tenant-id` header drives the RLS GUC, and the policy filters regardless of
what the handler asks for.

#### Two write paths, and why

| Path                       | Transaction        | Used for                                             |
| -------------------------- | ------------------ | ---------------------------------------------------- |
| `audit.record(session, …)` | The caller's       | Successes — the row commits atomically with the act. |
| `audit.record_isolated(…)` | Its own, committed | **Failures.**                                        |

A failed login rolls its transaction back by definition. An audit row written
inside it rolls back too — losing exactly the rows anyone would ever page on.
This is the one case where a separate transaction is correct rather than
sloppy.

#### The swallow-but-count trade

Audit writes **never** raise to the caller. Stated plainly because it is a real
trade: a database problem degrades the audit log rather than taking down login.
The alternative makes the audit log a new availability dependency for
authentication — a bad deal for a SaaS whose users cannot work when they cannot
sign in.

The price is paid by `security_audit_write_failures_total` and the
`AuditLogWriteFailures` alert. **Silent** is the failure mode being guarded
against; **unavailable-but-loud** is what replaces it.

### 5. Alerts, runbook, dashboard

`infra/monitoring/prometheus/rules/security-metrics.yml` — five rules, all with
runbook sections in [12-PRODUCTION-RUNBOOK.md](../12-PRODUCTION-RUNBOOK.md)
(link resolution enforced by `tests/infra`):

| Alert                         | Severity | Fires on                                       |
| ----------------------------- | -------- | ---------------------------------------------- |
| `TokenForgeryAttempt`         | **page** | Any sustained signature/algorithm failure rate |
| `CrossTenantAccessAttempt`    | **page** | **Any** occurrence                             |
| `CredentialStuffingSuspected` | **page** | >50% of logins failing at >1/s                 |
| `HighAuthFailureRate`         | ticket   | >5 gateway auth rejections/s for 10m           |
| `AuditLogWriteFailures`       | ticket   | Privileged actions happening with no record    |

Three Grafana panels (ids 12–14) on the existing overview dashboard.

No new scrape target, port, or endpoint: every counter registers into the
default Prometheus registry that T309b's `/metrics` already exposes, on the
existing `app-metrics` job.

---

## Scope — what this deliberately does **not** cover

Stated so the gap is a known decision rather than an assumption:

- **Only the gateway and auth-service emit security metrics.** The other ten
  services do not. This is not laziness: the two signals that exist here can
  only be produced where both the untrusted request and the verified identity
  are visible (the gateway) or where credentials are checked (auth-service).
  A domain service sees an already-validated `x-tenant-id` and has nothing to
  compare it against — a "cross-tenant attempt" is not observable there.
- **Only auth actions are audited.** Role grants, user suspensions, refund
  issuance, and integration credential changes are privileged and belong in
  this log, but they live in services that would need a way to write it.
  Adding a cross-service audit ingestion API would have introduced
  service-to-service authentication, which this platform does not have yet, on
  the back of an observability task. `auth.py`'s `record()` is written to be
  portable when that lands; the action name is free-text precisely so a new
  kind of privileged action needs no migration.
- **No anomaly detection, no automatic blocking.** These are counters and
  alerts. Rate limiting stays at the gateway and Cloudflare.
- **No log retention/pruning policy for `auth_audit_log`.** It grows
  unboundedly. The owner role retains DELETE so pruning is possible as a
  deliberate privileged operation; nothing does it yet.

## Not verified

- **No Prometheus has ever evaluated these rules.** The PromQL is committed and
  the YAML parses; `promtool check rules` needs the Docker monitoring stack,
  which this machine cannot run. Handed to Agent 3 —
  [T310b handoff](../handoffs/T310b-security-observability-antigravity-handoff.md).
- **Migration 0016 has never been applied.** In particular the append-only
  REVOKE is asserted by reading the SQL, not by watching Postgres reject an
  UPDATE.
- **Thresholds are uncalibrated guesses.** There is no production traffic to
  calibrate against. Every runbook section says which direction to move its
  threshold and why.
- **No alert has ever fired**, so the Alertmanager → PagerDuty/Slack path for
  these specific rules is unproven end to end (the routing itself is shared
  with T309's alerts, which are equally unproven for the same reason).
