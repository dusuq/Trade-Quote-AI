"""Concrete repository implementations backed by SQLAlchemy/Postgres.
Implements the Protocols in `app.domain.repositories`. Untested against a
live database in this environment — integration coverage lands once the dev
stack is verified under T002b; the use-case logic itself is fully covered
against in-memory fakes in tests/.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domain.entities import Contact, Customer, CustomerNote, Property, Tag
from app.infrastructure.models import (
    ContactModel,
    CustomerModel,
    CustomerNoteModel,
    CustomerTagModel,
    PropertyModel,
    TagModel,
)


def _to_customer(row: CustomerModel) -> Customer:
    return Customer(
        id=row.id,
        tenant_id=row.tenant_id,
        display_name=row.display_name,
        company_name=row.company_name,
        email=row.email,
        phone=row.phone,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_contact(row: ContactModel) -> Contact:
    return Contact(
        id=row.id,
        tenant_id=row.tenant_id,
        customer_id=row.customer_id,
        name=row.name,
        email=row.email,
        phone=row.phone,
        is_primary=row.is_primary,
        created_at=row.created_at,
    )


def _to_property(row: PropertyModel) -> Property:
    return Property(
        id=row.id,
        tenant_id=row.tenant_id,
        customer_id=row.customer_id,
        address_line1=row.address_line1,
        address_line2=row.address_line2,
        city=row.city,
        region=row.region,
        postal_code=row.postal_code,
        country=row.country,
        lat=row.lat,
        lng=row.lng,
        created_at=row.created_at,
    )


def _to_tag(row: TagModel) -> Tag:
    return Tag(id=row.id, tenant_id=row.tenant_id, label=row.label, color=row.color)


def _to_note(row: CustomerNoteModel) -> CustomerNote:
    return CustomerNote(
        id=row.id,
        tenant_id=row.tenant_id,
        customer_id=row.customer_id,
        body=row.body,
        author_id=row.author_id,
        created_at=row.created_at,
    )


class SqlAlchemyCustomerRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, customer: Customer) -> Customer:
        row = CustomerModel(
            id=customer.id,
            tenant_id=customer.tenant_id,
            display_name=customer.display_name,
            company_name=customer.company_name,
            email=customer.email,
            phone=customer.phone,
        )
        self._session.add(row)
        self._session.flush()
        return _to_customer(row)

    def get(self, tenant_id: UUID, customer_id: UUID) -> Customer | None:
        row = self._session.get(CustomerModel, customer_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _to_customer(row)

    def search(self, tenant_id: UUID, query: str | None, limit: int, offset: int) -> list[Customer]:
        stmt = select(CustomerModel).where(CustomerModel.tenant_id == tenant_id)
        if query:
            like = f"%{query}%"
            stmt = stmt.where(
                or_(CustomerModel.display_name.ilike(like), CustomerModel.company_name.ilike(like))
            )
        stmt = stmt.order_by(CustomerModel.created_at.desc()).limit(limit).offset(offset)
        rows = self._session.scalars(stmt).all()
        return [_to_customer(r) for r in rows]

    def count(self, tenant_id: UUID, query: str | None) -> int:
        stmt = select(func.count()).select_from(CustomerModel).where(
            CustomerModel.tenant_id == tenant_id
        )
        if query:
            like = f"%{query}%"
            stmt = stmt.where(
                or_(CustomerModel.display_name.ilike(like), CustomerModel.company_name.ilike(like))
            )
        return self._session.scalar(stmt) or 0


class SqlAlchemyContactRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, contact: Contact) -> Contact:
        row = ContactModel(
            id=contact.id,
            tenant_id=contact.tenant_id,
            customer_id=contact.customer_id,
            name=contact.name,
            email=contact.email,
            phone=contact.phone,
            is_primary=contact.is_primary,
        )
        self._session.add(row)
        self._session.flush()
        return _to_contact(row)

    def list_for_customer(self, tenant_id: UUID, customer_id: UUID) -> list[Contact]:
        stmt = select(ContactModel).where(
            ContactModel.tenant_id == tenant_id, ContactModel.customer_id == customer_id
        )
        return [_to_contact(r) for r in self._session.scalars(stmt).all()]

    def unset_primary(self, tenant_id: UUID, customer_id: UUID) -> None:
        stmt = select(ContactModel).where(
            ContactModel.tenant_id == tenant_id,
            ContactModel.customer_id == customer_id,
            ContactModel.is_primary.is_(True),
        )
        for row in self._session.scalars(stmt).all():
            row.is_primary = False


class SqlAlchemyPropertyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, prop: Property) -> Property:
        row = PropertyModel(
            id=prop.id,
            tenant_id=prop.tenant_id,
            customer_id=prop.customer_id,
            address_line1=prop.address_line1,
            address_line2=prop.address_line2,
            city=prop.city,
            region=prop.region,
            postal_code=prop.postal_code,
            country=prop.country,
            lat=prop.lat,
            lng=prop.lng,
        )
        self._session.add(row)
        self._session.flush()
        return _to_property(row)

    def list_for_customer(self, tenant_id: UUID, customer_id: UUID) -> list[Property]:
        stmt = select(PropertyModel).where(
            PropertyModel.tenant_id == tenant_id, PropertyModel.customer_id == customer_id
        )
        return [_to_property(r) for r in self._session.scalars(stmt).all()]


class SqlAlchemyTagRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_label(self, tenant_id: UUID, label: str) -> Tag | None:
        stmt = select(TagModel).where(TagModel.tenant_id == tenant_id, TagModel.label == label)
        row = self._session.scalars(stmt).first()
        return _to_tag(row) if row else None

    def add(self, tag: Tag) -> Tag:
        row = TagModel(id=tag.id, tenant_id=tag.tenant_id, label=tag.label, color=tag.color)
        self._session.add(row)
        self._session.flush()
        return _to_tag(row)

    def attach_to_customer(self, tenant_id: UUID, customer_id: UUID, tag_id: UUID) -> None:
        existing = self._session.get(CustomerTagModel, {"customer_id": customer_id, "tag_id": tag_id})
        if existing is not None:
            return
        self._session.add(
            CustomerTagModel(tenant_id=tenant_id, customer_id=customer_id, tag_id=tag_id)
        )
        self._session.flush()

    def list_for_customer(self, tenant_id: UUID, customer_id: UUID) -> list[Tag]:
        stmt = (
            select(TagModel)
            .join(CustomerTagModel, CustomerTagModel.tag_id == TagModel.id)
            .where(
                CustomerTagModel.tenant_id == tenant_id,
                CustomerTagModel.customer_id == customer_id,
            )
        )
        return [_to_tag(r) for r in self._session.scalars(stmt).all()]


class SqlAlchemyNoteRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, note: CustomerNote) -> CustomerNote:
        row = CustomerNoteModel(
            id=note.id,
            tenant_id=note.tenant_id,
            customer_id=note.customer_id,
            author_id=note.author_id,
            body=note.body,
        )
        self._session.add(row)
        self._session.flush()
        return _to_note(row)

    def list_for_customer(
        self, tenant_id: UUID, customer_id: UUID, limit: int = 50
    ) -> list[CustomerNote]:
        stmt = (
            select(CustomerNoteModel)
            .where(
                CustomerNoteModel.tenant_id == tenant_id,
                CustomerNoteModel.customer_id == customer_id,
            )
            # id.desc() is a deterministic tiebreaker so same-timestamp rows have
            # a stable order rather than an arbitrary one.
            .order_by(CustomerNoteModel.created_at.desc(), CustomerNoteModel.id.desc())
            .limit(limit)
        )
        return [_to_note(r) for r in self._session.scalars(stmt).all()]
