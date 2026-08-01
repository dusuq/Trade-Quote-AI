"""Pydantic schemas (DTOs) for the payment-service interface layer."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import (
    InvoiceStatus,
    PaymentProvider,
    PaymentStatus,
    PaymentType,
)


class PaymentIntentCreate(BaseModel):
    quote_id: uuid.UUID
    provider: PaymentProvider = PaymentProvider.STRIPE
    payment_type: PaymentType = PaymentType.DEPOSIT
    amount_minor: int = Field(..., gt=0, description="Amount in minor units (cents)")
    currency: str = Field(default="USD", min_length=3, max_length=3)
    description: str | None = None
    idempotency_key: str = Field(..., min_length=1, max_length=255)


class PaymentResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    quote_id: uuid.UUID
    invoice_id: uuid.UUID | None
    provider: PaymentProvider
    payment_type: PaymentType
    status: PaymentStatus
    amount_minor: int
    currency: str
    provider_payment_id: str | None
    provider_checkout_url: str | None
    description: str | None
    failure_reason: str | None
    idempotency_key: str
    captured_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InvoiceCreate(BaseModel):
    quote_id: uuid.UUID
    customer_id: uuid.UUID
    subtotal_minor: int = Field(..., ge=0)
    tax_minor: int = Field(default=0, ge=0)
    total_minor: int = Field(..., ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    due_at: datetime | None = None
    deposit_bps: int = Field(
        default=5000, ge=0, le=10000,
        description="Deposit percentage in basis points (5000 = 50%)",
    )
    notes: str | None = None


class InvoiceResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    quote_id: uuid.UUID
    customer_id: uuid.UUID
    number: str
    status: InvoiceStatus
    subtotal_minor: int
    tax_minor: int
    total_minor: int
    amount_paid_minor: int
    amount_due_minor: int
    currency: str
    due_at: datetime | None
    issued_at: datetime | None
    paid_at: datetime | None
    deposit_bps: int
    notes: str | None
    created_at: datetime
    updated_at: datetime
    payments: list[PaymentResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class InvoiceIssueRequest(BaseModel):
    due_at: datetime | None = None


class StripeWebhookPayload(BaseModel):
    id: str
    type: str
    data: dict[str, object]


class SquareWebhookPayload(BaseModel):
    type: str
    event_id: str
    data: dict[str, object]
