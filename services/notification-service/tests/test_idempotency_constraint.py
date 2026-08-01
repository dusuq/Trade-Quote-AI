"""The idempotency key's *database* constraint (T205c).

The route's `get_by_idempotency_key` lookup is check-then-insert, so on its own
two concurrent identical requests both miss and both insert. The partial unique
index is what actually closes that race, which makes it worth a test rather
than trusting that the migration and the ORM agree.

Until T205c the ORM declared no index at all, so this was unenforceable under
the SQLite harness and only Postgres would have caught a duplicate. Declaring
the `sqlite_where` variant alongside `postgresql_where` is what lets these run
here.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.infrastructure.models import NotificationMessageORM


def _row(tenant_id: uuid.UUID, key: str | None) -> NotificationMessageORM:
    return NotificationMessageORM(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        channel="email",
        recipient="jane@domain.com",
        to_redacted="j***e@domain.com",
        template_name="quote_delivery",
        subject="Your quote",
        body="hello",
        status="queued",
        idempotency_key=key,
    )


def test_duplicate_key_in_one_tenant_is_rejected(api_session) -> None:
    tenant = uuid.uuid4()
    api_session.add(_row(tenant, "abc-123"))
    api_session.flush()

    api_session.add(_row(tenant, "abc-123"))
    with pytest.raises(IntegrityError):
        api_session.flush()


def test_the_same_key_in_two_tenants_is_allowed(api_session) -> None:
    """Scoped to (tenant_id, idempotency_key): one tenant's choice of key must
    never collide with — or be probeable from — another's."""
    api_session.add(_row(uuid.uuid4(), "shared-key"))
    api_session.add(_row(uuid.uuid4(), "shared-key"))
    api_session.flush()


def test_many_rows_without_a_key_do_not_collide(api_session) -> None:
    """The index is partial for this reason — most sends carry no key, and a
    plain unique index would make the second one fail on NULL."""
    tenant = uuid.uuid4()
    api_session.add(_row(tenant, None))
    api_session.add(_row(tenant, None))
    api_session.flush()
