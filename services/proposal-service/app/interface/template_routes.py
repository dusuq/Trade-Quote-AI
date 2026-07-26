"""HTTP routes for proposal templates. Trusts the gateway's x-tenant-id."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Header, HTTPException, status

from app.application import template_services
from app.domain.errors import TemplateNotFoundError
from app.infrastructure.db import tenant_session
from app.interface.schemas import TemplateCreate, TemplateResponse, TemplateUpdate

router = APIRouter(prefix="/v1/proposal-templates", tags=["proposal-templates"])


def _require_tenant(x_tenant_id: str | None) -> uuid.UUID:
    if not x_tenant_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing tenant context")
    try:
        return uuid.UUID(x_tenant_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid tenant id") from exc


@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
def create_template(
    body: TemplateCreate, x_tenant_id: str | None = Header(default=None)
) -> TemplateResponse:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as session:
        template = template_services.create_template(session, tenant_id, body)
        return TemplateResponse.model_validate(template)


@router.get("", response_model=list[TemplateResponse])
def list_templates(x_tenant_id: str | None = Header(default=None)) -> list[TemplateResponse]:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as session:
        templates = template_services.list_templates(session, tenant_id)
        return [TemplateResponse.model_validate(t) for t in templates]


@router.put("/{template_id}", response_model=TemplateResponse)
def update_template(
    template_id: uuid.UUID,
    body: TemplateUpdate,
    x_tenant_id: str | None = Header(default=None),
) -> TemplateResponse:
    tenant_id = _require_tenant(x_tenant_id)
    try:
        with tenant_session(tenant_id) as session:
            template = template_services.update_template(session, tenant_id, template_id, body)
            return TemplateResponse.model_validate(template)
    except TemplateNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
