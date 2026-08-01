"""Business logic for the payment-service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import stripe as stripe_sdk
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.domain.models import (
    InvoiceModel,
    InvoiceStatus,
    PaymentModel,
    PaymentProvider,
    PaymentStatus,
    PaymentType,
)


class PaymentNotFoundError(Exception):
    pass


class InvoiceNotFoundError(Exception):
    pass


class DuplicateIdempotencyKeyError(Exception):
    pass


def _next_invoice_number(session: Session, tenant_id: uuid.UUID) -> str:
    result = session.execute(
        select(InvoiceModel)
        .where(InvoiceModel.tenant_id == tenant_id)
        .order_by(InvoiceModel.created_at.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()
    if last and last.number.startswith("INV-"):
        try:
            seq = int(last.number.split("-")[1]) + 1
        except (IndexError, ValueError):
            seq = 1
    else:
        seq = 1
    return f"INV-{seq:05d}"


def create_payment_intent(
    session: Session,
    tenant_id: uuid.UUID,
    quote_id: uuid.UUID,
    provider: PaymentProvider,
    payment_type: PaymentType,
    amount_minor: int,
    currency: str,
    idempotency_key: str,
    description: str | None = None,
    actor_id: uuid.UUID | None = None,
) -> PaymentModel:
    existing = session.execute(
        select(PaymentModel).where(PaymentModel.idempotency_key == idempotency_key).limit(1)
    ).scalar_one_or_none()
    if existing:
        raise DuplicateIdempotencyKeyError(
            f"Payment with idempotency key '{idempotency_key}' already exists"
        )

    provider_payment_id: str | None = None
    checkout_url: str | None = None

    if provider == PaymentProvider.STRIPE and settings.stripe_secret_key:
        stripe_sdk.api_key = settings.stripe_secret_key
        checkout = stripe_sdk.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": currency.lower(),
                    "unit_amount": amount_minor,
                    "product_data": {"name": description or "Payment for quote"},
                },
                "quantity": 1,
            }],
            mode="payment",
            metadata={
                "tenant_id": str(tenant_id),
                "quote_id": str(quote_id),
                "idempotency_key": idempotency_key,
            },
            success_url="https://app.tradequote.ai/payments/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url="https://app.tradequote.ai/payments/cancel",
            idempotency_key=idempotency_key,
        )
        provider_payment_id = checkout.id
        checkout_url = checkout.url

    payment = PaymentModel(
        tenant_id=tenant_id,
        quote_id=quote_id,
        provider=provider,
        payment_type=payment_type,
        status=PaymentStatus.PENDING,
        amount_minor=amount_minor,
        currency=currency,
        provider_payment_id=provider_payment_id,
        provider_checkout_url=checkout_url,
        description=description,
        idempotency_key=idempotency_key,
    )
    session.add(payment)
    session.flush()
    return payment


def capture_payment(
    session: Session,
    tenant_id: uuid.UUID,
    payment_id: uuid.UUID,
    provider_payment_id: str | None = None,
) -> PaymentModel:
    payment = session.execute(
        select(PaymentModel).where(
            PaymentModel.id == payment_id,
            PaymentModel.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if not payment:
        raise PaymentNotFoundError(f"Payment {payment_id} not found")

    payment.status = PaymentStatus.CAPTURED
    payment.captured_at = datetime.now(UTC)
    if provider_payment_id:
        payment.provider_payment_id = provider_payment_id
    session.flush()

    if payment.invoice_id:
        _update_invoice_paid_amount(session, tenant_id, payment.invoice_id)

    return payment


def fail_payment(
    session: Session,
    tenant_id: uuid.UUID,
    payment_id: uuid.UUID,
    reason: str,
) -> PaymentModel:
    payment = session.execute(
        select(PaymentModel).where(
            PaymentModel.id == payment_id,
            PaymentModel.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if not payment:
        raise PaymentNotFoundError(f"Payment {payment_id} not found")

    payment.status = PaymentStatus.FAILED
    payment.failure_reason = reason
    session.flush()
    return payment


def get_payment(
    session: Session, tenant_id: uuid.UUID, payment_id: uuid.UUID
) -> PaymentModel:
    payment = session.execute(
        select(PaymentModel).where(
            PaymentModel.id == payment_id,
            PaymentModel.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if not payment:
        raise PaymentNotFoundError(f"Payment {payment_id} not found")
    return payment


def list_payments(
    session: Session,
    tenant_id: uuid.UUID,
    quote_id: uuid.UUID | None = None,
    status: PaymentStatus | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[PaymentModel]:
    stmt = select(PaymentModel).where(PaymentModel.tenant_id == tenant_id)
    if quote_id:
        stmt = stmt.where(PaymentModel.quote_id == quote_id)
    if status:
        stmt = stmt.where(PaymentModel.status == status)
    stmt = stmt.order_by(PaymentModel.created_at.desc()).offset(skip).limit(limit)
    return list(session.execute(stmt).scalars().all())


def get_payment_by_provider_id(
    session: Session, provider_payment_id: str
) -> PaymentModel | None:
    return session.execute(
        select(PaymentModel).where(
            PaymentModel.provider_payment_id == provider_payment_id
        )
    ).scalar_one_or_none()


def create_invoice(
    session: Session,
    tenant_id: uuid.UUID,
    quote_id: uuid.UUID,
    customer_id: uuid.UUID,
    subtotal_minor: int,
    tax_minor: int,
    total_minor: int,
    currency: str = "USD",
    due_at: datetime | None = None,
    deposit_bps: int = 5000,
    notes: str | None = None,
) -> InvoiceModel:
    number = _next_invoice_number(session, tenant_id)
    invoice = InvoiceModel(
        tenant_id=tenant_id,
        quote_id=quote_id,
        customer_id=customer_id,
        number=number,
        status=InvoiceStatus.DRAFT,
        subtotal_minor=subtotal_minor,
        tax_minor=tax_minor,
        total_minor=total_minor,
        amount_paid_minor=0,
        amount_due_minor=total_minor,
        currency=currency,
        due_at=due_at,
        deposit_bps=deposit_bps,
        notes=notes,
    )
    session.add(invoice)
    session.flush()
    return invoice


def issue_invoice(
    session: Session,
    tenant_id: uuid.UUID,
    invoice_id: uuid.UUID,
    due_at: datetime | None = None,
) -> InvoiceModel:
    invoice = session.execute(
        select(InvoiceModel).where(
            InvoiceModel.id == invoice_id,
            InvoiceModel.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if not invoice:
        raise InvoiceNotFoundError(f"Invoice {invoice_id} not found")

    invoice.status = InvoiceStatus.ISSUED
    invoice.issued_at = datetime.now(UTC)
    if due_at:
        invoice.due_at = due_at
    session.flush()
    return invoice


def get_invoice(
    session: Session, tenant_id: uuid.UUID, invoice_id: uuid.UUID
) -> InvoiceModel:
    invoice = session.execute(
        select(InvoiceModel).where(
            InvoiceModel.id == invoice_id,
            InvoiceModel.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if not invoice:
        raise InvoiceNotFoundError(f"Invoice {invoice_id} not found")
    return invoice


def list_invoices(
    session: Session,
    tenant_id: uuid.UUID,
    quote_id: uuid.UUID | None = None,
    status: InvoiceStatus | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[InvoiceModel]:
    stmt = select(InvoiceModel).where(InvoiceModel.tenant_id == tenant_id)
    if quote_id:
        stmt = stmt.where(InvoiceModel.quote_id == quote_id)
    if status:
        stmt = stmt.where(InvoiceModel.status == status)
    stmt = stmt.order_by(InvoiceModel.created_at.desc()).offset(skip).limit(limit)
    return list(session.execute(stmt).scalars().all())


def _update_invoice_paid_amount(
    session: Session, tenant_id: uuid.UUID, invoice_id: uuid.UUID
) -> None:
    invoice = session.execute(
        select(InvoiceModel).where(
            InvoiceModel.id == invoice_id,
            InvoiceModel.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if not invoice:
        return

    captured_payments = session.execute(
        select(PaymentModel).where(
            PaymentModel.invoice_id == invoice_id,
            PaymentModel.status == PaymentStatus.CAPTURED,
        )
    ).scalars().all()

    total_paid = sum(p.amount_minor for p in captured_payments)
    invoice.amount_paid_minor = total_paid
    invoice.amount_due_minor = max(0, invoice.total_minor - total_paid)

    if invoice.amount_due_minor == 0:
        invoice.status = InvoiceStatus.PAID
        invoice.paid_at = datetime.now(UTC)

    session.flush()
