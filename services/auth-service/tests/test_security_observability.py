"""T310b — security observability in the identity service.

No database: every case drives the real code with a fake Session, or hits the
route surface at a point that returns before any query runs. That is a
deliberate limit, stated rather than hidden — what these prove is that the
right rows are *constructed* and the right counters *move*. What they cannot
prove is that Postgres accepts the row, that RLS scopes the read, or that the
0016 REVOKE actually blocks an UPDATE. Those need a live database and are
covered by tests/integration/test_postgres_rls.py, which skips itself when
Postgres is unreachable (the normal local state — see 0015's header for how
that exact pattern hid a real bug once already).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app.application import audit, services
from app.infrastructure import security_metrics
from app.infrastructure.models import AuthAuditLogModel, UserModel
from app.infrastructure.security_metrics import LoginFailureReason
from app.main import app


def sample(name: str, labels: dict[str, str] | None = None) -> float:
    """Current value of a counter sample, 0.0 when the series does not exist."""
    return REGISTRY.get_sample_value(name, labels or {}) or 0.0


class FakeSession:
    """Just enough Session for the audit writer and `authenticate`."""

    def __init__(self, user: UserModel | None = None, role_keys: list[str] | None = None) -> None:
        self.added: list[Any] = []
        self.flushed = 0
        self._user = user
        self._role_keys = role_keys or []

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        self.flushed += 1

    def scalar(self, _stmt: Any) -> Any:
        return self._user

    def scalars(self, _stmt: Any) -> Any:
        class _Result:
            def __init__(self, values: list[str]) -> None:
                self._values = values

            def all(self) -> list[str]:
                return self._values

        return _Result(self._role_keys)

    def rows(self) -> list[AuthAuditLogModel]:
        return [o for o in self.added if isinstance(o, AuthAuditLogModel)]


class ExplodingSession(FakeSession):
    def add(self, obj: Any) -> None:
        raise RuntimeError("database is on fire")


def _user(*, status: str = "active", password: str = "correct horse battery staple") -> UserModel:
    return UserModel(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="owner@example.com",
        full_name=None,
        password_hash=services.security.hash_password(password, iterations=1_000),
        status=status,
    )


# ── The audit writer ─────────────────────────────────────────────────────────


class TestAuditWriter:
    def test_record_appends_a_row_to_the_callers_transaction(self) -> None:
        session = FakeSession()
        tenant_id, actor_id = uuid.uuid4(), uuid.uuid4()

        audit.record(
            session,  # type: ignore[arg-type]
            tenant_id=tenant_id,
            action=audit.ACTION_LOGIN_SUCCEEDED,
            actor_id=actor_id,
            actor_email="owner@example.com",
            ip_address="203.0.113.7",
            metadata={"k": "v"},
        )

        (row,) = session.rows()
        assert row.tenant_id == tenant_id
        assert row.actor_id == actor_id
        assert row.action == audit.ACTION_LOGIN_SUCCEEDED
        assert row.outcome == audit.OUTCOME_SUCCESS
        assert row.ip_address == "203.0.113.7"
        assert row.audit_metadata == {"k": "v"}
        # Flushed inside the caller's transaction — the audit row and the thing
        # it audits commit together, so neither can exist without the other.
        assert session.flushed == 1

    def test_record_counts_the_privileged_action(self) -> None:
        labels = {"action": audit.ACTION_TENANT_REGISTERED, "outcome": audit.OUTCOME_SUCCESS}
        before = sample("security_privileged_actions_total", labels)

        audit.record(
            FakeSession(),  # type: ignore[arg-type]
            tenant_id=uuid.uuid4(),
            action=audit.ACTION_TENANT_REGISTERED,
        )

        assert sample("security_privileged_actions_total", labels) == before + 1

    def test_a_failed_write_is_swallowed_but_counted(self) -> None:
        """The trade in audit.py's docstring, locked down.

        Auditing must not be able to take down login — but a silently lost
        audit row is exactly the A09 failure this task exists to fix, so the
        loss has to be loud somewhere. `security_audit_write_failures_total`
        is that somewhere, and AuditLogWriteFailures pages on it.
        """
        before_failures = sample("security_audit_write_failures_total")
        before_actions = sample(
            "security_privileged_actions_total",
            {"action": audit.ACTION_LOGIN_SUCCEEDED, "outcome": audit.OUTCOME_SUCCESS},
        )

        audit.record(  # must not raise
            ExplodingSession(),  # type: ignore[arg-type]
            tenant_id=uuid.uuid4(),
            action=audit.ACTION_LOGIN_SUCCEEDED,
        )

        assert sample("security_audit_write_failures_total") == before_failures + 1
        # And it must NOT claim the action was recorded.
        assert (
            sample(
                "security_privileged_actions_total",
                {"action": audit.ACTION_LOGIN_SUCCEEDED, "outcome": audit.OUTCOME_SUCCESS},
            )
            == before_actions
        )

    def test_attacker_controlled_actor_email_is_length_capped(self) -> None:
        # A failed login writes whatever address was submitted. Without a cap,
        # one request could push an arbitrarily large blob into the audit log.
        session = FakeSession()
        audit.record(
            session,  # type: ignore[arg-type]
            tenant_id=uuid.uuid4(),
            action=audit.ACTION_LOGIN_FAILED,
            outcome=audit.OUTCOME_FAILURE,
            actor_email="a" * 5_000,
        )
        (row,) = session.rows()
        assert row.actor_email is not None
        assert len(row.actor_email) == audit.MAX_ACTOR_EMAIL_LENGTH

    def test_user_agent_is_length_capped_too(self) -> None:
        session = FakeSession()
        audit.record(
            session,  # type: ignore[arg-type]
            tenant_id=uuid.uuid4(),
            action=audit.ACTION_LOGIN_FAILED,
            user_agent="U" * 5_000,
        )
        (row,) = session.rows()
        assert row.user_agent is not None
        assert len(row.user_agent) == 500


# ── Login failure classification ─────────────────────────────────────────────


class TestLoginFailureReasons:
    """`authenticate` must hand back WHY, without the API ever revealing it."""

    def test_unknown_user(self) -> None:
        with pytest.raises(services.AuthError) as exc:
            services.authenticate(
                FakeSession(user=None),  # type: ignore[arg-type]
                email="nobody@example.com",
                password="x",
                totp_code=None,
            )
        assert exc.value.reason is LoginFailureReason.UNKNOWN_USER
        assert exc.value.user_id is None  # nothing to attribute the attempt to

    def test_bad_password_is_attributed_to_the_real_user(self) -> None:
        user = _user()
        with pytest.raises(services.AuthError) as exc:
            services.authenticate(
                FakeSession(user=user),  # type: ignore[arg-type]
                email=user.email,
                password="not the password",
                totp_code=None,
            )
        assert exc.value.reason is LoginFailureReason.BAD_PASSWORD
        # This is what separates a targeted brute force (one actor_id, many
        # rows) from credential stuffing (many emails, no actor_id at all).
        assert exc.value.user_id == user.id

    def test_inactive_user(self) -> None:
        password = "correct horse battery staple"
        user = _user(status="suspended", password=password)
        with pytest.raises(services.AuthError) as exc:
            services.authenticate(
                FakeSession(user=user),  # type: ignore[arg-type]
                email=user.email,
                password=password,
                totp_code=None,
            )
        assert exc.value.reason is LoginFailureReason.INACTIVE_USER

    def test_success_returns_the_user_id_for_attribution(self) -> None:
        password = "correct horse battery staple"
        user = _user(password=password)
        result = services.authenticate(
            FakeSession(user=user, role_keys=["owner"]),  # type: ignore[arg-type]
            email=user.email,
            password=password,
            totp_code=None,
        )
        assert result.user_id == user.id
        assert result.access_token and result.refresh_token


class TestLoginMetrics:
    def test_failure_moves_both_the_attempt_and_the_reason_counter(self) -> None:
        reason = LoginFailureReason.BAD_PASSWORD
        before_attempts = sample("auth_login_attempts_total", {"result": "failure"})
        before_reason = sample("auth_login_failures_total", {"reason": str(reason)})

        security_metrics.record_login_failure(reason)

        assert sample("auth_login_attempts_total", {"result": "failure"}) == before_attempts + 1
        assert sample("auth_login_failures_total", {"reason": str(reason)}) == before_reason + 1

    def test_success_moves_only_the_attempt_counter(self) -> None:
        before = sample("auth_login_attempts_total", {"result": "success"})
        security_metrics.record_login_success()
        assert sample("auth_login_attempts_total", {"result": "success"}) == before + 1

    def test_every_reason_is_a_closed_set_value(self) -> None:
        # These counters are driven by UNAUTHENTICATED traffic. A label derived
        # from request input would be a remote "allocate a new Prometheus time
        # series" primitive, so the set must stay closed and small.
        assert {str(r) for r in LoginFailureReason} == {
            "unknown_tenant",
            "unknown_user",
            "bad_password",
            "inactive_user",
            "mfa_failed",
        }

    def test_metrics_endpoint_exposes_the_security_series(self) -> None:
        security_metrics.record_login_failure(LoginFailureReason.UNKNOWN_USER)
        body = TestClient(app).get("/metrics").text
        assert "auth_login_failures_total" in body
        assert "auth_login_attempts_total" in body
        assert "security_audit_write_failures_total" in body


# ── The audit-log read endpoint ──────────────────────────────────────────────


class TestAuditLogEndpointAuthorization:
    """Every case here is refused *before* any query runs — no DB needed.

    That is also the point: reading the log is itself privileged, so the
    authorization decision must not depend on the database being reachable.
    """

    client = TestClient(app)

    def test_requires_tenant_context(self) -> None:
        resp = self.client.get("/v1/auth/audit-log")
        assert resp.status_code == 401

    def test_rejects_a_malformed_tenant_id(self) -> None:
        resp = self.client.get(
            "/v1/auth/audit-log",
            headers={"x-tenant-id": "not-a-uuid", "x-user-roles": "owner"},
        )
        assert resp.status_code == 400

    @pytest.mark.parametrize("roles", ["", "viewer", "estimator,technician"])
    def test_rejects_roles_that_do_not_administer_the_tenant(self, roles: str) -> None:
        resp = self.client.get(
            "/v1/auth/audit-log",
            headers={"x-tenant-id": str(uuid.uuid4()), "x-user-roles": roles},
        )
        assert resp.status_code == 403

    def test_caps_the_page_size(self) -> None:
        # Validation runs before the role check, so this 422s without a DB.
        resp = self.client.get(
            "/v1/auth/audit-log?limit=100000",
            headers={"x-tenant-id": str(uuid.uuid4()), "x-user-roles": "owner"},
        )
        assert resp.status_code == 422

    def test_rejects_an_unknown_outcome_filter(self) -> None:
        resp = self.client.get(
            "/v1/auth/audit-log?outcome=maybe",
            headers={"x-tenant-id": str(uuid.uuid4()), "x-user-roles": "owner"},
        )
        assert resp.status_code == 422
