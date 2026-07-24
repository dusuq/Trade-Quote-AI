"""In-memory fake repositories implementing the Protocols in
app.domain.repositories — let the application/services.py use cases be
tested with zero database, zero mocking framework, full behavioral fidelity.
"""

from __future__ import annotations

from uuid import UUID

from app.domain.entities import Contact, Customer, CustomerNote, Property, Tag


class FakeCustomerRepository:
    def __init__(self) -> None:
        self._rows: dict[UUID, Customer] = {}

    def add(self, customer: Customer) -> Customer:
        self._rows[customer.id] = customer
        return customer

    def get(self, tenant_id: UUID, customer_id: UUID) -> Customer | None:
        row = self._rows.get(customer_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return row

    def search(self, tenant_id: UUID, query: str | None, limit: int, offset: int) -> list[Customer]:
        matches = [c for c in self._rows.values() if c.tenant_id == tenant_id]
        if query:
            q = query.lower()
            matches = [
                c
                for c in matches
                if q in c.display_name.lower() or (c.company_name and q in c.company_name.lower())
            ]
        matches.sort(key=lambda c: c.created_at or 0, reverse=True)
        return matches[offset : offset + limit]

    def count(self, tenant_id: UUID, query: str | None) -> int:
        matches = [c for c in self._rows.values() if c.tenant_id == tenant_id]
        if query:
            q = query.lower()
            matches = [
                c
                for c in matches
                if q in c.display_name.lower() or (c.company_name and q in c.company_name.lower())
            ]
        return len(matches)


class FakeContactRepository:
    def __init__(self) -> None:
        self._rows: list[Contact] = []

    def add(self, contact: Contact) -> Contact:
        self._rows.append(contact)
        return contact

    def list_for_customer(self, tenant_id: UUID, customer_id: UUID) -> list[Contact]:
        return [
            c for c in self._rows if c.tenant_id == tenant_id and c.customer_id == customer_id
        ]

    def unset_primary(self, tenant_id: UUID, customer_id: UUID) -> None:
        for c in self._rows:
            if c.tenant_id == tenant_id and c.customer_id == customer_id and c.is_primary:
                c.is_primary = False


class FakePropertyRepository:
    def __init__(self) -> None:
        self._rows: list[Property] = []

    def add(self, prop: Property) -> Property:
        self._rows.append(prop)
        return prop

    def list_for_customer(self, tenant_id: UUID, customer_id: UUID) -> list[Property]:
        return [
            p for p in self._rows if p.tenant_id == tenant_id and p.customer_id == customer_id
        ]


class FakeTagRepository:
    def __init__(self) -> None:
        self._tags: dict[UUID, Tag] = {}
        self._links: set[tuple[UUID, UUID]] = set()  # (customer_id, tag_id)

    def get_by_label(self, tenant_id: UUID, label: str) -> Tag | None:
        for tag in self._tags.values():
            if tag.tenant_id == tenant_id and tag.label == label:
                return tag
        return None

    def add(self, tag: Tag) -> Tag:
        self._tags[tag.id] = tag
        return tag

    def attach_to_customer(self, tenant_id: UUID, customer_id: UUID, tag_id: UUID) -> None:
        self._links.add((customer_id, tag_id))

    def list_for_customer(self, tenant_id: UUID, customer_id: UUID) -> list[Tag]:
        tag_ids = {tid for (cid, tid) in self._links if cid == customer_id}
        return [t for t in self._tags.values() if t.id in tag_ids and t.tenant_id == tenant_id]


class FakeNoteRepository:
    def __init__(self) -> None:
        self._rows: list[tuple[int, CustomerNote]] = []
        self._seq = 0

    def add(self, note: CustomerNote) -> CustomerNote:
        # Insertion sequence is a stable tiebreaker for notes created within the
        # clock's resolution window — models "later insert sorts newer", which is
        # the real-world invariant (each note is its own request/transaction).
        self._rows.append((self._seq, note))
        self._seq += 1
        return note

    def list_for_customer(
        self, tenant_id: UUID, customer_id: UUID, limit: int = 50
    ) -> list[CustomerNote]:
        matches = [
            (seq, n)
            for (seq, n) in self._rows
            if n.tenant_id == tenant_id and n.customer_id == customer_id
        ]
        matches.sort(key=lambda pair: (pair[1].created_at, pair[0]), reverse=True)
        return [n for (_seq, n) in matches][:limit]
