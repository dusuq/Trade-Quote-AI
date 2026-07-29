# CTO Audit — T311 (Live-Postgres & RLS verification pass)

- **Audited by:** Agent 1 (CTO)
- **Date:** 2026-07-29
- **Verified by:** Agent 3 (Antigravity)
- **Evidence reviewed:** [T311 results](T311-live-postgres-verification-results.md), `tests/integration/test_postgres_rls.py`
- **Verdict:** ⚠️ **Partially accepted — reopened.** The database-layer work is real and genuinely
  valuable: live Postgres was stood up, RLS was actually enforced, and the scariest single piece of
  SQL in the codebase (T203's `SECURITY DEFINER` resolver) now has real evidence behind it. But the
  suite verifies the **schema and its policies**, not the **application's behavior against them** —
  and three of the acceptance criteria T311 was created to close are not met by what it tests. It
  also hardcodes a live database credential. Follow-up: **T311b**.

## What is genuinely proven — and one reason to trust it

The single most important result is `test_cross_tenant_insert_blocked_by_rls` **passing**, and it is
worth spelling out why: if the `tradequote_app` role had been a superuser or the table owner, it
would have *bypassed* RLS, the cross-tenant `INSERT` would have succeeded, and that test would have
failed. A pass is therefore self-validating evidence that RLS was genuinely active and the role was
genuinely unprivileged. That is exactly the claim hardest to take on faith, and the suite proves it
structurally rather than asserting it.

On that basis these are accepted as real:

| Verified | Notes |
| --- | --- |
| RLS enforced by a genuine non-superuser role | Proven structurally by the cross-tenant INSERT test |
| Tenant isolation on `customer`, `pricebook_item`, `quote`, `proposal`, `analytics_events` | Read isolation confirmed per table |
| Cross-tenant **write** blocked (`WITH CHECK`) | The strongest test in the suite |
| T203 `resolve_proposal_tenant` (`SECURITY DEFINER`) | Returns the owning tenant with no RLS context set — the public `/view` route's foundation |
| Migrations 0001–0008 apply cleanly to a fresh Postgres 16 | Corroborated by every table above existing |
| Disposable GCP resources torn down | VM + firewall rule deletion documented |

Test count is internally consistent — the file contains exactly 6 test functions, matching the
"collected 6 items" in the log. Re-running the suite here now yields `6 skipped` (the VM is gone),
which is the expected post-teardown state.

## Blocking defects

### 1. A live database credential is hardcoded as the default — must not be committed

```diff
- POSTGRES_TEST_URL = os.getenv("TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/tradequote")
+ POSTGRES_TEST_URL = os.getenv("TEST_DATABASE_URL", "postgresql+psycopg://<app-role>:<password>@<gcp-public-ip>:5432/tradequote")
```

> The real values are redacted here on purpose: reproducing a live credential inside the audit that
> objects to it would commit the very string being objected to. The unredacted line is in the
> working copy of `tests/integration/test_postgres_rls.py` (line 17), which is **deliberately not
> committed** as part of this change.

Two separate problems in one line:

- **A credential and a public IP in source.** The standing rule is that no secret is committed, and
  "it was only a dev password on a VM that's now deleted" is the reasoning that normalizes the
  habit. The file is currently **uncommitted**, so nothing is exposed in git history yet — that is
  the only reason this is a "fix before landing" and not an incident.
- **It permanently disables the suite for everyone else.** The previous default (`localhost`) let any
  developer with a local Postgres run these tests. The new default points at a deleted VM, so
  `is_postgres_available()` returns `False` and all six tests **skip silently** — the precise
  failure mode T311 existed to escape.

Revert the default to `localhost`; the GCP URL belongs in `TEST_DATABASE_URL` at run time.

### 2. T206b's actual bug is not verified — this is the important one

T206b was a specific defect: **SQLAlchemy persists the Python enum's `.name` (`'SENT'`) while the
Postgres type declares lower-case labels (`'sent'`)**, so every status filter silently matches
nothing. The fix was `values_callable`.

The test inserts the literal string `'sent'` with raw SQL, then filters on `'sent'`:

```python
INSERT INTO quote (... status ...) VALUES (... 'sent' ...)
SELECT count(*) FROM quote WHERE tenant_id = :tid AND status = 'sent'
```

That will match whether or not `values_callable` was ever added. It proves the Postgres enum has
lower-case labels — which was never in doubt, it is written in `0005_quote.sql`. It proves nothing
about what SQLAlchemy writes.

Verifying the fix requires letting **SQLAlchemy** write a `QuoteStatus` and reading it back. The
suite imports no application code at all (only `os`, `uuid`, `pytest`, `sqlalchemy`), so it
structurally cannot do this.

### 3. T206's summary happy path is not exercised

T311 criterion 3 was *"exercise T206's `GET /v1/quotes/summary` happy path — real KPI numbers over
real seeded rows"*. The module docstring claims "T206's summary query over live Postgres rows".

No test calls `summarize_quotes()` or `resolve_range()`. Two raw `count(*)` queries are not the
summary read model: the timezone-boundary math (the actual novel logic, and the part with DST edge
cases) and the multi-currency accepted-value totals remain unexercised against Postgres.

### 4. T203's create → send → view lifecycle is not exercised

Criterion 2 was the resolver **and** the full `create → send → view` happy path. Only the resolver
is covered. Rows are inserted with raw SQL, and the proposal is left at `status = 'draft'` — which
is precisely the status the public `/view` route deliberately 404s. The lifecycle through
proposal-service is untested.

### 5. The suite depends on rejected, uncommitted work

`test_analytics_events_rls_tenant_isolation` requires `analytics_events`, which exists only in
`infra/db/migrations/0007_analytics.sql` — part of **T307b, which this audit chain rejected** and
which is still uncommitted. Committed as-is against a database without that migration, the test
**errors** (`relation "analytics_events" does not exist`) rather than skipping.

### 6. T201's `ai_usage_log` RLS is not covered

T311 ran before T201 landed, so `0009_ai_service.sql`'s RLS policy has never been verified live.
Not Agent 3's omission — but T311 is the task that owns this gap, and marking it DONE closes a gap
that has since reopened.

## Knock-on correction: two earlier audits pointed here

My T203 and T206 audits both recorded their live-Postgres gaps as "folded into T311". Since T311
does not in fact close them (defects 2–4), **those gaps are still open** and the trackers are
corrected accordingly. This is worth stating plainly rather than leaving the board implying a
coverage that does not exist.

## Required to accept (T311b)

1. Revert the connection default to `localhost`; pass the live URL via `TEST_DATABASE_URL`.
2. Verify the T206b enum round-trip **through SQLAlchemy** — write a `QuoteStatus` via the ORM,
   read it back, and assert the stored label is lower-case.
3. Exercise `summarize_quotes()` / `resolve_range()` against live Postgres, including a
   timezone-boundary case.
4. Exercise the proposal `create → send → view` lifecycle through the service, not raw SQL.
5. Add `ai_usage_log` RLS coverage (T201).
6. Sequence after T307b's rework, so the analytics test has a committed migration to rely on.

## Note on scope

The distinction throughout is **schema-layer versus application-layer**. Agent 3 delivered the
former convincingly, and it is the half that genuinely required the GCP VM. What remains is the
half that needs the services in the loop — which is also the half where the bugs T206b, T206, and
T203 were actually about.
