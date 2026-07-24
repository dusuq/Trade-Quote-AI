"""HTTP routes. Trusts the API Gateway's identity headers (x-tenant-id,
x-user-id) — the gateway already verified the JWT (see apps/api-gateway),
so this service never decodes tokens itself.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, status

from app.application import services
from app.config import settings
from app.domain.errors import CustomerNotFoundError
from app.infrastructure.db import tenant_session
from app.infrastructure.sqlalchemy_repositories import (
    SqlAlchemyContactRepository,
    SqlAlchemyCustomerRepository,
    SqlAlchemyNoteRepository,
    SqlAlchemyPropertyRepository,
    SqlAlchemyTagRepository,
)
from app.interface.schemas import (
    AddContactRequest,
    AddNoteRequest,
    AddPropertyRequest,
    ContactResponse,
    CreateCustomerRequest,
    CustomerListResponse,
    CustomerResponse,
    NoteResponse,
    PropertyResponse,
    TagCustomerRequest,
    TagResponse,
    TimelineEntryResponse,
)

router = APIRouter(prefix="/v1/customers", tags=["customers"])


def _require_tenant(x_tenant_id: str | None) -> UUID:
    if not x_tenant_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing tenant context")
    try:
        return UUID(x_tenant_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid tenant id") from exc


def _require_user(x_user_id: str | None) -> UUID | None:
    if not x_user_id:
        return None
    try:
        return UUID(x_user_id)
    except ValueError:
        return None


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
def create_customer(
    body: CreateCustomerRequest,
    x_tenant_id: str | None = Header(default=None),
) -> CustomerResponse:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as s:
        repo = SqlAlchemyCustomerRepository(s)
        customer, _event = services.create_customer(
            repo,
            tenant_id=tenant_id,
            display_name=body.display_name,
            company_name=body.company_name,
            email=body.email,
            phone=body.phone,
        )
        # TODO(T003 outbox): persist the returned domain event to the outbox in this same tx.
        return CustomerResponse(**customer.__dict__)


@router.get("", response_model=CustomerListResponse)
def list_customers(
    q: str | None = Query(default=None),
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1),
    x_tenant_id: str | None = Header(default=None),
) -> CustomerListResponse:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as s:
        repo = SqlAlchemyCustomerRepository(s)
        results, resolved, total = services.search_customers(
            repo,
            tenant_id=tenant_id,
            query=q,
            page=page,
            page_size=page_size,
            default_page_size=settings.default_page_size,
            max_page_size=settings.max_page_size,
        )
        return CustomerListResponse(
            items=[CustomerResponse(**c.__dict__) for c in results],
            page=resolved.page,
            page_size=resolved.page_size,
            total=total,
        )


@router.get("/{customer_id}", response_model=CustomerResponse)
def get_customer(customer_id: UUID, x_tenant_id: str | None = Header(default=None)) -> CustomerResponse:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as s:
        repo = SqlAlchemyCustomerRepository(s)
        try:
            customer = services.get_customer(repo, tenant_id=tenant_id, customer_id=customer_id)
        except CustomerNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "customer not found") from exc
        return CustomerResponse(**customer.__dict__)


@router.post(
    "/{customer_id}/properties", response_model=PropertyResponse, status_code=status.HTTP_201_CREATED
)
def add_property(
    customer_id: UUID, body: AddPropertyRequest, x_tenant_id: str | None = Header(default=None)
) -> PropertyResponse:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as s:
        customer_repo = SqlAlchemyCustomerRepository(s)
        property_repo = SqlAlchemyPropertyRepository(s)
        try:
            prop, _event = services.add_property(
                customer_repo,
                property_repo,
                tenant_id=tenant_id,
                customer_id=customer_id,
                **body.model_dump(),
            )
        except CustomerNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "customer not found") from exc
        return PropertyResponse(**prop.__dict__)


@router.post(
    "/{customer_id}/contacts", response_model=ContactResponse, status_code=status.HTTP_201_CREATED
)
def add_contact(
    customer_id: UUID, body: AddContactRequest, x_tenant_id: str | None = Header(default=None)
) -> ContactResponse:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as s:
        customer_repo = SqlAlchemyCustomerRepository(s)
        contact_repo = SqlAlchemyContactRepository(s)
        try:
            contact = services.add_contact(
                customer_repo,
                contact_repo,
                tenant_id=tenant_id,
                customer_id=customer_id,
                **body.model_dump(),
            )
        except CustomerNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "customer not found") from exc
        return ContactResponse(**contact.__dict__)


@router.post(
    "/{customer_id}/notes", response_model=NoteResponse, status_code=status.HTTP_201_CREATED
)
def add_note(
    customer_id: UUID,
    body: AddNoteRequest,
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> NoteResponse:
    tenant_id = _require_tenant(x_tenant_id)
    author_id = _require_user(x_user_id)
    with tenant_session(tenant_id) as s:
        customer_repo = SqlAlchemyCustomerRepository(s)
        note_repo = SqlAlchemyNoteRepository(s)
        try:
            note = services.add_note(
                customer_repo,
                note_repo,
                tenant_id=tenant_id,
                customer_id=customer_id,
                body=body.body,
                author_id=author_id,
            )
        except CustomerNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "customer not found") from exc
        return NoteResponse(**note.__dict__)


@router.post("/{customer_id}/tags", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
def tag_customer(
    customer_id: UUID, body: TagCustomerRequest, x_tenant_id: str | None = Header(default=None)
) -> TagResponse:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as s:
        customer_repo = SqlAlchemyCustomerRepository(s)
        tag_repo = SqlAlchemyTagRepository(s)
        try:
            tag = services.tag_customer(
                customer_repo,
                tag_repo,
                tenant_id=tenant_id,
                customer_id=customer_id,
                label=body.label,
                color=body.color,
            )
        except CustomerNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "customer not found") from exc
        return TagResponse(**tag.__dict__)


@router.get("/{customer_id}/timeline", response_model=list[TimelineEntryResponse])
def get_timeline(
    customer_id: UUID, x_tenant_id: str | None = Header(default=None)
) -> list[TimelineEntryResponse]:
    tenant_id = _require_tenant(x_tenant_id)
    with tenant_session(tenant_id) as s:
        customer_repo = SqlAlchemyCustomerRepository(s)
        note_repo = SqlAlchemyNoteRepository(s)
        try:
            entries = services.get_customer_timeline(
                customer_repo, note_repo, tenant_id=tenant_id, customer_id=customer_id
            )
        except CustomerNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "customer not found") from exc
        return [
            TimelineEntryResponse(
                kind=e.kind, occurred_at=e.occurred_at, summary=e.summary, ref_id=e.ref_id
            )
            for e in entries
        ]
