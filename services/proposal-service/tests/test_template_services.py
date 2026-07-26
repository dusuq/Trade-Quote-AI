"""Tests for proposal template CRUD (T203 / M8)."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.application import template_services
from app.domain.errors import TemplateNotFoundError
from app.interface.schemas import TemplateCreate, TemplateUpdate


def _create(db_session, tenant_id, *, name="Standard", is_default=True):
    return template_services.create_template(
        db_session,
        tenant_id,
        TemplateCreate(
            name=name,
            company_name="Bright Sparks Electric",
            primary_color="#1D4ED8",
            is_default=is_default,
        ),
    )


def test_create_template(db_session, tenant_id):
    template = _create(db_session, tenant_id)
    assert template.id is not None
    assert template.company_name == "Bright Sparks Electric"
    assert template.is_default is True


def test_list_templates_scoped_to_tenant(db_session, tenant_id):
    import uuid

    _create(db_session, tenant_id)
    other_tenant = uuid.uuid4()
    _create(db_session, other_tenant, name="Other Co")

    templates = template_services.list_templates(db_session, tenant_id)
    assert len(templates) == 1
    assert templates[0].name == "Standard"


def test_update_template(db_session, tenant_id):
    template = _create(db_session, tenant_id)
    updated = template_services.update_template(
        db_session, tenant_id, template.id, TemplateUpdate(primary_color="#000000")
    )
    assert updated.primary_color == "#000000"


def test_update_unknown_template_raises(db_session, tenant_id):
    import uuid

    with pytest.raises(TemplateNotFoundError):
        template_services.update_template(
            db_session, tenant_id, uuid.uuid4(), TemplateUpdate(primary_color="#000000")
        )


def test_only_one_default_template_per_tenant(db_session, tenant_id):
    _create(db_session, tenant_id, name="First", is_default=True)
    db_session.flush()
    with pytest.raises(IntegrityError):
        _create(db_session, tenant_id, name="Second", is_default=True)
        db_session.flush()
