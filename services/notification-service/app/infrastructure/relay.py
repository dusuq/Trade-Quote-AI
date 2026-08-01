"""Outbox relay — claims unprocessed events and marks them published.

For MVP this logs each event; a future version will publish to Redis Streams
(see docs/03-DOMAIN-EVENTS.md).

The relay reads across every tenant, which RLS forbids by default. It goes
through `OutboxRelayStore` — backed in production by SECURITY DEFINER
functions — rather than by opening an un-scoped session, because an un-scoped
session sees nothing at all (see `outbox_relay_store.py`).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import AbstractContextManager

from sqlalchemy.orm import Session

from app.config import settings
from app.domain.protocols import OutboxRelayStore
from app.infrastructure.db import relay_session
from app.infrastructure.outbox_relay_store import PostgresOutboxRelayStore

logger = logging.getLogger(__name__)

SessionScope = Callable[[], AbstractContextManager[Session]]
StoreFactory = Callable[[Session], OutboxRelayStore]


class OutboxRelay:
    def __init__(
        self,
        batch_size: int = settings.outbox_relay_batch_size,
        interval_seconds: float = settings.outbox_relay_interval_seconds,
        *,
        session_scope: SessionScope = relay_session,
        store_factory: StoreFactory = PostgresOutboxRelayStore,
    ) -> None:
        self._batch_size = batch_size
        self._interval = interval_seconds
        self._session_scope = session_scope
        self._store_factory = store_factory

    def poll_and_publish(self) -> int:
        """Process one batch. Returns the number of events published.

        Claim and mark happen in one transaction: the rows are locked by
        `FOR UPDATE SKIP LOCKED` until it commits, so a second replica polling
        concurrently takes a different batch instead of republishing this one.
        """
        with self._session_scope() as session:
            store = self._store_factory(session)
            events = store.claim_unprocessed(self._batch_size)
            if not events:
                return 0
            for event in events:
                logger.info(
                    "outbox.published",
                    extra={
                        "event_name": event.event_name,
                        "event_id": str(event.event_id),
                        "tenant_id": str(event.tenant_id),
                    },
                )
            marked = store.mark_processed([e.event_id for e in events])
            if marked != len(events):
                # Should be impossible while we hold the row locks. If it ever
                # happens, something else is marking rows and at-least-once has
                # quietly become at-most-once for the difference.
                logger.warning(
                    "outbox.mark_mismatch", extra={"claimed": len(events), "marked": marked}
                )
        return len(events)

    async def run_forever(self) -> None:
        """Background loop — call from FastAPI lifespan."""
        logger.info("outbox relay started (interval=%.1fs)", self._interval)
        try:
            while True:
                try:
                    self.poll_and_publish()
                except Exception:
                    logger.exception("outbox relay poll failed")
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            logger.info("outbox relay stopped")
