"""Domain entities (framework-free, pure Python) for the PDF engine (M9).

Scoped to what T107 needs: rendering a branded proposal PDF from data handed
in by the caller (quote-service + customer-service + tenant branding). This
is deliberately lighter than the full Proposal Builder (M8/T203) — there is
no `proposal` DB table yet; that persistence layer, templates, and versioning
land with T203. The PDF engine is a stateless rendering capability T203 will
call into.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

CURRENCY_SYMBOLS = {"USD": "$", "CAD": "$", "AUD": "$", "NZD": "$", "GBP": "£"}


@dataclass(slots=True, frozen=True)
class Money:
    """Integer minor units (cents) + ISO-4217 currency. Never floats."""

    amount_minor: int
    currency: str = "USD"

    def formatted(self) -> str:
        symbol = CURRENCY_SYMBOLS.get(self.currency, "")
        return f"{symbol}{self.amount_minor / 100:,.2f}"


@dataclass(slots=True)
class CompanyBranding:
    company_name: str
    logo_path: str | None = None  # local path or URL to a logo image
    primary_color: str = "#111827"  # hex, used for headings/rules
    phone: str | None = None
    email: str | None = None
    website: str | None = None


@dataclass(slots=True)
class CustomerInfo:
    display_name: str
    email: str | None = None
    phone: str | None = None
    property_address: str | None = None


@dataclass(slots=True)
class ProposalLineItem:
    description: str
    quantity: float
    unit: str
    unit_price: Money
    line_total: Money


@dataclass(slots=True)
class ProposalDocument:
    proposal_id: UUID
    quote_id: UUID
    tenant_id: UUID
    branding: CompanyBranding
    customer: CustomerInfo
    line_items: list[ProposalLineItem]
    subtotal: Money
    tax: Money
    total: Money
    scope_of_work: str
    warranty_text: str | None = None
    terms_text: str | None = None
    valid_until: str | None = None  # display-only ISO date, e.g. "2026-08-15"
    qr_payload_url: str | None = None  # link a QR code should open (view/pay page)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
