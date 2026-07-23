"""Pydantic request/response DTOs for the HTTP interface."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class RegisterTenantRequest(BaseModel):
    tenant_name: str = Field(min_length=2, max_length=120)
    slug: str = Field(min_length=2, max_length=60, pattern=r"^[a-z0-9-]+$")
    owner_email: EmailStr
    owner_password: str = Field(min_length=8, max_length=200)
    owner_name: str | None = None


class LoginRequest(BaseModel):
    slug: str
    email: EmailStr
    password: str
    totp_code: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class InviteUserRequest(BaseModel):
    email: EmailStr
    role: str = "estimator"
    full_name: str | None = None


class MfaSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str


class MfaVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str | None
    status: str
    roles: list[str]
