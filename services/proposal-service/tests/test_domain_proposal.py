"""Tests for the Proposal Builder's domain layer (T203 / M8)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.domain.events import proposal_sent, proposal_viewed
from app.domain.proposal import ProposalStatus


def test_proposal_status_values_are_lowercase():
    # Guards against the exact T206b-class bug: the Python enum's *value*
    # (not .name) must match what the Postgres enum type declares.
    assert ProposalStatus.DRAFT.value == "draft"
    assert ProposalStatus.SENT.value == "sent"
    assert ProposalStatus.VIEWED.value == "viewed"


def test_proposal_sent_event_shape():
    tenant_id = uuid.uuid4()
    proposal_id = uuid.uuid4()
    quote_id = uuid.uuid4()
    event = proposal_sent(tenant_id, proposal_id, quote_id, channel="email")
    assert event.event_name == "proposal.document.sent"
    assert event.payload == {
        "proposalId": str(proposal_id),
        "quoteId": str(quote_id),
        "channel": "email",
    }


def test_proposal_viewed_event_shape():
    tenant_id = uuid.uuid4()
    proposal_id = uuid.uuid4()
    viewed_at = datetime.now(UTC)
    event = proposal_viewed(tenant_id, proposal_id, viewed_at)
    assert event.event_name == "proposal.document.viewed"
    assert event.payload["proposalId"] == str(proposal_id)
    assert event.payload["viewedAt"] == viewed_at.isoformat()
