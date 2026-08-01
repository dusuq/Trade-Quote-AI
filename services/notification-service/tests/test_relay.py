"""Outbox relay tests.

These drive the relay through its `OutboxRelayStore` port with an in-memory
fake. What they cannot cover is the part that actually broke in T205b: the
SECURITY DEFINER functions and `FOR UPDATE SKIP LOCKED` are Postgres-only and
SQLite has no RLS to get wrong, so a green run here says nothing about whether
the relay can see a row in production. That is exactly why the previous tests
passed while the relay published nothing — they patched out the one function
that was broken. Live verification is tracked as T311b.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager

import pytest

from app.domain.events import DomainEvent, message_sent
from app.infrastructure.relay import OutboxRelay


class FakeOutboxRelayStore:
    """In-memory stand-in for the SECURITY DEFINER-backed store."""

    def __init__(self, events: list[DomainEvent] | None = None) -> None:
        self.events = events or []
        self.processed: set[uuid.UUID] = set()
        self.claims: list[int] = []

    def claim_unprocessed(self, limit: int) -> list[DomainEvent]:
        self.claims.append(limit)
        pending = [e for e in self.events if e.event_id not in self.processed]
        return pending[:limit]

    def mark_processed(self, event_ids: Sequence[uuid.UUID]) -> int:
        fresh = [eid for eid in event_ids if eid not in self.processed]
        self.processed.update(fresh)
        return len(fresh)


def _event() -> DomainEvent:
    return message_sent(
        uuid.uuid4(),
        notification_id=uuid.uuid4(),
        channel="email",
        template="quote_delivery",
        to_redacted="j***e@domain.com",
    )


def _relay(store: FakeOutboxRelayStore, **kwargs) -> OutboxRelay:
    @contextmanager
    def _scope() -> Iterator[None]:
        yield None

    return OutboxRelay(
        session_scope=_scope,
        store_factory=lambda _session: store,
        **kwargs,
    )


def test_relay_publishes_and_marks_claimed_events() -> None:
    store = FakeOutboxRelayStore([_event(), _event()])

    published = _relay(store).poll_and_publish()

    assert published == 2
    assert store.processed == {e.event_id for e in store.events}


def test_relay_does_not_republish() -> None:
    store = FakeOutboxRelayStore([_event()])
    relay = _relay(store)

    assert relay.poll_and_publish() == 1
    assert relay.poll_and_publish() == 0


def test_relay_reports_nothing_to_do_without_marking() -> None:
    store = FakeOutboxRelayStore([])

    assert _relay(store).poll_and_publish() == 0
    assert store.processed == set()


def test_relay_honours_the_batch_size() -> None:
    store = FakeOutboxRelayStore([_event() for _ in range(5)])

    assert _relay(store, batch_size=2).poll_and_publish() == 2
    assert store.claims == [2]


def test_relay_warns_when_it_marks_fewer_than_it_claimed(caplog: pytest.LogCaptureFixture) -> None:
    """Impossible while the row locks are held — so if it ever happens, the
    at-least-once guarantee has quietly become at-most-once and it must be
    loud rather than inferred from a count later."""
    class RacingStore(FakeOutboxRelayStore):
        """Claims two, but only one is still unmarked by the time we write —
        i.e. something outside our row locks marked it in between."""

        def mark_processed(self, event_ids: Sequence[uuid.UUID]) -> int:
            super().mark_processed(event_ids)
            return len(event_ids) - 1

    store = RacingStore([_event(), _event()])

    with caplog.at_level("WARNING"):
        assert _relay(store).poll_and_publish() == 2

    assert any(record.message == "outbox.mark_mismatch" for record in caplog.records)


def test_relay_disabled_by_default() -> None:
    from app.config import settings

    assert settings.outbox_relay_enabled is False
