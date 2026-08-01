"""Cross-tenant outbox reads for the relay, via SECURITY DEFINER functions.

Why this exists rather than a plain `SELECT`: `outbox_event` is under RLS with
`USING (tenant_id = app_current_tenant())`, and the relay has no tenant
context. `app_current_tenant()` returns NULL when the GUC is unset, so
`tenant_id = NULL` is never TRUE and a direct query returns **zero rows,
silently** — the T205b defect. Opening a session without setting the GUC does
not grant a bypass; only a definer function (or a BYPASSRLS role, which would
be a far broader grant) does.

The two functions live in `0012_notification_outbox_relay.sql`. They are
Postgres-only, so this class cannot run under the SQLite test harness — the
same standing limitation as esign-service's `PostgresTenantResolver`, and the
reason the port exists.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domain.events import DomainEvent, NotificationEventName


class PostgresOutboxRelayStore:
    def __init__(self, session: Session) -> None:
        self.session = session

    def claim_unprocessed(self, limit: int) -> list[DomainEvent]:
        rows = self.session.execute(
            text("SELECT * FROM outbox_claim_unprocessed(:limit)"), {"limit": limit}
        ).mappings()
        return [
            DomainEvent(
                # The registry is a Literal type; the column is free text. Only
                # this service writes the table, so the cast is safe — but it is
                # a cast, not a validation, and is called out rather than hidden.
                event_name=cast(NotificationEventName, row["event_name"]),
                tenant_id=row["tenant_id"],
                payload=row["payload"],
                actor_id=row["actor_id"],
                event_version=row["event_version"],
                event_id=row["event_id"],
                occurred_at=row["occurred_at"],
                correlation_id=row["correlation_id"],
                causation_id=row["causation_id"],
            )
            for row in rows
        ]

    def mark_processed(self, event_ids: Sequence[UUID]) -> int:
        if not event_ids:
            return 0
        marked = self.session.execute(
            text("SELECT outbox_mark_processed(:ids)"), {"ids": list(event_ids)}
        ).scalar_one()
        return int(marked)
