# 🟢 Verification Evidence — T311 (Live-Postgres & RLS Pass)

- **Verified by:** Agent 3 — Google Antigravity (Gemini 3.6)
- **Date:** 2026-07-28
- **PostgreSQL Environment:** GCP Compute Engine instance `tradequote-pg-test` running container `pgvector/pgvector:pg16` on `us-east1-b`
- **Database Role:** `tradequote_app` (non-superuser application role enforcing RLS)

---

## 📋 Summary of Verified Live-Postgres Acceptance Criteria

| # | Acceptance Criterion | Status | Evidence / Test Executed |
|---|---|---|---|
| 1 | **PostgreSQL RLS Suite** | ✅ **PASSED** | Executed `tests/integration/test_postgres_rls.py` for real against GCP PostgreSQL with all 8 migrations applied. |
| 2 | **T203 Proposal `SECURITY DEFINER` & RLS** | ✅ **PASSED** | Verified `resolve_proposal_tenant(proposal_id)` returns tenant without RLS context for public `/view`, and cross-tenant reads return 0 rows. |
| 3 | **T206 / T206b Quotes Summary & Lowercase Enum Matching** | ✅ **PASSED** | Verified status equality filters (`'sent'`, `'accepted'`) match lower-case Postgres ENUM labels correctly via `values_callable`. |
| 4 | **T307b Analytics `analytics_events` RLS** | ✅ **PASSED** | Verified `analytics_events` RLS policy `tenant_isolation` enforces multi-tenant boundary on live database. |
| 5 | **Cross-Tenant Write Protection** | ✅ **PASSED** | Verified cross-tenant `INSERT` attempt throws `psycopg.errors.InsufficientPrivilege / row-level security policy` error. |

---

## 💻 Live Test Output Log

```text
============================= test session starts =============================
platform win32 -- Python 3.12.13, pytest-9.1.1, pluggy-1.6.0
rootdir: D:\TradeQuote AI
plugins: anyio-4.14.2
collected 6 items

tests\integration\test_postgres_rls.py ......                            [100%]

============================= 6 passed in 22.80s ==============================
```

---

## 🛠️ GCP Resource Teardown

- VM instance `tradequote-pg-test` (GCP e2-medium) deleted via `gcloud compute instances delete tradequote-pg-test --zone=us-east1-b`.
- Firewall rule `allow-postgres-test` deleted via `gcloud compute firewall-rules delete allow-postgres-test`.
