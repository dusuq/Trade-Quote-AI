"""Tamper-evidence tests for the audit hash chain (M10 / T204).

These are the tests that make the audit trail worth having: each one is a
concrete tampering attempt that verification must catch.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.domain.entities import AuditEvent
from app.domain.hash_chain import (
    GENESIS_HASH,
    compute_entry_hash,
    compute_signature_hash,
    verify_chain,
)

TENANT = uuid.uuid4()
BASE_TIME = datetime(2026, 7, 28, 12, 0, 0, tzinfo=UTC)


def build_chain(request_id: uuid.UUID, count: int = 3) -> list[AuditEvent]:
    """A correctly-linked chain, built the same way the service builds one."""
    entries: list[AuditEvent] = []
    prev_hash = GENESIS_HASH
    for index in range(count):
        sequence = index + 1
        occurred_at = BASE_TIME + timedelta(minutes=index)
        event_type = f"event.{sequence}"
        payload = {"step": sequence}
        entry_hash = compute_entry_hash(
            request_id=request_id,
            sequence=sequence,
            event_type=event_type,
            payload=payload,
            occurred_at=occurred_at,
            prev_hash=prev_hash,
        )
        entries.append(
            AuditEvent(
                id=uuid.uuid4(),
                tenant_id=TENANT,
                request_id=request_id,
                sequence=sequence,
                event_type=event_type,
                payload=payload,
                occurred_at=occurred_at,
                prev_hash=prev_hash,
                entry_hash=entry_hash,
            )
        )
        prev_hash = entry_hash
    return entries


def test_intact_chain_verifies() -> None:
    result = verify_chain(build_chain(uuid.uuid4()))
    assert result.is_valid
    assert result.entry_count == 3
    assert result.broken_at_sequence is None


def test_empty_chain_is_vacuously_valid() -> None:
    result = verify_chain([])
    assert result.is_valid
    assert result.entry_count == 0


def test_detects_mutated_payload() -> None:
    """The headline case: someone edits what an audit entry says happened."""
    entries = build_chain(uuid.uuid4())
    entries[1].payload = {"step": 2, "ip_address": "10.0.0.99"}

    result = verify_chain(entries)

    assert not result.is_valid
    assert result.broken_at_sequence == 2
    assert "content mutated" in (result.reason or "")


def test_detects_mutated_event_type() -> None:
    entries = build_chain(uuid.uuid4())
    entries[2].event_type = "request.declined"

    result = verify_chain(entries)

    assert not result.is_valid
    assert result.broken_at_sequence == 3


def test_detects_mutated_timestamp() -> None:
    """When something happened is as load-bearing as what happened."""
    entries = build_chain(uuid.uuid4())
    entries[0].occurred_at = BASE_TIME - timedelta(days=30)

    result = verify_chain(entries)

    assert not result.is_valid
    assert result.broken_at_sequence == 1


def test_detects_deleted_middle_entry() -> None:
    """Deleting an inconvenient entry leaves a sequence gap."""
    entries = build_chain(uuid.uuid4(), count=4)
    del entries[1]

    result = verify_chain(entries)

    assert not result.is_valid
    assert result.broken_at_sequence == 2
    assert "missing" in (result.reason or "")


def test_detects_reordered_entries() -> None:
    """Swapping two entries' positions breaks the prev_hash linkage."""
    entries = build_chain(uuid.uuid4())
    entries[1].sequence, entries[2].sequence = 3, 2

    result = verify_chain(entries)

    assert not result.is_valid
    assert result.broken_at_sequence == 2
    assert "broken link" in (result.reason or "")


def test_detects_forged_entry_appended_to_the_end() -> None:
    """An attacker appending a fabricated 'they signed it' entry."""
    request_id = uuid.uuid4()
    entries = build_chain(request_id)
    forged_payload = {"signature_hash": "deadbeef"}
    occurred_at = BASE_TIME + timedelta(hours=1)
    entries.append(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=TENANT,
            request_id=request_id,
            sequence=4,
            event_type="signature.applied",
            payload=forged_payload,
            occurred_at=occurred_at,
            # The forger controls this entry's own hash but cannot produce a
            # prev_hash that matches the real entry 3 without also rewriting it.
            prev_hash=GENESIS_HASH,
            entry_hash=compute_entry_hash(
                request_id=request_id,
                sequence=4,
                event_type="signature.applied",
                payload=forged_payload,
                occurred_at=occurred_at,
                prev_hash=GENESIS_HASH,
            ),
        )
    )

    result = verify_chain(entries)

    assert not result.is_valid
    assert result.broken_at_sequence == 4
    assert "broken link" in (result.reason or "")


def test_detects_tampered_genesis() -> None:
    entries = build_chain(uuid.uuid4())
    entries[0].prev_hash = "f" * 64

    result = verify_chain(entries)

    assert not result.is_valid
    assert result.broken_at_sequence == 1


def test_detects_entry_spliced_in_from_another_signature_request() -> None:
    """`request_id` is inside the hashed material precisely to stop this.

    A genuine, internally-valid entry lifted from another request — with its
    visible linkage (sequence, prev_hash) fixed up to fit — still fails,
    because its stored hash was computed over a different request_id.
    """
    victim_id = uuid.uuid4()
    victim = build_chain(victim_id, count=2)
    donor = build_chain(uuid.uuid4(), count=2)

    stolen = donor[1]
    stolen.sequence = 2
    stolen.prev_hash = victim[0].entry_hash
    spliced = [victim[0], stolen]

    result = verify_chain(spliced)

    assert not result.is_valid
    assert result.broken_at_sequence == 2
    assert "content mutated" in (result.reason or "")


def test_hash_is_independent_of_payload_key_order() -> None:
    """Canonical encoding must sort keys, or verification would fail on an
    untampered chain purely because a dict was rebuilt in another order."""
    request_id = uuid.uuid4()
    common = {
        "request_id": request_id,
        "sequence": 1,
        "event_type": "request.created",
        "occurred_at": BASE_TIME,
        "prev_hash": GENESIS_HASH,
    }
    first = compute_entry_hash(payload={"a": 1, "b": 2}, **common)
    second = compute_entry_hash(payload={"b": 2, "a": 1}, **common)

    assert first == second


def test_full_rechain_passes_documenting_the_limit_of_a_self_contained_chain() -> None:
    """Honest boundary of this mechanism.

    A hash chain proves *internal consistency*, not authenticity. An attacker
    with write access to every row can mutate an entry and recompute the
    entire tail, and verification will pass. Defending against that requires
    something outside the chain — append-only grants, WORM storage, or
    anchoring the head hash somewhere the attacker doesn't control. That is
    an operational control, tracked in docs/modules/M10-esignature.md, not
    something this module can solve. This test exists so nobody mistakes the
    guarantee for more than it is.
    """
    request_id = uuid.uuid4()
    entries = build_chain(request_id)

    entries[1].payload = {"step": 2, "tampered": True}
    prev_hash = entries[0].entry_hash
    for entry in entries[1:]:
        entry.prev_hash = prev_hash
        entry.entry_hash = compute_entry_hash(
            request_id=entry.request_id,
            sequence=entry.sequence,
            event_type=entry.event_type,
            payload=entry.payload,
            occurred_at=entry.occurred_at,
            prev_hash=prev_hash,
        )
        prev_hash = entry.entry_hash

    assert verify_chain(entries).is_valid


def test_signature_hash_binds_to_the_exact_document() -> None:
    common = {
        "signer_id": uuid.uuid4(),
        "signer_name": "Jordan Rivera",
        "ip_address": "203.0.113.7",
        "signed_at": BASE_TIME,
    }
    against_original = compute_signature_hash(document_sha256="a" * 64, **common)
    against_swapped = compute_signature_hash(document_sha256="b" * 64, **common)

    assert against_original != against_swapped


def test_signature_hash_is_stable_for_identical_inputs() -> None:
    args = {
        "signer_id": uuid.uuid4(),
        "signer_name": "Jordan Rivera",
        "document_sha256": "a" * 64,
        "ip_address": "203.0.113.7",
        "signed_at": BASE_TIME,
    }
    assert compute_signature_hash(**args) == compute_signature_hash(**args)
