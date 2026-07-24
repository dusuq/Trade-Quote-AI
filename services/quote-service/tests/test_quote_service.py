"""Unit and integration tests for quote-service domain logic & REST API."""

from __future__ import annotations

from app.application import services
from app.domain.models import ItemKind, QuoteStatus
from app.interface.schemas import LineItemCreate, QuoteCreate


def test_create_quote_with_initial_line_items(db_session, tenant_id, customer_id):
    quote_in = QuoteCreate(
        customer_id=customer_id,
        title="200A Electrical Panel Upgrade",
        tax_rate_bps=875,  # 8.75% tax
        initial_line_items=[
            LineItemCreate(
                kind=ItemKind.MATERIAL,
                description="200A Main Breaker Panel",
                quantity=1,
                unit_cost_minor=15000,  # $150.00
                markup_bps=3000,  # 30% markup -> $195.00 (19500 minor)
            ),
            LineItemCreate(
                kind=ItemKind.LABOR,
                description="Journeyman Labor",
                quantity=6.5,
                unit_cost_minor=6000,  # $60/hr
                markup_bps=2500,  # 25% markup -> $75/hr (7500 minor)
            ),
        ],
    )

    quote, event = services.create_quote(db_session, tenant_id, quote_in)

    assert quote.id is not None
    assert quote.number.startswith("Q-")
    assert quote.status == QuoteStatus.DRAFT
    assert len(quote.line_items) == 2

    # Line item 1: 1 * 19500 = 19500
    # Line item 2: 6.5 * 7500 = 48750
    # Subtotal: 19500 + 48750 = 68250 ($682.50)
    # Tax (8.75%): 68250 * 0.0875 = 5971.875 -> 5972 minor ($59.72)
    # Total: 68250 + 5972 = 74222 ($742.22)
    assert quote.subtotal_minor == 68250
    assert quote.tax_minor == 5972
    assert quote.total_minor == 74222

    # Verify event structure
    assert event["eventName"] == "quote.quote.created"
    assert event["payload"]["quoteId"] == str(quote.id)


def test_optional_line_items_excluded_from_subtotal(db_session, tenant_id, customer_id):
    quote_in = QuoteCreate(
        customer_id=customer_id,
        title="HVAC Maintenance",
        tax_rate_bps=0,
        initial_line_items=[
            LineItemCreate(
                kind=ItemKind.LABOR,
                description="AC Tune Up Base",
                quantity=1,
                unit_price_minor=12000,
                is_optional=False,
            ),
            LineItemCreate(
                kind=ItemKind.MATERIAL,
                description="Optional Surge Protector",
                quantity=1,
                unit_price_minor=18000,
                is_optional=True,
            ),
        ],
    )

    quote, _ = services.create_quote(db_session, tenant_id, quote_in)

    # Subtotal should only include non-optional item ($120.00)
    assert quote.subtotal_minor == 12000
    assert quote.total_minor == 12000


def test_add_and_delete_line_items(db_session, tenant_id, customer_id):
    quote, _ = services.create_quote(
        db_session,
        tenant_id,
        QuoteCreate(customer_id=customer_id, title="Plumbing Repair"),
    )

    # Add line item
    line1, event1 = services.add_line_item(
        db_session,
        tenant_id,
        quote.id,
        LineItemCreate(description="Pipe Replacement", quantity=2, unit_price_minor=5000),
    )
    assert quote.subtotal_minor == 10000
    assert event1["eventName"] == "quote.quote.lineItemsChanged"

    # Add second line item
    _line2, _ = services.add_line_item(
        db_session,
        tenant_id,
        quote.id,
        LineItemCreate(description="Shutoff Valve", quantity=1, unit_price_minor=3500),
    )
    assert quote.subtotal_minor == 13500

    # Delete first line item
    event2 = services.delete_line_item(db_session, tenant_id, quote.id, line1.id)
    assert quote.subtotal_minor == 3500
    assert event2["eventName"] == "quote.quote.lineItemsChanged"


def test_send_quote_creates_immutable_version(db_session, tenant_id, customer_id):
    quote, _ = services.create_quote(
        db_session,
        tenant_id,
        QuoteCreate(
            customer_id=customer_id,
            title="Roofing Estimate",
            initial_line_items=[
                LineItemCreate(description="Shingles", quantity=10, unit_price_minor=4000)
            ],
        ),
    )

    assert quote.status == QuoteStatus.DRAFT
    assert quote.current_version == 1

    # Send quote
    sent_quote, sent_event = services.send_quote(db_session, tenant_id, quote.id, channel="email")

    assert sent_quote.status == QuoteStatus.SENT
    assert sent_quote.current_version == 2  # Incremented for subsequent edits
    assert sent_event["eventName"] == "quote.quote.sent"
    assert sent_event["payload"]["channel"] == "email"

    # Verify version snapshot recorded in quote_version table
    versions = services.list_quote_versions(db_session, tenant_id, quote.id)
    assert len(versions) == 1
    assert versions[0].version == 1
    assert versions[0].snapshot["title"] == "Roofing Estimate"
    assert versions[0].snapshot["subtotal_minor"] == 40000


def test_quote_status_lifecycle_accept_and_reject(db_session, tenant_id, customer_id):
    # Test Accept
    quote_acc, _ = services.create_quote(db_session, tenant_id, QuoteCreate(customer_id=customer_id))
    services.send_quote(db_session, tenant_id, quote_acc.id)
    accepted_quote, acc_event = services.accept_quote(db_session, tenant_id, quote_acc.id)

    assert accepted_quote.status == QuoteStatus.ACCEPTED
    assert acc_event["eventName"] == "quote.estimate.accepted"

    # Test Reject
    quote_rej, _ = services.create_quote(db_session, tenant_id, QuoteCreate(customer_id=customer_id))
    services.send_quote(db_session, tenant_id, quote_rej.id)
    rejected_quote, rej_event = services.reject_quote(
        db_session, tenant_id, quote_rej.id, reason="Price too high"
    )

    assert rejected_quote.status == QuoteStatus.REJECTED
    assert rej_event["eventName"] == "quote.estimate.rejected"
    assert rej_event["payload"]["reason"] == "Price too high"
