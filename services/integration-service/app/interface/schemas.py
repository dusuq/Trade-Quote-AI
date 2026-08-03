"""Pydantic request/response DTOs for the HTTP interface."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.entities import ProviderKind, SyncDirection

# ── Connection DTOs ────────────────────────────────────────────────────────


class CreateConnectionRequest(BaseModel):
    # Literal, not a regex str: Pydantic still rejects unknown providers with a
    # 422, and the value now types as ProviderKind straight through to the use
    # case instead of being a bare str the boundary has to re-narrow.
    provider: ProviderKind
    display_name: str | None = None


class ConnectionResponse(BaseModel):
    id: UUID
    provider: str
    status: str
    external_account_id: str | None
    display_name: str | None
    scopes: str | None
    created_at: datetime | None
    updated_at: datetime | None
    created_by: UUID | None


class ConnectionListResponse(BaseModel):
    items: list[ConnectionResponse]
    total: int


class ActivateConnectionRequest(BaseModel):
    access_token_encrypted: str = Field(min_length=1)
    refresh_token_encrypted: str | None = None
    token_expires_at: datetime | None = None
    external_account_id: str | None = None
    scopes: str | None = None


# ── Webhook DTOs ───────────────────────────────────────────────────────────


class CreateWebhookRequest(BaseModel):
    target_url: str = Field(min_length=1, max_length=2048)
    event_types: list[str] = Field(min_length=1)
    secret: str | None = None


class WebhookResponse(BaseModel):
    id: UUID
    connection_id: UUID
    target_url: str
    event_types: list[str]
    is_active: bool
    created_at: datetime | None


class WebhookListResponse(BaseModel):
    items: list[WebhookResponse]
    total: int


# ── Sync DTOs ──────────────────────────────────────────────────────────────


class StartSyncRequest(BaseModel):
    direction: SyncDirection
    entity_type: str = Field(min_length=1, max_length=100)
    entity_id: UUID | None = None
    request_payload: dict | None = None


class CompleteSyncRequest(BaseModel):
    # Only terminal states are completable — a subset of SyncStatus, and
    # assignable to it, so complete_sync() stays fully typed.
    status: Literal["success", "failed"]
    external_id: str | None = None
    error_message: str | None = None
    response_payload: dict | None = None


class SyncLogResponse(BaseModel):
    id: UUID
    connection_id: UUID
    direction: str
    entity_type: str
    entity_id: UUID | None
    status: str
    external_id: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None


class SyncLogListResponse(BaseModel):
    items: list[SyncLogResponse]
    total: int
