"""Privileged-action audit log (T310b / M27 — OWASP A09).

Writes the `auth_audit_log` rows that migration 0016 prepared. The table has
existed since 0002 and nothing ever wrote to it — a control that is present on
the schema diagram and absent in reality, which is worse than not having it.

Two write paths, and the difference between them matters:

  * `record(session, ...)` joins the caller's transaction. Use it when the
    audited action itself is committing — the audit row lands atomically with
    the thing it describes, so there is no window where one exists without the
    other.

  * `record_isolated(tenant_id, ...)` opens its own transaction. Use it for
    FAILURES. A failed login rolls its transaction back by definition, and an
    audit row written inside that transaction rolls back with it — the
    failures, which are the only rows anyone will ever page on, would vanish.
    This is the one case where a separate transaction is correct rather than
    sloppy.

Audit writes never propagate an exception to the caller. That is a deliberate
trade and worth stating plainly: it means a database problem degrades the audit
log rather than taking down login. The alternative — failing the request —
turns the audit log into a new availability dependency for authentication,
which is a bad trade for a SaaS whose users cannot work when they cannot log
in. The mitigation is that every swallowed failure increments
`security_audit_write_failures_total`, and `AuditLogWriteFailures` pages on it
(infra/monitoring/prometheus/rules/security-metrics.yml). Silent is the failure
mode being guarded against; unavailable-but-loud is what replaces it.
"""

from __future__ import annotations

import logging
import uuid
from typing import Final

from sqlalchemy.orm import Session

from app.infrastructure import security_metrics
from app.infrastructure.models import AuthAuditLogModel

logger = logging.getLogger(__name__)

# Canonical action names. Free-text in the schema (see 0016 for why), but
# constants here so a typo does not silently create a parallel action nobody
# queries for.
ACTION_TENANT_REGISTERED: Final = "tenant.registered"
ACTION_LOGIN_SUCCEEDED: Final = "auth.login.succeeded"
ACTION_LOGIN_FAILED: Final = "auth.login.failed"

OUTCOME_SUCCESS: Final = "success"
OUTCOME_FAILURE: Final = "failure"

# `actor_email` is attacker-controlled on a failed login — the submitted
# address need not belong to any real user. Cap it so a single request cannot
# push an arbitrarily large blob into the log, and so the row stays readable.
MAX_ACTOR_EMAIL_LENGTH: Final = 320  # RFC 5321 maximum path length.


def _clip(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    return value if len(value) <= limit else value[:limit]


def _build(
    *,
    tenant_id: uuid.UUID,
    action: str,
    outcome: str,
    actor_id: uuid.UUID | None,
    actor_email: str | None,
    ip_address: str | None,
    user_agent: str | None,
    request_id: str | None,
    target_type: str | None,
    target_id: uuid.UUID | None,
    metadata: dict[str, object] | None,
) -> AuthAuditLogModel:
    return AuthAuditLogModel(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_email=_clip(actor_email, MAX_ACTOR_EMAIL_LENGTH),
        action=action,
        outcome=outcome,
        ip_address=ip_address,
        user_agent=_clip(user_agent, 500),
        request_id=_clip(request_id, 100),
        target_type=target_type,
        target_id=target_id,
        audit_metadata=metadata or {},
    )


def record(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    action: str,
    outcome: str = OUTCOME_SUCCESS,
    actor_id: uuid.UUID | None = None,
    actor_email: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    metadata: dict[str, object] | None = None,
) -> None:
    """Append an audit row inside the caller's transaction.

    Never raises: see the module docstring. On failure the row is lost and
    `security_audit_write_failures_total` moves, which is what alerts.
    """
    try:
        session.add(
            _build(
                tenant_id=tenant_id,
                action=action,
                outcome=outcome,
                actor_id=actor_id,
                actor_email=actor_email,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
                target_type=target_type,
                target_id=target_id,
                metadata=metadata,
            )
        )
        session.flush()
    except Exception:  # Deliberate catch-all: auditing must never break auth.
        security_metrics.audit_write_failures_total.inc()
        logger.exception("audit log write failed", extra={"action": action, "outcome": outcome})
        return
    security_metrics.privileged_actions_total.labels(action=action, outcome=outcome).inc()


def record_isolated(
    *,
    tenant_id: uuid.UUID,
    action: str,
    outcome: str = OUTCOME_FAILURE,
    actor_id: uuid.UUID | None = None,
    actor_email: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    metadata: dict[str, object] | None = None,
) -> None:
    """Append an audit row in its own committed transaction.

    For events whose own transaction is rolling back — a failed login being the
    canonical case. Imported lazily so this module stays importable (and unit
    testable) without a live database.
    """
    from app.infrastructure.db import tenant_session

    try:
        with tenant_session(tenant_id) as session:
            session.add(
                _build(
                    tenant_id=tenant_id,
                    action=action,
                    outcome=outcome,
                    actor_id=actor_id,
                    actor_email=actor_email,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    request_id=request_id,
                    target_type=target_type,
                    target_id=target_id,
                    metadata=metadata,
                )
            )
    except Exception:  # Deliberate catch-all: auditing must never break auth.
        security_metrics.audit_write_failures_total.inc()
        logger.exception("audit log write failed", extra={"action": action, "outcome": outcome})
        return
    security_metrics.privileged_actions_total.labels(action=action, outcome=outcome).inc()
