# Proposal Service — PDF Engine (Module M9)

- **Owner Agent:** Agent 4 — Opus + Sonnet 4.6 (this task, T107, built by Agent 1/CTO)
- **Bounded Context / Purpose:** Branded PDF rendering for proposals/quotes
- **Status:** T107 implemented + unit-verified (14/14 tests, ruff + mypy clean).

## Scope note

This is deliberately narrower than the full **Proposal Builder (M8 / T203)**. There is no `proposal`
DB table yet — this service is a **stateless PDF-rendering capability**: given a fully-populated
document (branding + customer + line items + totals, assembled by the caller from quote-service +
customer-service + tenant settings), it renders a professional, branded, multi-page PDF and stores
it. T203 will own persistence, templates, and versioning, and will call into this engine rather than
duplicate PDF logic.

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
├── domain/          entities.py (ProposalDocument/Money/LineItem), events.py, errors.py,
│                     storage.py (PdfStorage Protocol)
├── application/      pdf_renderer.py (pure rendering, reportlab + qrcode),
│                     services.py (render_and_store_proposal_pdf, fetch_proposal_pdf)
├── infrastructure/   local_storage.py (tenant-scoped local-disk PdfStorage impl)
└── interface/        schemas.py (Pydantic DTOs), routes.py (FastAPI)
main.py               FastAPI app + /health
```

## Endpoints (v1)

| Method | Path                     | Purpose                                       |
| ------ | ------------------------ | --------------------------------------------- |
| POST   | `/v1/proposals/pdf`      | Render + store a branded PDF, return metadata |
| GET    | `/v1/proposals/{id}/pdf` | Stream the stored PDF bytes back              |
| GET    | `/health`                | Liveness                                      |

Wired into the API Gateway at `/v1/proposals` (`apps/api-gateway`, `PROPOSAL_SERVICE_URL`, default
port `8005`).

## Develop

```bash
uv venv --python 3.12 && uv pip install -e ".[dev]"
uv run pytest -q       # 14 tests: renderer (real PDF text-extraction checks) + use cases (fakes)
uvicorn app.main:app --reload --port 8005
```

## Definition of Done

- ✅ Clean Architecture layering; storage behind a `Protocol` (Repository-Pattern style)
- ✅ Emits domain events per `packages/types` contract
- ✅ Tenant-scoped storage (local-disk paths keyed by `tenant_id`)
- ✅ Behavioral tests: renderer output verified via real PDF text extraction (`pypdf`), not just
  "didn't crash"; use cases tested against an in-memory fake storage
- ✅ ruff + mypy clean; wired into the gateway
- ⬜ Full Proposal Builder (persistence, templates, versioning) — T203, lands separately
- ⬜ Swap local-disk storage for MinIO/S3 once object storage is live (T002b infra already runs it)
