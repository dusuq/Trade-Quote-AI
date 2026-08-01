"""Outbox relay unit tests."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import patch

from sqlalchemy.orm import Session, sessionmaker

from app.domain.events import message_sent
from app.infrastructure.models import OutboxEventORM
from app.infrastructure.relay import OutboxRelay
from app.infrastructure.repositories import SqlAlchemyOutboxRepository


def _seed_event(session: Session, tenant_id: uuid.UUID) -> OutboxEventORM:
    repo = SqlAlchemyOutboxRepository(session)
    event = message_sent(
        tenant_id,
        notification_id=uuid.uuid4(),
        channel="email",
        template="quote_delivery",
        to_redacted="j***e@domain.com",
    )
    repo.add(event)
    session.flush()
    row = session.get(OutboxEventORM, event.event_id)
    assert row is not None
    return row


def test_relay_processes_unprocessed_events(engine) -> None:
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    tenant_id = uuid.uuid4()
    row = _seed_event(session, tenant_id)
    assert row.processed_at is None

    @contextmanager
    def _admin() -> Iterator[Session]:
        yield session

    with patch("app.infrastructure.relay.admin_session", _admin):
        relay = OutboxRelay(batch_size=10, interval_seconds=1.0)
        count = relay.poll_and_publish()

    assert count == 1
    session.refresh(row)
    assert row.processed_at is not None

    session.rollback()
    session.close()


def test_relay_is_idempotent(engine) -> None:
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    tenant_id = uuid.uuid4()
    _seed_event(session, tenant_id)

    @contextmanager
    def _admin() -> Iterator[Session]:
        yield session

    with patch("app.infrastructure.relay.admin_session", _admin):
        relay = OutboxRelay(batch_size=10, interval_seconds=1.0)
        first = relay.poll_and_publish()
        second = relay.poll_and_publish()

    assert first == 1
    assert second == 0

    session.rollback()
    session.close()


def test_relay_disabled_by_default() -> None:
    from app.config import settings

    assert settings.outbox_relay_enabled is False
