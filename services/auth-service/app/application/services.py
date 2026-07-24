"""Auth use cases. Orchestrate persistence (Session), security primitives, and
domain events. Sessions are injected so use cases stay testable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

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
    """Raised for invalid credentials / auth failures (maps to 401)."""


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


def authenticate(
    session: Session, *, email: str, password: str, totp_code: str | None
) -> tuple[str, str]:
    """Verify credentials (+ MFA if enrolled) and return (access, refresh raw token)."""
    user = session.scalar(select(UserModel).where(UserModel.email == email))
    if user is None or not user.password_hash:
        raise AuthError("invalid credentials")
    if not security.verify_password(password, user.password_hash):
        raise AuthError("invalid credentials")
    if user.status != "active":
        raise AuthError("user not active")

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
    return access, raw_refresh
