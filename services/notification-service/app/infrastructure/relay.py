"""Outbox relay — polls unprocessed events and marks them as processed.

For MVP this logs each event; a future version will publish to Redis Streams
(see docs/03-DOMAIN-EVENTS.md).
"""

from __future__ import annotations

import asyncio
import logging

from app.config import settings
from app.infrastructure.db import admin_session
from app.infrastructure.repositories import SqlAlchemyOutboxRepository

logger = logging.getLogger(__name__)


class OutboxRelay:
    def __init__(
        self,
        batch_size: int = settings.outbox_relay_batch_size,
        interval_seconds: float = settings.outbox_relay_interval_seconds,
    ) -> None:
        self._batch_size = batch_size
        self._interval = interval_seconds

    def poll_and_publish(self) -> int:
        """Process one batch of unprocessed events. Returns count processed."""
        with admin_session() as session:
            repo = SqlAlchemyOutboxRepository(session)
            events = repo.fetch_unprocessed(limit=self._batch_size)
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
            repo.mark_processed([e.event_id for e in events])
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
