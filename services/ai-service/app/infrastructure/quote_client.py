"""Quote creation over HTTP (ADR-0003 — this call *is* the deliverable)."""

from __future__ import annotations

from uuid import UUID

from app.domain.errors import UpstreamServiceError
from app.domain.models import LineItemDraft
from app.infrastructure.http import ServiceClient


class HttpQuoteCreator:
    """Implements `QuoteCreator` against `POST /v1/quotes`."""

    def __init__(self, client: ServiceClient) -> None:
        self._client = client

    def create_quote(
        self,
        tenant_id: UUID,
        user_id: UUID | None,
        *,
        customer_id: UUID,
        property_id: UUID | None,
        title: str,
        created_via: str,
        tax_rate_bps: int,
        line_items: list[LineItemDraft],
    ) -> UUID:
        body = {
            "customer_id": str(customer_id),
            "property_id": str(property_id) if property_id else None,
            "title": title,
            "created_via": created_via,
            "tax_rate_bps": tax_rate_bps,
            "owner_id": str(user_id) if user_id else None,
            "initial_line_items": [self._line_item(item) for item in line_items],
        }

        payload = self._client.request(
            "POST", "/v1/quotes", tenant_id=tenant_id, user_id=user_id, json=body
        )

        try:
            return UUID(str(payload["id"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise UpstreamServiceError(
                "quote-service", "create returned no usable quote id"
            ) from exc

    @staticmethod
    def _line_item(item: LineItemDraft) -> dict[str, object]:
        """Map a draft to `LineItemCreate`.

        `unit_price_minor` is deliberately omitted: quote-service derives it
        from `unit_cost_minor` and `markup_bps`, and it should stay the only
        place that arithmetic happens.

        `quantity` is serialized via `str(Decimal)` -> `float` at the JSON
        boundary because the upstream field is a float; the Decimal is what
        kept the value exact everywhere it mattered on our side.
        """
        return {
            "pricebook_item_id": (
                str(item.pricebook_item_id) if item.pricebook_item_id else None
            ),
            "kind": item.kind,
            "description": item.description,
            "quantity": float(item.quantity),
            "unit": item.unit,
            "unit_cost_minor": item.unit_cost_minor,
            "markup_bps": item.markup_bps,
            "is_optional": False,
            "sort_order": item.sort_order,
        }
