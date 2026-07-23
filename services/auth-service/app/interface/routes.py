"""HTTP routes. Thin adapters: validate DTO → call use case → map result/errors."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy import select

from app.application import security, services
from app.application.services import AuthError
from app.infrastructure.db import SessionLocal, tenant_session
from app.infrastructure.models import TenantModel
from app.interface.schemas import (
    LoginRequest,
    RegisterTenantRequest,
    TokenResponse,
    UserResponse,
)
from app.config import settings

router = APIRouter(prefix="/v1/auth", tags=["auth"])


def _resolve_tenant_id(slug: str) -> uuid.UUID:
    """Tenant lookup runs outside RLS (tenant table is not tenant-scoped)."""
    with SessionLocal() as s:
        tid = s.scalar(select(TenantModel.id).where(TenantModel.slug == slug))
    if tid is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown tenant")
    return tid


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterTenantRequest) -> TokenResponse:
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
        s.commit()
    return TokenResponse(
        access_token=access, refresh_token=raw_refresh, expires_in=settings.jwt_expires_in
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest) -> TokenResponse:
    tenant_id = _resolve_tenant_id(body.slug)
    try:
        with tenant_session(tenant_id) as s:
            access, refresh = services.authenticate(
                s, email=body.email, password=body.password, totp_code=body.totp_code
            )
    except AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    return TokenResponse(
        access_token=access, refresh_token=refresh, expires_in=settings.jwt_expires_in
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
