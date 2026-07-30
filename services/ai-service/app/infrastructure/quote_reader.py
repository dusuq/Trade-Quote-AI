"""Reading quotes from quote-service over HTTP (ADR-0003).

This is the read counterpart to `HttpQuoteCreator`. It is a *separate* class on
purpose (M16 plan Q1 / ISP): `HttpQuoteCreator` only ever POSTs, and a class
named "creator" that also reads would be misleading. Both share the one
sanctioned `ServiceClient`.

`GET /v1/quotes/{id}` is idempotent — safe to retry, which the client already
does for GETs.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.application.line_items import normalize_quantity
from app.domain.errors import QuoteNotFoundError, UpstreamServiceError
from app.domain.models import QuoteLineItem, QuoteSnapshot
from app.infrastructure.http import ServiceClient

# Keyword → trade, scanned against the quote title to seed the missing-items
# prompt. Advisory only: the model re-classifies from the actual line items and
# may override this. Order matters only in that the first hit wins.
_TRADE_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("electric", "electrical"),
    ("panel", "electrical"),
    ("wiring", "electrical"),
    ("plumb", "plumbing"),
    ("pipe", "plumbing"),
    ("drain", "plumbing"),
    ("hvac", "hvac"),
    ("furnace", "hvac"),
    ("air condition", "hvac"),
    ("ac ", "hvac"),
    ("solar", "solar"),
    ("pv ", "solar"),
    ("roof", "roofing"),
    ("shingle", "roofing"),
    ("floor", "flooring"),
    ("paint", "painting"),
    ("landscap", "landscaping"),
    ("clean", "cleaning"),
)


def _infer_trade_hint(title: str | None) -> str | None:
    if not title:
        return None
    lowered = title.lower()
    for keyword, trade in _TRADE_KEYWORDS:
        if keyword in lowered:
            return trade
    return None


class HttpQuoteReader:
    """Implements `QuoteReader` against `GET /v1/quotes/{id}`."""

    def __init__(self, client: ServiceClient) -> None:
        self._client = client

    def get_quote(
        self, tenant_id: UUID, user_id: UUID | None, quote_id: UUID
    ) -> QuoteSnapshot:
        try:
            payload = self._client.request(
                "GET",
                f"/v1/quotes/{quote_id}",
                tenant_id=tenant_id,
                user_id=user_id,
            )
        except UpstreamServiceError as exc:
            # quote-service returns 404 both for a genuinely missing quote and
            # for one in another tenant — either way it isn't this caller's to
            # see, so both surface as QuoteNotFoundError (→ 404, no leak).
            if exc.status_code == 404:
                raise QuoteNotFoundError(str(quote_id)) from exc
            raise
        return self._to_snapshot(payload)

    @staticmethod
    def _to_snapshot(payload: Any) -> QuoteSnapshot:
        if not isinstance(payload, dict):
            raise UpstreamServiceError("quote-service", "quote response was not an object")
        try:
            line_items = tuple(
                HttpQuoteReader._to_line_item(raw)
                for raw in payload.get("line_items", [])
            )
            return QuoteSnapshot(
                quote_id=UUID(str(payload["id"])),
                trade_hint=_infer_trade_hint(payload.get("title")),
                currency=str(payload.get("currency", "USD")),
                tax_rate_bps=int(payload.get("tax_rate_bps", 0)),
                subtotal_minor=int(payload.get("subtotal_minor", 0)),
                tax_minor=int(payload.get("tax_minor", 0)),
                total_minor=int(payload.get("total_minor", 0)),
                line_items=line_items,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise UpstreamServiceError(
                "quote-service", f"quote response was unusable: {exc}"
            ) from exc

    @staticmethod
    def _to_line_item(raw: Any) -> QuoteLineItem:
        return QuoteLineItem(
            id=UUID(str(raw["id"])),
            kind=str(raw["kind"]),
            description=str(raw["description"]),
            quantity=normalize_quantity(raw["quantity"]),
            unit=str(raw.get("unit") or "each"),
            unit_cost_minor=int(raw["unit_cost_minor"]),
            markup_bps=int(raw["markup_bps"]),
            unit_price_minor=int(raw["unit_price_minor"]),
            line_total_minor=int(raw["line_total_minor"]),
            pricebook_item_id=(
                UUID(str(raw["pricebook_item_id"]))
                if raw.get("pricebook_item_id")
                else None
            ),
            is_optional=bool(raw.get("is_optional", False)),
        )
