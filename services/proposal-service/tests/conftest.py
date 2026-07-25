"""Shared fixtures for proposal-service tests."""

from __future__ import annotations

import uuid

import pytest

from app.domain.entities import (
    CompanyBranding,
    CustomerInfo,
    Money,
    ProposalDocument,
    ProposalLineItem,
)


@pytest.fixture
def sample_document() -> ProposalDocument:
    return ProposalDocument(
        proposal_id=uuid.uuid4(),
        quote_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        branding=CompanyBranding(
            company_name="Bright Sparks Electric",
            primary_color="#1D4ED8",
            phone="(555) 123-4567",
            email="hello@brightsparks.example",
            website="brightsparks.example",
        ),
        customer=CustomerInfo(
            display_name="Jordan Rivera",
            email="jordan@example.com",
            phone="(555) 987-6543",
            property_address="742 Evergreen Terrace, Springfield",
        ),
        line_items=[
            ProposalLineItem(
                description="Replace 200A panel",
                quantity=1,
                unit="each",
                unit_price=Money(85000, "USD"),
                line_total=Money(85000, "USD"),
            ),
            ProposalLineItem(
                description="Install LED recessed lights",
                quantity=12,
                unit="each",
                unit_price=Money(4500, "USD"),
                line_total=Money(54000, "USD"),
            ),
        ],
        subtotal=Money(139000, "USD"),
        tax=Money(12160, "USD"),
        total=Money(151160, "USD"),
        scope_of_work="Replace the main electrical panel and install 12 LED recessed lights "
        "throughout the living room and kitchen.",
        warranty_text="All labor is warrantied for 2 years from the completion date.",
        terms_text="50% deposit due at signing, balance due on completion.",
        valid_until="2026-08-15",
        qr_payload_url="https://tradequote.example/p/view",
    )
