"""Unit tests for quote-service analytics event dispatching & trade inference."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import httpx

from app.domain.trade_inference import infer_trade
from app.interface.routes import _emit_analytics_event


def test_infer_trade_keyword_matching():
    assert infer_trade("200A Electrical Panel Upgrade") == "electrical"
    assert infer_trade("Fix Plumbing Pipe Leak") == "plumbing"
    assert infer_trade("New HVAC Furnace Installation") == "hvac"
    assert infer_trade("Solar Inverter Replacement") == "solar"
    assert infer_trade("Roofing Shingle Repair") == "roofing"
    assert infer_trade("Hardwood Flooring") == "flooring"
    assert infer_trade("Custom Cabinet") == "general"


def test_infer_trade_line_item_fallback():
    assert infer_trade("Service Job", ["Replace Romex wiring and 15A outlet"]) == "electrical"
    assert infer_trade(None, ["Repair leaking faucet"]) == "plumbing"
    assert infer_trade(None, None) == "general"


def test_emit_analytics_event_swallows_all_exceptions():
    tenant_id = uuid.uuid4()
    quote_id = uuid.uuid4()
    customer_id = uuid.uuid4()

    # Mock httpx.post to raise InvalidURL (which does not inherit from httpx.HTTPError)
    with patch("httpx.post", side_effect=httpx.InvalidURL("Invalid URL format")):
        # Must not raise an exception
        _emit_analytics_event(
            tenant_id=tenant_id,
            quote_id=quote_id,
            customer_id=customer_id,
            event_type="quote.quote.created",
            trade="electrical",
            amount_minor=150000,
            customer_name="Acme Corp",
        )

    # Mock httpx.post to raise generic Exception
    with patch("httpx.post", side_effect=RuntimeError("Connection failed")):
        _emit_analytics_event(
            tenant_id=tenant_id,
            quote_id=quote_id,
            customer_id=customer_id,
            event_type="quote.quote.created",
            trade="electrical",
            amount_minor=150000,
        )


def test_emit_analytics_event_successful_payload():
    tenant_id = uuid.uuid4()
    quote_id = uuid.uuid4()
    customer_id = uuid.uuid4()

    with patch("httpx.post") as mock_post:
        _emit_analytics_event(
            tenant_id=tenant_id,
            quote_id=quote_id,
            customer_id=customer_id,
            event_type="quote.estimate.accepted",
            trade="hvac",
            amount_minor=250000,
            customer_name="Jane Doe",
        )

        assert mock_post.called
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["json"]["quote_id"] == str(quote_id)
        assert call_kwargs["json"]["customer_id"] == str(customer_id)
        assert call_kwargs["json"]["customer_name"] == "Jane Doe"
        assert call_kwargs["json"]["event_type"] == "quote.estimate.accepted"
        assert call_kwargs["json"]["trade"] == "hvac"
        assert call_kwargs["json"]["amount_minor"] == 250000
