"""HttpQuoteReader — JSON→domain mapping and error translation.

The ServiceClient is faked: HttpQuoteReader only calls `.request(...)`, so a
tiny stub that returns a canned body (or raises) exercises it with no network.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest

from app.domain.errors import QuoteNotFoundError, UpstreamServiceError
from app.infrastructure.quote_reader import HttpQuoteReader, _infer_trade_hint

QUOTE_ID = str(uuid.uuid4())
LINE_ID = str(uuid.uuid4())
PB_ID = str(uuid.uuid4())


def _quote_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "id": QUOTE_ID,
        "title": "200A Panel Upgrade",
        "currency": "USD",
        "tax_rate_bps": 875,
        "subtotal_minor": 104_000,
        "tax_minor": 9_100,
        "total_minor": 113_100,
        "line_items": [
            {
                "id": LINE_ID,
                "kind": "material",
                "description": "200A main breaker panel",
                "quantity": 1.0,
                "unit": "each",
                "unit_cost_minor": 80_000,
                "markup_bps": 3000,
                "unit_price_minor": 104_000,
                "line_total_minor": 104_000,
                "pricebook_item_id": PB_ID,
                "is_optional": False,
            }
        ],
    }
    payload.update(overrides)
    return payload


class _StubClient:
    def __init__(self, *, body: Any = None, error: Exception | None = None):
        self._body = body
        self._error = error
        self.calls: list[tuple[str, str]] = []

    def request(self, method: str, path: str, **_kwargs: Any) -> Any:
        self.calls.append((method, path))
        if self._error is not None:
            raise self._error
        return self._body


def test_maps_quote_response_to_snapshot() -> None:
    reader = HttpQuoteReader(_StubClient(body=_quote_payload()))

    snap = reader.get_quote(uuid.uuid4(), uuid.uuid4(), uuid.UUID(QUOTE_ID))

    assert str(snap.quote_id) == QUOTE_ID
    assert snap.trade_hint == "electrical"  # inferred from "Panel" in the title
    assert snap.subtotal_minor == 104_000
    assert len(snap.line_items) == 1
    item = snap.line_items[0]
    assert item.quantity == Decimal(1)
    assert isinstance(item.quantity, Decimal)  # not float — money safety
    assert item.unit_cost_minor == 80_000
    assert str(item.pricebook_item_id) == PB_ID


def test_get_uses_the_right_path() -> None:
    client = _StubClient(body=_quote_payload())
    reader = HttpQuoteReader(client)
    reader.get_quote(uuid.uuid4(), None, uuid.UUID(QUOTE_ID))
    assert client.calls == [("GET", f"/v1/quotes/{QUOTE_ID}")]


def test_404_becomes_quote_not_found() -> None:
    error = UpstreamServiceError("quote-service", "HTTP 404", status_code=404)
    reader = HttpQuoteReader(_StubClient(error=error))

    with pytest.raises(QuoteNotFoundError):
        reader.get_quote(uuid.uuid4(), None, uuid.uuid4())


def test_non_404_upstream_error_propagates() -> None:
    error = UpstreamServiceError("quote-service", "HTTP 502", status_code=502)
    reader = HttpQuoteReader(_StubClient(error=error))

    with pytest.raises(UpstreamServiceError):
        reader.get_quote(uuid.uuid4(), None, uuid.uuid4())


def test_malformed_body_raises_upstream_error() -> None:
    reader = HttpQuoteReader(_StubClient(body={"id": QUOTE_ID, "line_items": [{"bad": 1}]}))
    with pytest.raises(UpstreamServiceError):
        reader.get_quote(uuid.uuid4(), None, uuid.UUID(QUOTE_ID))


def test_quote_with_no_line_items_maps_cleanly() -> None:
    reader = HttpQuoteReader(_StubClient(body=_quote_payload(line_items=[])))
    snap = reader.get_quote(uuid.uuid4(), None, uuid.UUID(QUOTE_ID))
    assert snap.line_items == ()


def test_trade_hint_inference() -> None:
    assert _infer_trade_hint("Kitchen plumbing rough-in") == "plumbing"
    assert _infer_trade_hint("HVAC replacement") == "hvac"
    assert _infer_trade_hint("Solar array install") == "solar"
    assert _infer_trade_hint("Quote 1042") is None
    assert _infer_trade_hint(None) is None
