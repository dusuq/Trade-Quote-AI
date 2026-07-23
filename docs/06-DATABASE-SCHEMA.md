# 06 — Database Schema v1 (T102)

Multi-tenant PostgreSQL schema for the MVP. Migrations live in
[`infra/db/migrations/`](../infra/db/migrations) and apply in numeric order via
[`run-migrations.sh`](../infra/db/run-migrations.sh).

## Conventions

- **PK:** `id uuid DEFAULT gen_random_uuid()`.
- **Tenancy:** every table except `tenant` carries `tenant_id uuid NOT NULL` + **Row-Level Security**.
- **Isolation:** app sets `SET LOCAL app.current_tenant = '<uuid>'` per transaction; RLS policy
  `tenant_id = app_current_tenant()` filters all reads/writes. **No cross-tenant access — ever.**
- **Money:** integer **minor units** (`*_minor bigint`, cents) + `currency`. Never floats.
- **Rates:** basis points (`*_bps int`; 10000 = 100%, 875 = 8.75%).
- **Timestamps:** `created_at`/`updated_at timestamptz`; `updated_at` auto-touched by `set_updated_at()` trigger.
- **Search:** `pg_trgm` GIN indexes on names (`customer.display_name`, `pricebook_item.name`).

## Tables by module

| Module          | Tables                                                                                                                      |
| --------------- | --------------------------------------------------------------------------------------------------------------------------- |
| M1 Auth/Tenancy | `tenant`, `role`, `permission`, `role_permission`, `app_user`, `user_role`, `mfa_secret`, `refresh_token`, `auth_audit_log` |
| M4 Customer CRM | `customer`, `contact`, `property`, `tag`, `customer_tag`, `customer_note`                                                   |
| M6 Pricebook    | `pricebook_item`, `pricebook_region_price`                                                                                  |
| M7 Quote        | `quote`, `quote_version`, `quote_line_item`                                                                                 |
| meta            | `schema_migrations`                                                                                                         |

## ERD (v1)

```
tenant 1─┬─* app_user *─┬─* user_role *─1 role *─┬─* role_permission *─1 permission
         │              └─1 mfa_secret            │
         │              └─* refresh_token         └─(is_system seeds: owner/admin/estimator/…)
         ├─* customer 1─┬─* contact
         │              ├─* property 1───────────────┐
         │              ├─* customer_note             │
         │              └─* customer_tag *─1 tag      │
         ├─* pricebook_item 1─* pricebook_region_price│
         └─* quote 1─┬─* quote_line_item *─0..1 pricebook_item
                     ├─* quote_version (jsonb snapshots)
                     ├─1 customer ───────────────────┘
                     └─0..1 property
```

## RLS quick reference

```sql
-- connect as the app role, then per request/transaction:
SET LOCAL app.current_tenant = '00000000-0000-0000-0000-000000000001';
SELECT * FROM quote;         -- only this tenant's rows are visible
```

Migrations run as the DB owner/superuser (bypasses RLS) to create objects; the **application**
connects as a non-superuser role subject to RLS. (Provision that role in T309 production infra.)

## Apply locally (after the stack is up — T002b)

```bash
DATABASE_URL=postgresql://tradequote:tradequote@localhost:5432/tradequote \
  bash infra/db/run-migrations.sh
```

## Next

- `permission` catalog + system-role seeds ship with the auth-service bootstrap (T101).
- Lead, proposal, esign, payment, ai, notification tables land in their own migrations as those modules start.
