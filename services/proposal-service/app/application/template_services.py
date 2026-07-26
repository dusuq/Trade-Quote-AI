"""Use cases for proposal template CRUD (T203 / M8)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.errors import TemplateNotFoundError
from app.infrastructure.models import ProposalTemplateModel
from app.interface.schemas import TemplateCreate, TemplateUpdate


def create_template(
    session: Session, tenant_id: UUID, data: TemplateCreate
) -> ProposalTemplateModel:
    template = ProposalTemplateModel(
        tenant_id=tenant_id,
        name=data.name,
        company_name=data.company_name,
        logo_url=data.logo_url,
        primary_color=data.primary_color,
        phone=data.phone,
        email=data.email,
        website=data.website,
        default_terms_text=data.default_terms_text,
        default_warranty_text=data.default_warranty_text,
        is_default=data.is_default,
    )
    session.add(template)
    session.flush()
    return template


def list_templates(session: Session, tenant_id: UUID) -> list[ProposalTemplateModel]:
    return list(
        session.scalars(
            select(ProposalTemplateModel).where(ProposalTemplateModel.tenant_id == tenant_id)
        )
    )


def _get_template(
    session: Session, tenant_id: UUID, template_id: UUID
) -> ProposalTemplateModel:
    template = session.scalar(
        select(ProposalTemplateModel).where(
            ProposalTemplateModel.id == template_id,
            ProposalTemplateModel.tenant_id == tenant_id,
        )
    )
    if not template:
        raise TemplateNotFoundError(f"Template '{template_id}' not found.")
    return template


def update_template(
    session: Session, tenant_id: UUID, template_id: UUID, data: TemplateUpdate
) -> ProposalTemplateModel:
    template = _get_template(session, tenant_id, template_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(template, field, value)
    session.flush()
    return template
