"""Domain entities (framework-free, pure Python) for integration connectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

ProviderKind = Literal["quickbooks", "xero", "zapier"]
ConnectionStatus = Literal["pending", "active", "expired", "revoked", "error"]
SyncDirection = Literal["push", "pull"]
SyncStatus = Literal["pending", "running", "success", "failed"]


@dataclass(slots=True)
class IntegrationConnection:
    id: UUID
    tenant_id: UUID
    provider: ProviderKind
    status: ConnectionStatus
    external_account_id: str | None = None
    display_name: str | None = None
    access_token_encrypted: str | None = None
    refresh_token_encrypted: str | None = None
    token_expires_at: datetime | None = None
    scopes: str | None = None
    config_json: dict | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by: UUID | None = None


@dataclass(slots=True)
class WebhookSubscription:
    id: UUID
    tenant_id: UUID
    connection_id: UUID
    target_url: str
    event_types: list[str] = field(default_factory=list)
    secret: str | None = None
    is_active: bool = True
    created_at: datetime | None = None


@dataclass(slots=True)
class SyncLog:
    id: UUID
    tenant_id: UUID
    connection_id: UUID
    direction: SyncDirection
    entity_type: str
    entity_id: UUID | None = None
    status: SyncStatus = "pending"
    external_id: str | None = None
    error_message: str | None = None
    request_payload: dict | None = None
    response_payload: dict | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
