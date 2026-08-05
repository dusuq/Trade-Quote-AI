"""Auth use cases. Orchestrate persistence (Session), security primitives, and
domain events. Sessions are injected so use cases stay testable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application import security
from app.config import settings
from app.domain.entities import RoleKey
from app.domain.events import DomainEvent, tenant_created, user_invited
from app.infrastructure.models import (
    RefreshTokenModel,
    RoleModel,
    TenantModel,
    UserModel,
    UserRoleModel,
)
from app.infrastructure.security_metrics import LoginFailureReason

SYSTEM_ROLES: dict[RoleKey, str] = {
    RoleKey.OWNER: "Owner",
    RoleKey.ADMIN: "Admin",
    RoleKey.ESTIMATOR: "Estimator",
    RoleKey.TECHNICIAN: "Technician",
    RoleKey.SALESPERSON: "Salesperson",
    RoleKey.OFFICE: "Office Staff",
    RoleKey.ACCOUNTANT: "Accountant",
    RoleKey.VIEWER: "Viewer",
}


class AuthError(Exception):
    """Raised for invalid credentials / auth failures (maps to 401).

    Carries a machine-readable `reason` (and the matched user, when there was
    one) so the route can label metrics and write an audit row without
    string-matching the message — T310b. The HTTP response still says a flat
    "invalid credentials" regardless of reason: the detail is for the tenant's
    own audit log and the metrics endpoint, never for the caller, or the login
    endpoint becomes an account-enumeration oracle.
    """

    def __init__(
        self,
        message: str,
        *,
        reason: LoginFailureReason,
        user_id: uuid.UUID | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.user_id = user_id


def register_tenant(
    session: Session,
    *,
    tenant_name: str,
    slug: str,
    owner_email: str,
    owner_password: str,
    owner_name: str | None,
) -> tuple[TenantModel, UserModel, list[DomainEvent]]:
    """Create a tenant, seed its system roles, and create the owner user."""
    tenant = TenantModel(id=uuid.uuid4(), name=tenant_name, slug=slug)
    session.add(tenant)
    session.flush()  # assign PK before dependents

    roles: dict[RoleKey, RoleModel] = {}
    for key, label in SYSTEM_ROLES.items():
        role = RoleModel(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            key=key.value,
            name=label,
            is_system=True,
        )
        session.add(role)
        roles[key] = role
    session.flush()

    owner = UserModel(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        email=owner_email,
        full_name=owner_name,
        password_hash=security.hash_password(owner_password),
        status="active",
    )
    session.add(owner)
    session.flush()
    session.add(
        UserRoleModel(tenant_id=tenant.id, user_id=owner.id, role_id=roles[RoleKey.OWNER].id)
    )

    events = [
        tenant_created(tenant.id, tenant_name, tenant.plan),
        user_invited(tenant.id, owner.id, owner_email, RoleKey.OWNER.value),
    ]
    return tenant, owner, events


def _user_role_keys(session: Session, user: UserModel) -> list[str]:
    stmt = (
        select(RoleModel.key)
        .join(UserRoleModel, UserRoleModel.role_id == RoleModel.id)
        .where(UserRoleModel.user_id == user.id)
    )
    return list(session.scalars(stmt).all())


class AuthResult(NamedTuple):
    """Successful authentication.

    `user_id` is here so the route can attribute the audit row to the actor
    (T310b) without re-querying — a NamedTuple so existing tuple unpacking of
    the first two elements keeps working.
    """

    access_token: str
    refresh_token: str
    user_id: uuid.UUID


def authenticate(
    session: Session, *, email: str, password: str, totp_code: str | None
) -> AuthResult:
    """Verify credentials (+ MFA if enrolled) and return (access, refresh raw token).

    The session is already tenant-scoped by the caller, so the `email` lookup is
    RLS-bounded to that tenant — the same address in another tenant is a
    different user and will not match here.
    """
    user = session.scalar(select(UserModel).where(UserModel.email == email))
    if user is None or not user.password_hash:
        # No user row, or an SSO-only account with no password to check.
        # Distinguished from a wrong password for the audit log and metrics
        # only — the caller still sees the same message either way.
        raise AuthError("invalid credentials", reason=LoginFailureReason.UNKNOWN_USER)
    if not security.verify_password(password, user.password_hash):
        raise AuthError(
            "invalid credentials", reason=LoginFailureReason.BAD_PASSWORD, user_id=user.id
        )
    if user.status != "active":
        raise AuthError(
            "user not active", reason=LoginFailureReason.INACTIVE_USER, user_id=user.id
        )

    role_keys = _user_role_keys(session, user)
    access = security.issue_access_token(
        user_id=user.id, tenant_id=user.tenant_id, roles=role_keys
    )
    raw_refresh, refresh_hash = security.new_refresh_token()
    session.add(
        RefreshTokenModel(
            id=uuid.uuid4(),
            tenant_id=user.tenant_id,
            user_id=user.id,
            token_hash=refresh_hash,
            expires_at=datetime.now(UTC)
            + timedelta(seconds=settings.refresh_expires_in),
        )
    )
    user.last_login_at = datetime.now(UTC)
    return AuthResult(access_token=access, refresh_token=raw_refresh, user_id=user.id)
