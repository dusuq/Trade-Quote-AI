# Proposal Service — PDF Engine + Proposal Builder (Modules M9 / M8)

- **Owner Agent:** Agent 4 — Opus + Sonnet 4.6 (T107 PDF engine; T203 Proposal Builder)
- **Bounded Context / Purpose:** Branded PDF rendering, plus persistence, templates, and lifecycle
  for proposals/quotes
- **Status:** T107 (PDF engine) implemented + unit-verified. T203 (Proposal Builder: persistence,
  templates, send/view lifecycle, the public view-link route) implemented on top of it — see
  `docs/modules/M8-proposal-builder.md`.

## Scope note

T107 shipped a **stateless PDF-rendering capability**: given a fully-populated document (branding +
customer + line items + totals, assembled by the caller from quote-service + customer-service +
tenant settings), it renders a professional, branded, multi-page PDF and stores it. T203 (this
task's persistence layer) now owns the `proposal` and `proposal_version` DB tables, proposal
templates, and the create/send/view lifecycle, calling into the T107 engine rather than duplicating
PDF logic. See `docs/modules/M8-proposal-builder.md` for the full module spec.

## Responsibilities

- Render a branded proposal PDF: cover page, customer/property info, scope of work, a line-items
  table, subtotal/tax/total, warranty and terms sections, and a signature page
- Embed a QR code (caller supplies the payload URL — e.g. a future view/pay page)
- Persist the rendered PDF via a storage `Protocol` (local disk today; swap for the MinIO/S3-compatible
  object store in `infra/docker` without touching use-case code)
- Emit `proposal.document.generated` / `proposal.document.pdfRendered` domain events

## Architecture (Clean Architecture layering)

```
app/
├── domain/          entities.py (ProposalDocument/Money/LineItem), proposal.py (Proposal,
│                     ProposalTemplate, TenantResolver Protocol), events.py, errors.py,
│                     storage.py (PdfStorage Protocol)
├── application/      pdf_renderer.py (pure rendering, reportlab + qrcode),
│                     services.py (render_and_store_proposal_pdf, fetch_proposal_pdf),
│                     proposal_services.py (create/get/send/view/list_versions),
│                     template_services.py (template CRUD)
├── infrastructure/   local_storage.py (tenant-scoped local-disk PdfStorage impl),
│                     db.py (tenant_session, PostgresTenantResolver), models.py (SQLAlchemy)
└── interface/        schemas.py (Pydantic DTOs), routes.py (T107 PDF routes, FastAPI),
                      proposal_routes.py (proposal CRUD/send/view), template_routes.py
main.py               FastAPI app + /health
```

## Endpoints (v1)

| Method | Path                           | Purpose                                                       |
| ------ | ------------------------------ | -------------------------------------------------------------- |
| POST   | `/v1/proposals/pdf`            | Render + store a branded PDF, return metadata (T107)          |
| GET    | `/v1/proposals/{id}/pdf`       | Stream the stored PDF bytes back (T107)                       |
| POST   | `/v1/proposals`                | Create a proposal (persists + renders version 1 PDF)          |
| GET    | `/v1/proposals/{id}`           | Fetch a proposal by id                                        |
| GET    | `/v1/proposals/{id}/versions`  | List a proposal's version history                             |
| POST   | `/v1/proposals/{id}/send`      | Mark a proposal SENT, emits `proposal.sent`                   |
| GET    | `/v1/proposals/{id}/view`      | **Public, no auth headers** — the customer's view link; marks VIEWED on first open, streams the PDF |
| POST   | `/v1/proposal-templates`       | Create a proposal template                                    |
| GET    | `/v1/proposal-templates`       | List a tenant's proposal templates                            |
| PUT    | `/v1/proposal-templates/{id}`  | Update a proposal template                                    |
| GET    | `/health`                      | Liveness                                                       |

Every route above trusts the API Gateway's `x-tenant-id` header and requires it — except
`GET /v1/proposals/{id}/view`, which is the one deliberately public route in this codebase: it
resolves its own tenant via a `SECURITY DEFINER` Postgres function (`PostgresTenantResolver`, see
`app/infrastructure/db.py`) since a customer opening their proposal link has no TradeQuote AI
session at all.

Wired into the API Gateway at `/v1/proposals` and `/v1/proposal-templates` (`apps/api-gateway`,
`PROPOSAL_SERVICE_URL`, default port `8005`). The gateway pattern-matches the `/view` path as
public; all other routes require a valid session.

## Develop

```bash
uv venv --python 3.12 && uv pip install -e ".[dev]"
uv run pytest -q       # 30 tests: renderer (real PDF text-extraction checks) + use cases (fakes) + routes
uvicorn app.main:app --reload --port 8005
```

## Definition of Done

- ✅ Clean Architecture layering; storage behind a `Protocol` (Repository-Pattern style)
- ✅ Emits domain events per `packages/types` contract
- ✅ Tenant-scoped storage (local-disk paths keyed by `tenant_id`)
- ✅ Behavioral tests: renderer output verified via real PDF text extraction (`pypdf`), not just
  "didn't crash"; use cases tested against an in-memory fake storage
- ✅ ruff + mypy clean; wired into the gateway
- ✅ Full Proposal Builder (persistence, templates, versioning) — T203, implemented on top of the
  T107 PDF engine: `proposal`/`proposal_version` tables, template CRUD, create/send/view lifecycle,
  and the public `/view` route (404s on unknown/draft ids and on a missing stored PDF, never a 500)
- ⬜ Swap local-disk storage for MinIO/S3 once object storage is live (T002b infra already runs it)
