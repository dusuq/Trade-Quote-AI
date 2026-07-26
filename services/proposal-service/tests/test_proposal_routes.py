"""Route-level tests for the Proposal Builder (T203 / M8), including the
public /view route — the one route in this codebase with no auth header."""

from __future__ import annotations

import uuid

from app.application import proposal_services, template_services
from app.interface import proposal_routes
from app.interface.schemas import (
    CompanyBrandingDto,
    CustomerInfoDto,
    LineItemDto,
    MoneyDto,
    ProposalCreate,
    TemplateCreate,
)
from tests.fakes import FakePdfStorage, FakeTenantResolver


def _create_via_services(db_session, tenant_id, storage):
    template = template_services.create_template(
        db_session,
        tenant_id,
        TemplateCreate(name="Standard", company_name="Bright Sparks Electric", is_default=True),
    )
    payload = ProposalCreate(
        quote_id=uuid.uuid4(),
        template_id=template.id,
        branding=CompanyBrandingDto(company_name="Bright Sparks Electric"),
        customer=CustomerInfoDto(display_name="Jordan Rivera"),
        line_items=[
            LineItemDto(
                description="Replace 200A panel",
                quantity=1,
                unit="each",
                unit_price=MoneyDto(amount_minor=85000),
                line_total=MoneyDto(amount_minor=85000),
            )
        ],
        subtotal=MoneyDto(amount_minor=85000),
        tax=MoneyDto(amount_minor=0),
        total=MoneyDto(amount_minor=85000),
        scope_of_work="Replace the main electrical panel.",
    )
    proposal, _events = proposal_services.create_proposal(db_session, storage, tenant_id, payload)
    proposal_services.send_proposal(db_session, tenant_id, proposal.id, channel="email")
    return proposal


def test_view_route_succeeds_with_no_tenant_header(client, monkeypatch, db_session, tenant_id):
    """The critical guarantee of D4: no x-tenant-id, no bearer token — just
    the proposal id in the URL — must still work."""
    storage = FakePdfStorage()
    proposal = _create_via_services(db_session, tenant_id, storage)

    monkeypatch.setattr(proposal_routes, "_storage", storage)
    monkeypatch.setattr(
        proposal_routes, "_tenant_resolver", FakeTenantResolver({proposal.id: tenant_id})
    )
    monkeypatch.setattr(
        "app.infrastructure.db.SessionLocal", lambda: db_session, raising=False
    )

    response = client.get(f"/v1/proposals/{proposal.id}/view")
    # No Authorization header, no x-tenant-id header, at all.
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"


def test_view_route_unknown_proposal_returns_404(client, monkeypatch):
    monkeypatch.setattr(proposal_routes, "_tenant_resolver", FakeTenantResolver({}))
    response = client.get(f"/v1/proposals/{uuid.uuid4()}/view")
    assert response.status_code == 404
