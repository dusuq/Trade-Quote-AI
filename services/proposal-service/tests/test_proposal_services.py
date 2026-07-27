"""Tests for proposal create/send/view use cases (T203 / M8)."""

from __future__ import annotations

import uuid

import pytest

from app.application import proposal_services, template_services
from app.domain.errors import ProposalNotFoundError
from app.domain.proposal import ProposalStatus
from app.infrastructure.models import ProposalModel
from app.interface.schemas import (
    CompanyBrandingDto,
    CustomerInfoDto,
    LineItemDto,
    MoneyDto,
    ProposalCreate,
    TemplateCreate,
)
from tests.fakes import FakePdfStorage


def _make_template(db_session, tenant_id):
    return template_services.create_template(
        db_session,
        tenant_id,
        TemplateCreate(name="Standard", company_name="Bright Sparks Electric", is_default=True),
    )


def _create_payload(template_id) -> ProposalCreate:
    return ProposalCreate(
        quote_id=uuid.uuid4(),
        template_id=template_id,
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


def test_create_proposal_renders_v1_and_persists(db_session, tenant_id):
    template = _make_template(db_session, tenant_id)
    storage = FakePdfStorage()

    proposal, events = proposal_services.create_proposal(
        db_session, storage, tenant_id, _create_payload(template.id)
    )

    assert proposal.id is not None
    assert proposal.number.startswith("P-")
    assert proposal.status == ProposalStatus.DRAFT
    assert proposal.current_version == 1
    assert proposal.storage_key == f"proposals/{proposal.id}.pdf"
    assert len(storage.read(tenant_id, proposal.storage_key)) > 0

    versions = proposal_services.list_versions(db_session, tenant_id, proposal.id)
    assert len(versions) == 1
    assert versions[0].version == 1
    assert versions[0].snapshot["customer"]["display_name"] == "Jordan Rivera"

    event_names = {e.event_name for e in events}
    assert event_names == {"proposal.document.generated", "proposal.document.pdfRendered"}


def test_send_proposal_transitions_status(db_session, tenant_id):
    template = _make_template(db_session, tenant_id)
    storage = FakePdfStorage()
    proposal, _ = proposal_services.create_proposal(
        db_session, storage, tenant_id, _create_payload(template.id)
    )

    sent, event = proposal_services.send_proposal(db_session, tenant_id, proposal.id, channel="email")

    assert sent.status == ProposalStatus.SENT
    assert sent.sent_at is not None
    assert event.event_name == "proposal.document.sent"


def test_send_unknown_proposal_raises(db_session, tenant_id):
    with pytest.raises(ProposalNotFoundError):
        proposal_services.send_proposal(db_session, tenant_id, uuid.uuid4(), channel="email")


def test_mark_viewed_transitions_status_and_emits_once(db_session, tenant_id):
    template = _make_template(db_session, tenant_id)
    storage = FakePdfStorage()
    proposal, _ = proposal_services.create_proposal(
        db_session, storage, tenant_id, _create_payload(template.id)
    )
    proposal_services.send_proposal(db_session, tenant_id, proposal.id, channel="email")

    pdf_bytes, event = proposal_services.mark_viewed_and_fetch_pdf(
        db_session, storage, tenant_id, proposal.id
    )
    assert len(pdf_bytes) > 0
    assert event is not None
    assert event.event_name == "proposal.document.viewed"

    reloaded = db_session.get(ProposalModel, proposal.id)
    assert reloaded.status == ProposalStatus.VIEWED
    first_viewed_at = reloaded.viewed_at
    assert first_viewed_at is not None

    # Second view: status stays VIEWED, viewed_at does not re-stamp, no event.
    _pdf_bytes_2, event_2 = proposal_services.mark_viewed_and_fetch_pdf(
        db_session, storage, tenant_id, proposal.id
    )
    assert event_2 is None
    reloaded_again = db_session.get(ProposalModel, proposal.id)
    assert reloaded_again.viewed_at == first_viewed_at


def test_list_proposals_scopes_tenant_and_filters_by_quote_id_and_status(db_session, tenant_id):
    template = _make_template(db_session, tenant_id)
    storage = FakePdfStorage()

    payload_a = _create_payload(template.id)
    proposal_a, _ = proposal_services.create_proposal(db_session, storage, tenant_id, payload_a)

    payload_b = _create_payload(template.id)
    proposal_b, _ = proposal_services.create_proposal(db_session, storage, tenant_id, payload_b)
    proposal_services.send_proposal(db_session, tenant_id, proposal_b.id, channel="email")

    other_tenant_id = uuid.uuid4()
    other_template = _make_template(db_session, other_tenant_id)
    proposal_services.create_proposal(
        db_session, storage, other_tenant_id, _create_payload(other_template.id)
    )

    # Tenant scoping: other tenant's proposal must never appear.
    all_for_tenant = proposal_services.list_proposals(db_session, tenant_id)
    assert {p.id for p in all_for_tenant} == {proposal_a.id, proposal_b.id}

    # Filter by quote_id.
    by_quote = proposal_services.list_proposals(db_session, tenant_id, quote_id=payload_a.quote_id)
    assert [p.id for p in by_quote] == [proposal_a.id]

    # Filter by status.
    by_status = proposal_services.list_proposals(
        db_session, tenant_id, status=ProposalStatus.SENT
    )
    assert [p.id for p in by_status] == [proposal_b.id]
