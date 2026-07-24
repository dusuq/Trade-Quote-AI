"""Behavioral tests for the Customer CRM use cases — run entirely against the
in-memory fakes in tests/fakes.py, no database required.
"""

from __future__ import annotations

import uuid

import pytest

from app.application import services
from app.domain.errors import CustomerNotFoundError
from tests.fakes import (
    FakeContactRepository,
    FakeCustomerRepository,
    FakeNoteRepository,
    FakePropertyRepository,
    FakeTagRepository,
)

TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()


def _make_customer(repo: FakeCustomerRepository, tenant_id=TENANT_A, name="Acme Plumbing"):
    customer, event = services.create_customer(repo, tenant_id=tenant_id, display_name=name)
    return customer, event


class TestCreateCustomer:
    def test_creates_and_returns_domain_event(self) -> None:
        repo = FakeCustomerRepository()
        customer, event = _make_customer(repo)
        assert customer.display_name == "Acme Plumbing"
        assert customer.tenant_id == TENANT_A
        assert event.event_name == "customer.customer.created"
        assert event.payload["customerId"] == str(customer.id)
        assert event.payload["displayName"] == "Acme Plumbing"


class TestGetCustomer:
    def test_returns_customer(self) -> None:
        repo = FakeCustomerRepository()
        customer, _ = _make_customer(repo)
        found = services.get_customer(repo, tenant_id=TENANT_A, customer_id=customer.id)
        assert found.id == customer.id

    def test_raises_when_missing(self) -> None:
        repo = FakeCustomerRepository()
        with pytest.raises(CustomerNotFoundError):
            services.get_customer(repo, tenant_id=TENANT_A, customer_id=uuid.uuid4())

    def test_enforces_tenant_isolation(self) -> None:
        """A customer created under tenant A must be invisible to tenant B."""
        repo = FakeCustomerRepository()
        customer, _ = _make_customer(repo, tenant_id=TENANT_A)
        with pytest.raises(CustomerNotFoundError):
            services.get_customer(repo, tenant_id=TENANT_B, customer_id=customer.id)


class TestSearchCustomers:
    def test_filters_by_query_case_insensitively(self) -> None:
        repo = FakeCustomerRepository()
        _make_customer(repo, name="Acme Plumbing")
        _make_customer(repo, name="Bright Sparks Electric")
        results, _page, total = services.search_customers(
            repo,
            tenant_id=TENANT_A,
            query="acme",
            page=None,
            page_size=None,
            default_page_size=20,
            max_page_size=100,
        )
        assert total == 1
        assert results[0].display_name == "Acme Plumbing"

    def test_paginates(self) -> None:
        repo = FakeCustomerRepository()
        for i in range(5):
            _make_customer(repo, name=f"Customer {i}")
        results, page, total = services.search_customers(
            repo,
            tenant_id=TENANT_A,
            query=None,
            page=2,
            page_size=2,
            default_page_size=20,
            max_page_size=100,
        )
        assert total == 5
        assert len(results) == 2
        assert page.offset == 2

    def test_does_not_leak_across_tenants(self) -> None:
        repo = FakeCustomerRepository()
        _make_customer(repo, tenant_id=TENANT_A, name="Tenant A Co")
        _make_customer(repo, tenant_id=TENANT_B, name="Tenant B Co")
        results, _page, total = services.search_customers(
            repo,
            tenant_id=TENANT_A,
            query=None,
            page=None,
            page_size=None,
            default_page_size=20,
            max_page_size=100,
        )
        assert total == 1
        assert results[0].display_name == "Tenant A Co"


class TestAddProperty:
    def test_adds_property_and_emits_event(self) -> None:
        customer_repo = FakeCustomerRepository()
        property_repo = FakePropertyRepository()
        customer, _ = _make_customer(customer_repo)
        prop, event = services.add_property(
            customer_repo,
            property_repo,
            tenant_id=TENANT_A,
            customer_id=customer.id,
            address_line1="123 Main St",
        )
        assert prop.customer_id == customer.id
        assert event.event_name == "customer.property.added"
        assert event.payload["addressLine1"] == "123 Main St"

    def test_raises_when_customer_missing(self) -> None:
        customer_repo = FakeCustomerRepository()
        property_repo = FakePropertyRepository()
        with pytest.raises(CustomerNotFoundError):
            services.add_property(
                customer_repo,
                property_repo,
                tenant_id=TENANT_A,
                customer_id=uuid.uuid4(),
                address_line1="123 Main St",
            )


class TestAddContact:
    def test_setting_new_primary_demotes_previous(self) -> None:
        customer_repo = FakeCustomerRepository()
        contact_repo = FakeContactRepository()
        customer, _ = _make_customer(customer_repo)

        first = services.add_contact(
            customer_repo, contact_repo, tenant_id=TENANT_A, customer_id=customer.id,
            name="Alice", is_primary=True,
        )
        assert first.is_primary is True

        second = services.add_contact(
            customer_repo, contact_repo, tenant_id=TENANT_A, customer_id=customer.id,
            name="Bob", is_primary=True,
        )
        assert second.is_primary is True

        all_contacts = contact_repo.list_for_customer(TENANT_A, customer.id)
        primaries = [c for c in all_contacts if c.is_primary]
        assert len(primaries) == 1
        assert primaries[0].name == "Bob"

    def test_non_primary_contact_does_not_affect_existing_primary(self) -> None:
        customer_repo = FakeCustomerRepository()
        contact_repo = FakeContactRepository()
        customer, _ = _make_customer(customer_repo)

        services.add_contact(
            customer_repo, contact_repo, tenant_id=TENANT_A, customer_id=customer.id,
            name="Alice", is_primary=True,
        )
        services.add_contact(
            customer_repo, contact_repo, tenant_id=TENANT_A, customer_id=customer.id,
            name="Charlie", is_primary=False,
        )
        primaries = [c for c in contact_repo.list_for_customer(TENANT_A, customer.id) if c.is_primary]
        assert len(primaries) == 1
        assert primaries[0].name == "Alice"


class TestAddNote:
    def test_adds_note(self) -> None:
        customer_repo = FakeCustomerRepository()
        note_repo = FakeNoteRepository()
        customer, _ = _make_customer(customer_repo)
        note = services.add_note(
            customer_repo, note_repo, tenant_id=TENANT_A, customer_id=customer.id,
            body="Called to confirm appointment.",
        )
        assert note.body == "Called to confirm appointment."


class TestTagCustomer:
    def test_creates_tag_on_first_use(self) -> None:
        customer_repo = FakeCustomerRepository()
        tag_repo = FakeTagRepository()
        customer, _ = _make_customer(customer_repo)
        tag = services.tag_customer(
            customer_repo, tag_repo, tenant_id=TENANT_A, customer_id=customer.id, label="VIP"
        )
        assert tag.label == "VIP"
        assert tag_repo.list_for_customer(TENANT_A, customer.id) == [tag]

    def test_reuses_existing_tag_for_same_label(self) -> None:
        customer_repo = FakeCustomerRepository()
        tag_repo = FakeTagRepository()
        c1, _ = _make_customer(customer_repo, name="Cust 1")
        c2, _ = _make_customer(customer_repo, name="Cust 2")

        tag1 = services.tag_customer(
            customer_repo, tag_repo, tenant_id=TENANT_A, customer_id=c1.id, label="VIP"
        )
        tag2 = services.tag_customer(
            customer_repo, tag_repo, tenant_id=TENANT_A, customer_id=c2.id, label="VIP"
        )
        assert tag1.id == tag2.id  # same tag reused, not duplicated


class TestCustomerTimeline:
    def test_returns_notes_sorted_most_recent_first(self) -> None:
        customer_repo = FakeCustomerRepository()
        note_repo = FakeNoteRepository()
        customer, _ = _make_customer(customer_repo)

        services.add_note(
            customer_repo, note_repo, tenant_id=TENANT_A, customer_id=customer.id, body="First note"
        )
        services.add_note(
            customer_repo, note_repo, tenant_id=TENANT_A, customer_id=customer.id, body="Second note"
        )

        timeline = services.get_customer_timeline(
            customer_repo, note_repo, tenant_id=TENANT_A, customer_id=customer.id
        )
        assert len(timeline) == 2
        assert timeline[0].summary == "Second note"
        assert all(e.kind == "note" for e in timeline)

    def test_raises_when_customer_missing(self) -> None:
        customer_repo = FakeCustomerRepository()
        note_repo = FakeNoteRepository()
        with pytest.raises(CustomerNotFoundError):
            services.get_customer_timeline(
                customer_repo, note_repo, tenant_id=TENANT_A, customer_id=uuid.uuid4()
            )
