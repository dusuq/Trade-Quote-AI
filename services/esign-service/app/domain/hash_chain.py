"""Tamper-evident hash chain for the signature audit trail (M10 / T204).

Pure domain logic: no I/O, no framework, no database. That is deliberate —
tamper-evidence is the legally load-bearing property of this module, so it
must be provable in CI without infrastructure, not asserted in a README.

Each audit entry commits to the one before it:

    entry_hash_n = sha256(canonical_json({..., prev_hash: entry_hash_{n-1}}))

So mutating, deleting, reordering, or inserting an entry breaks verification
from that point forward, and `verify_chain` reports exactly where.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

# `prev_hash` of the first link. 64 zeros mirrors the shape of a sha256 hex
# digest, so every link — including the first — is verified by the same code
# path with no special case.
GENESIS_HASH = "0" * 64

SEQUENCE_START = 1


def canonical_payload(
    *,
    request_id: UUID,
    sequence: int,
    event_type: str,
    payload: Mapping[str, Any],
    occurred_at: datetime,
    prev_hash: str,
) -> str:
    """Deterministic JSON encoding of one link's hashed material.

    `sort_keys` plus tight separators keep the encoding stable regardless of
    dict insertion order or Python version — without that, a re-verification
    could fail on an untampered chain.

    `request_id` is inside the hashed material on purpose: it stops a valid
    run of entries being spliced out of one signature request and into
    another, which sequence numbers and prev-hashes alone would not catch.
    """
    return json.dumps(
        {
            "request_id": str(request_id),
            "sequence": sequence,
            "event_type": event_type,
            "payload": payload,
            "occurred_at": occurred_at.astimezone(UTC).isoformat(),
            "prev_hash": prev_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def compute_entry_hash(
    *,
    request_id: UUID,
    sequence: int,
    event_type: str,
    payload: Mapping[str, Any],
    occurred_at: datetime,
    prev_hash: str,
) -> str:
    """SHA-256 of this link's canonical material. Hex digest, 64 chars."""
    material = canonical_payload(
        request_id=request_id,
        sequence=sequence,
        event_type=event_type,
        payload=payload,
        occurred_at=occurred_at,
        prev_hash=prev_hash,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def compute_signature_hash(
    *,
    signer_id: UUID,
    signer_name: str,
    document_sha256: str,
    ip_address: str,
    signed_at: datetime,
) -> str:
    """The signature's own fingerprint — what `esign.document.signed` carries
    as `signatureHash`.

    Binds *who* signed to *which exact document* (`document_sha256`) at *what
    moment* from *where*. Any of those changing produces a different hash.
    """
    material = json.dumps(
        {
            "signer_id": str(signer_id),
            "signer_name": signer_name,
            "document_sha256": document_sha256,
            "ip_address": ip_address,
            "signed_at": signed_at.astimezone(UTC).isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(slots=True, frozen=True)
class ChainVerification:
    """Result of verifying an audit chain.

    `broken_at_sequence` is the sequence number where verification first
    failed — the whole point of a chain over a flat log is being able to say
    *where* tampering happened, not just that it did.
    """

    is_valid: bool
    entry_count: int
    broken_at_sequence: int | None = None
    reason: str | None = None


class ChainEntry:
    """Structural shape `verify_chain` needs. Domain `AuditEvent` satisfies it.

    Declared as a plain class rather than a Protocol so this module stays
    importable with zero coupling — verification is called with domain
    entities, never ORM rows (the repository maps rows to entities first).
    """

    request_id: UUID
    sequence: int
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime
    prev_hash: str
    entry_hash: str


def verify_chain(entries: Sequence[Any]) -> ChainVerification:
    """Verify an audit chain end to end.

    Three distinct failure modes, checked in this order because each one
    would otherwise be misreported as the next:

    1. **Sequence gap** — an entry was deleted, or never written.
    2. **Broken link** — `prev_hash` doesn't match the previous entry's hash
       (reordering, or an entry spliced in).
    3. **Content mutation** — the stored hash doesn't match a recomputation
       of the entry's own material.

    An empty chain is vacuously valid: a signature request that has had
    nothing happen to it yet has nothing to falsify.
    """
    if not entries:
        return ChainVerification(is_valid=True, entry_count=0)

    ordered = sorted(entries, key=lambda e: e.sequence)
    expected_prev = GENESIS_HASH

    for index, entry in enumerate(ordered):
        expected_sequence = SEQUENCE_START + index

        if entry.sequence != expected_sequence:
            return ChainVerification(
                is_valid=False,
                entry_count=len(ordered),
                broken_at_sequence=expected_sequence,
                reason=(
                    f"sequence gap: expected {expected_sequence}, found {entry.sequence} "
                    "— an audit entry is missing"
                ),
            )

        if entry.prev_hash != expected_prev:
            return ChainVerification(
                is_valid=False,
                entry_count=len(ordered),
                broken_at_sequence=entry.sequence,
                reason=(
                    f"broken link at sequence {entry.sequence}: prev_hash does not match "
                    "the preceding entry — entries were reordered or one was inserted"
                ),
            )

        recomputed = compute_entry_hash(
            request_id=entry.request_id,
            sequence=entry.sequence,
            event_type=entry.event_type,
            payload=entry.payload,
            occurred_at=entry.occurred_at,
            prev_hash=entry.prev_hash,
        )
        if recomputed != entry.entry_hash:
            return ChainVerification(
                is_valid=False,
                entry_count=len(ordered),
                broken_at_sequence=entry.sequence,
                reason=(
                    f"content mutated at sequence {entry.sequence}: stored hash does not "
                    "match a recomputation of the entry's own contents"
                ),
            )

        expected_prev = entry.entry_hash

    return ChainVerification(is_valid=True, entry_count=len(ordered))
