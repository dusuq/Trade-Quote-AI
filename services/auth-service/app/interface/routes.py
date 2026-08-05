"""HTTP routes. Thin adapters: validate DTO → call use case → map result/errors.

Pre-auth routes (`/register`, `/login`) are on the gateway's public allowlist
and see no identity headers. `/audit-log` is authenticated, so the gateway has
already verified the JWT and injected `x-tenant-id` / `x-user-id` /
`x-user-roles` — this service trusts those, per docs/07-SERVICE-CONVENTIONS.md.
"""

from __future__ import annotations

import uuid
from typing import NamedTuple

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from sqlalchemy import select

from app.application import audit, security, services
from app.application.services import AuthError
from app.config import settings
from app.infrastructure import security_metrics
from app.infrastructure.db import SessionLocal, tenant_session
from app.infrastructure.models import AuthAuditLogModel, TenantModel
from app.infrastructure.security_metrics import LoginFailureReason
from app.interface.schemas import (
    AuditLogEntryResponse,
    AuditLogResponse,
    LoginRequest,
    RegisterTenantRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/v1/auth", tags=["auth"])

# Reading the security audit log is itself a privileged action: the rows carry
# every login attempt and every attempted email for the tenant. Only the two
# roles that already administer the tenant may see it.
AUDIT_READER_ROLES = frozenset({"owner", "admin"})

MAX_AUDIT_PAGE_SIZE = 200


def _resolve_tenant_id(slug: str) -> uuid.UUID:
    """Tenant lookup runs outside RLS (tenant table is not tenant-scoped)."""
    with SessionLocal() as s:
        tid = s.scalar(select(TenantModel.id).where(TenantModel.slug == slug))
    if tid is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown tenant")
    return tid


class ClientContext(NamedTuple):
    ip_address: str | None
    user_agent: str | None
    request_id: str | None


def _client_context(request: Request) -> ClientContext:
    """Caller attribution for an audit row.

    `x-forwarded-for` is the real peer address: the gateway *overwrites* any
    client-supplied value with `request.ip` before proxying (proxy.ts), so it
    cannot be chosen by the caller — which is what makes it worth recording.
    """
    forwarded = request.headers.get("x-forwarded-for")
    return ClientContext(
        ip_address=forwarded.split(",")[0].strip() if forwarded else None,
        user_agent=request.headers.get("user-agent"),
        request_id=request.headers.get("x-request-id"),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterTenantRequest, request: Request) -> TokenResponse:
    context = _client_context(request)
    # New tenant: create the tenant row first (no tenant context yet), then scope.
    with SessionLocal() as s:
        if s.scalar(select(TenantModel.id).where(TenantModel.slug == body.slug)):
            raise HTTPException(status.HTTP_409_CONFLICT, "slug already taken")
        tenant, owner, events = services.register_tenant(
            s,
            tenant_name=body.tenant_name,
            slug=body.slug,
            owner_email=body.owner_email,
            owner_password=body.owner_password,
            owner_name=body.owner_name,
        )
        # TODO(T003 outbox): persist `events` to the outbox in this same tx.
        _ = events
        access = security.issue_access_token(
            user_id=owner.id, tenant_id=tenant.id, roles=["owner"]
        )
        raw_refresh, _hash = security.new_refresh_token()
        # Same transaction as the tenant/owner rows: the audit record and the
        # thing it audits commit together or not at all (T310b).
        audit.record(
            s,
            tenant_id=tenant.id,
            action=audit.ACTION_TENANT_REGISTERED,
            actor_id=owner.id,
            actor_email=body.owner_email,
            target_type="tenant",
            target_id=tenant.id,
            metadata={"slug": body.slug},
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            request_id=context.request_id,
        )
        s.commit()
    return TokenResponse(
        access_token=access, refresh_token=raw_refresh, expires_in=settings.jwt_expires_in
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request) -> TokenResponse:
    context = _client_context(request)
    try:
        tenant_id = _resolve_tenant_id(body.slug)
    except HTTPException:
        # No tenant, so no tenant-scoped row can be written — the audit log is
        # tenant-partitioned and there is nothing to partition this under.
        # The metric is the only record, which is why it exists as its own
        # reason rather than folding into unknown_user.
        security_metrics.record_login_failure(LoginFailureReason.UNKNOWN_TENANT)
        raise

    try:
        with tenant_session(tenant_id) as s:
            result = services.authenticate(
                s, email=body.email, password=body.password, totp_code=body.totp_code
            )
            audit.record(
                s,
                tenant_id=tenant_id,
                action=audit.ACTION_LOGIN_SUCCEEDED,
                actor_id=result.user_id,
                actor_email=body.email,
                ip_address=context.ip_address,
                user_agent=context.user_agent,
                request_id=context.request_id,
            )
    except AuthError as exc:
        security_metrics.record_login_failure(exc.reason)
        # Isolated transaction, deliberately: this one is rolling back, and an
        # audit row written inside it would roll back too — losing exactly the
        # rows anyone would ever investigate. See app/application/audit.py.
        audit.record_isolated(
            tenant_id=tenant_id,
            action=audit.ACTION_LOGIN_FAILED,
            actor_id=exc.user_id,
            actor_email=body.email,
            metadata={"reason": str(exc.reason)},
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            request_id=context.request_id,
        )
        # Flat message regardless of reason — the detail stays in the tenant's
        # audit log and the metrics, so this endpoint is not an enumeration
        # oracle for which addresses have accounts.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials") from exc

    security_metrics.record_login_success()
    return TokenResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        expires_in=settings.jwt_expires_in,
    )


@router.get("/me", response_model=UserResponse)
def me(authorization: str = Header(default="")) -> UserResponse:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        claims = security.decode_access_token(token)
    except Exception as exc:  # jwt.InvalidTokenError and subclasses
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from exc
    return UserResponse(
        id=claims["sub"],
        email=claims.get("email", ""),
        full_name=None,
        status="active",
        roles=claims.get("roles", []),
    )


@router.get("/audit-log", response_model=AuditLogResponse)
def read_audit_log(
    limit: int = Query(default=50, ge=1, le=MAX_AUDIT_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    action: str | None = Query(default=None, max_length=100),
    outcome: str | None = Query(default=None, pattern="^(success|failure)$"),
    x_tenant_id: str | None = Header(default=None),
    x_user_roles: str | None = Header(default=None),
) -> AuditLogResponse:
    """The tenant's own security audit log, newest first (T310b).

    Tenant-scoped twice over: the `x-tenant-id` header drives the RLS GUC, and
    the policy on `auth_audit_log` filters rows to that tenant regardless of
    what this query asks for. There is no cross-tenant read here even if this
    handler were wrong.
    """
    if not x_tenant_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing tenant context")
    try:
        tenant_id = uuid.UUID(x_tenant_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid tenant id") from exc

    roles = {r.strip() for r in (x_user_roles or "").split(",") if r.strip()}
    if not roles & AUDIT_READER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient role")

    with tenant_session(tenant_id) as s:
        stmt = select(AuthAuditLogModel).order_by(AuthAuditLogModel.created_at.desc())
        if action:
            stmt = stmt.where(AuthAuditLogModel.action == action)
        if outcome:
            stmt = stmt.where(AuthAuditLogModel.outcome == outcome)
        rows = list(s.scalars(stmt.limit(limit).offset(offset)).all())

    return AuditLogResponse(
        entries=[
            AuditLogEntryResponse(
                id=str(row.id),
                action=row.action,
                outcome=row.outcome,
                actor_id=str(row.actor_id) if row.actor_id else None,
                actor_email=row.actor_email,
                ip_address=row.ip_address,
                target_type=row.target_type,
                target_id=str(row.target_id) if row.target_id else None,
                metadata=row.audit_metadata or {},
                created_at=row.created_at,
            )
            for row in rows
        ],
        limit=limit,
        offset=offset,
    )
