"""HTTP REST API routes for payment-service.

Trusts the API Gateway's identity headers (x-tenant-id, x-user-id) — the gateway already
verified the JWT (see apps/api-gateway), so this service never decodes tokens itself.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Header, HTTPException, Query, Request, status

from app.application.services import (
    DuplicateIdempotencyKeyError,
    InvoiceNotFoundError,
    PaymentNotFoundError,
    capture_payment,
    create_invoice,
    create_payment_intent,
    fail_payment,
    get_invoice,
    get_payment,
    get_payment_by_provider_id,
    issue_invoice,
    list_invoices,
    list_payments,
)
from app.domain.models import InvoiceStatus, PaymentStatus
from app.infrastructure.db import tenant_session
from app.interface.schemas import (
    InvoiceCreate,
    InvoiceIssueRequest,
    InvoiceResponse,
    PaymentIntentCreate,
    PaymentResponse,
)

router = APIRouter(prefix="/v1/payments", tags=["payments"])


def _require_tenant(x_tenant_id: str | None) -> uuid.UUID:
    if not x_tenant_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing tenant context")
    try:
        return uuid.UUID(x_tenant_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid tenant id") from exc


def _require_user(x_user_id: str | None) -> uuid.UUID | None:
    if not x_user_id:
        return None
    try:
        return uuid.UUID(x_user_id)
    except ValueError:
        return None


# --- Payment Intents ---


@router.post("/intents", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
def create_intent(
    body: PaymentIntentCreate,
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> PaymentResponse:
    tenant_id = _require_tenant(x_tenant_id)
    try:
        with tenant_session(tenant_id) as session:
            payment = create_payment_intent(
                session,
                tenant_id=tenant_id,
                quote_id=body.quote_id,
                provider=body.provider,
                payment_type=body.payment_type,
                amount_minor=body.amount_minor,
                currency=body.currency,
                idempotency_key=body.idempotency_key,
                description=body.description,
            )
            return PaymentResponse.model_validate(payment)
    except DuplicateIdempotencyKeyError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc


# --- Payments ---


@router.get("", response_model=list[PaymentResponse])
def list_payments_route(
    quote_id: uuid.UUID | None = Query(default=None),
    payment_status: PaymentStatus | None = Query(default=None, alias="status"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    x_tenant_id: str | None = Header(default=None),
) -> list[PaymentResponse]:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as session:
        payments = list_payments(
            session,
            tenant_id=tenant_id,
            quote_id=quote_id,
            status=payment_status,
            skip=skip,
            limit=limit,
        )
        return [PaymentResponse.model_validate(p) for p in payments]


@router.get("/{payment_id}", response_model=PaymentResponse)
def get_payment_route(
    payment_id: uuid.UUID,
    x_tenant_id: str | None = Header(default=None),
) -> PaymentResponse:
    tenant_id = _require_tenant(x_tenant_id)
    try:
        with tenant_session(tenant_id) as session:
            payment = get_payment(session, tenant_id, payment_id)
            return PaymentResponse.model_validate(payment)
    except PaymentNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# --- Invoices ---


@router.post("/invoices", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
def create_invoice_route(
    body: InvoiceCreate,
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> InvoiceResponse:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as session:
        invoice = create_invoice(
            session,
            tenant_id=tenant_id,
            quote_id=body.quote_id,
            customer_id=body.customer_id,
            subtotal_minor=body.subtotal_minor,
            tax_minor=body.tax_minor,
            total_minor=body.total_minor,
            currency=body.currency,
            due_at=body.due_at,
            deposit_bps=body.deposit_bps,
            notes=body.notes,
        )
        return InvoiceResponse.model_validate(invoice)


@router.get("/invoices", response_model=list[InvoiceResponse])
def list_invoices_route(
    quote_id: uuid.UUID | None = Query(default=None),
    invoice_status: InvoiceStatus | None = Query(default=None, alias="status"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    x_tenant_id: str | None = Header(default=None),
) -> list[InvoiceResponse]:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as session:
        invoices = list_invoices(
            session,
            tenant_id=tenant_id,
            quote_id=quote_id,
            status=invoice_status,
            skip=skip,
            limit=limit,
        )
        return [InvoiceResponse.model_validate(i) for i in invoices]


@router.get("/invoices/{invoice_id}", response_model=InvoiceResponse)
def get_invoice_route(
    invoice_id: uuid.UUID,
    x_tenant_id: str | None = Header(default=None),
) -> InvoiceResponse:
    tenant_id = _require_tenant(x_tenant_id)
    try:
        with tenant_session(tenant_id) as session:
            invoice = get_invoice(session, tenant_id, invoice_id)
            return InvoiceResponse.model_validate(invoice)
    except InvoiceNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/invoices/{invoice_id}/issue", response_model=InvoiceResponse)
def issue_invoice_route(
    invoice_id: uuid.UUID,
    body: InvoiceIssueRequest | None = None,
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> InvoiceResponse:
    tenant_id = _require_tenant(x_tenant_id)
    due_at = body.due_at if body else None
    try:
        with tenant_session(tenant_id) as session:
            invoice = issue_invoice(session, tenant_id, invoice_id, due_at=due_at)
            return InvoiceResponse.model_validate(invoice)
    except InvoiceNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# --- Webhooks (public — gateway skips auth for these) ---


@router.post("/webhooks/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(request: Request) -> dict[str, str]:
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        import stripe as stripe_sdk

        from app.config import settings

        if settings.stripe_webhook_secret:
            event = stripe_sdk.Webhook.construct_event(
                payload, sig_header, settings.stripe_webhook_secret
            )
        else:
            import json
            event = json.loads(payload)
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    event_type = event.get("type", "")

    if event_type == "checkout.session.completed":
        session_data = event.get("data", {}).get("object", {})
        provider_id = session_data.get("id")
        metadata = session_data.get("metadata", {})
        tenant_id_str = metadata.get("tenant_id")

        if provider_id and tenant_id_str:
            tenant_id = uuid.UUID(tenant_id_str)
            with tenant_session(tenant_id) as db_session:
                payment = get_payment_by_provider_id(db_session, provider_id)
                if payment:
                    capture_payment(db_session, tenant_id, payment.id, provider_id)

    elif event_type == "checkout.session.expired":
        session_data = event.get("data", {}).get("object", {})
        provider_id = session_data.get("id")
        metadata = session_data.get("metadata", {})
        tenant_id_str = metadata.get("tenant_id")

        if provider_id and tenant_id_str:
            tenant_id = uuid.UUID(tenant_id_str)
            with tenant_session(tenant_id) as db_session:
                payment = get_payment_by_provider_id(db_session, provider_id)
                if payment:
                    fail_payment(db_session, tenant_id, payment.id, "Checkout session expired")

    return {"status": "ok"}


@router.post("/webhooks/square", status_code=status.HTTP_200_OK)
async def square_webhook(request: Request) -> dict[str, str]:
    payload = await request.json()
    event_type = payload.get("type", "")

    if event_type == "payment.completed":
        data = payload.get("data", {}).get("object", {}).get("payment", {})
        provider_id = data.get("id")
        note = data.get("note", "")

        if provider_id and "|" in note:
            parts = note.split("|")
            tenant_id_str = parts[0] if len(parts) > 0 else None
            if tenant_id_str:
                try:
                    tenant_id = uuid.UUID(tenant_id_str)
                    with tenant_session(tenant_id) as db_session:
                        payment = get_payment_by_provider_id(db_session, provider_id)
                        if payment:
                            capture_payment(db_session, tenant_id, payment.id, provider_id)
                except ValueError:
                    pass

    return {"status": "ok"}
