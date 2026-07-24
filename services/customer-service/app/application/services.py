"""Customer CRM use cases. Depend only on the repository Protocols in
`app.domain.repositories` — fully unit-testable with in-memory fakes,
independent of SQLAlchemy/Postgres (see tests/fakes.py).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from uuid import UUID

from app.application.pagination import Page, resolve_page
from app.domain.entities import Contact, Customer, CustomerNote, Property, Tag, TimelineEntry
from app.domain.errors import CustomerNotFoundError
from app.domain.events import DomainEvent, customer_created, property_added
from app.domain.repositories import (
    ContactRepository,
    CustomerRepository,
    NoteRepository,
    PropertyRepository,
    TagRepository,
)


def _now() -> datetime:
    return datetime.now(UTC)


def create_customer(
    repo: CustomerRepository,
    *,
    tenant_id: UUID,
    display_name: str,
    company_name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
) -> tuple[Customer, DomainEvent]:
    customer = Customer(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        display_name=display_name,
        company_name=company_name,
        email=email,
        phone=phone,
        created_at=_now(),
        updated_at=_now(),
    )
    saved = repo.add(customer)
    event = customer_created(tenant_id, saved.id, saved.display_name)
    return saved, event


def get_customer(repo: CustomerRepository, *, tenant_id: UUID, customer_id: UUID) -> Customer:
    customer = repo.get(tenant_id, customer_id)
    if customer is None:
        raise CustomerNotFoundError(str(customer_id))
    return customer


def search_customers(
    repo: CustomerRepository,
    *,
    tenant_id: UUID,
    query: str | None,
    page: int | None,
    page_size: int | None,
    default_page_size: int,
    max_page_size: int,
) -> tuple[list[Customer], Page, int]:
    resolved = resolve_page(
        page, page_size, default_size=default_page_size, max_size=max_page_size
    )
    results = repo.search(tenant_id, query, resolved.limit, resolved.offset)
    total = repo.count(tenant_id, query)
    return results, resolved, total


def add_property(
    customer_repo: CustomerRepository,
    property_repo: PropertyRepository,
    *,
    tenant_id: UUID,
    customer_id: UUID,
    address_line1: str,
    address_line2: str | None = None,
    city: str | None = None,
    region: str | None = None,
    postal_code: str | None = None,
    country: str = "US",
    lat: float | None = None,
    lng: float | None = None,
) -> tuple[Property, DomainEvent]:
    if customer_repo.get(tenant_id, customer_id) is None:
        raise CustomerNotFoundError(str(customer_id))

    prop = Property(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        customer_id=customer_id,
        address_line1=address_line1,
        address_line2=address_line2,
        city=city,
        region=region,
        postal_code=postal_code,
        country=country,
        lat=lat,
        lng=lng,
        created_at=_now(),
    )
    saved = property_repo.add(prop)
    event = property_added(tenant_id, customer_id, saved.id, saved.address_line1)
    return saved, event


def add_contact(
    customer_repo: CustomerRepository,
    contact_repo: ContactRepository,
    *,
    tenant_id: UUID,
    customer_id: UUID,
    name: str,
    email: str | None = None,
    phone: str | None = None,
    is_primary: bool = False,
) -> Contact:
    if customer_repo.get(tenant_id, customer_id) is None:
        raise CustomerNotFoundError(str(customer_id))

    # A customer has at most one primary contact — setting a new one demotes the old.
    if is_primary:
        contact_repo.unset_primary(tenant_id, customer_id)

    contact = Contact(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        customer_id=customer_id,
        name=name,
        email=email,
        phone=phone,
        is_primary=is_primary,
        created_at=_now(),
    )
    return contact_repo.add(contact)


def add_note(
    customer_repo: CustomerRepository,
    note_repo: NoteRepository,
    *,
    tenant_id: UUID,
    customer_id: UUID,
    body: str,
    author_id: UUID | None = None,
) -> CustomerNote:
    if customer_repo.get(tenant_id, customer_id) is None:
        raise CustomerNotFoundError(str(customer_id))

    note = CustomerNote(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        customer_id=customer_id,
        body=body,
        author_id=author_id,
        created_at=_now(),
    )
    return note_repo.add(note)


def tag_customer(
    customer_repo: CustomerRepository,
    tag_repo: TagRepository,
    *,
    tenant_id: UUID,
    customer_id: UUID,
    label: str,
    color: str | None = None,
) -> Tag:
    if customer_repo.get(tenant_id, customer_id) is None:
        raise CustomerNotFoundError(str(customer_id))

    tag = tag_repo.get_by_label(tenant_id, label)
    if tag is None:
        tag = tag_repo.add(Tag(id=uuid.uuid4(), tenant_id=tenant_id, label=label, color=color))

    tag_repo.attach_to_customer(tenant_id, customer_id, tag.id)
    return tag


def get_customer_timeline(
    customer_repo: CustomerRepository,
    note_repo: NoteRepository,
    *,
    tenant_id: UUID,
    customer_id: UUID,
    limit: int = 50,
) -> list[TimelineEntry]:
    """Chronological view of a customer's history. Today this is just notes;
    future services (quote sent, proposal signed, payment captured) project
    their own domain events into this same shape as they come online.
    """
    if customer_repo.get(tenant_id, customer_id) is None:
        raise CustomerNotFoundError(str(customer_id))

    notes = note_repo.list_for_customer(tenant_id, customer_id, limit=limit)
    entries = [
        TimelineEntry(
            kind="note",
            occurred_at=note.created_at or _now(),
            summary=note.body,
            ref_id=note.id,
            extra={"authorId": str(note.author_id) if note.author_id else None},
        )
        for note in notes
    ]
    return sorted(entries, key=lambda e: e.occurred_at, reverse=True)
