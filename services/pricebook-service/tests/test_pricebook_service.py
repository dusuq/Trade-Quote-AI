"""Unit and integration tests for pricebook-service domain logic & REST API."""

from __future__ import annotations

import pytest

from app.application import services
from app.application.services import DuplicateSKUError
from app.domain.models import ItemKind
from app.interface.schemas import PricebookItemCreate, PricebookItemUpdate


def test_create_and_get_pricebook_item(db_session, tenant_id):
    create_dto = PricebookItemCreate(
        kind=ItemKind.MATERIAL,
        sku="COP-WIRE-122",
        name="Copper Wire 12/2 AWG 100ft",
        description="Non-metallic jacketed cable",
        unit="roll",
        unit_cost_minor=8500,  # $85.00
        default_markup_bps=2500,  # 25% markup
        currency="USD",
    )

    item, event = services.create_item(db_session, tenant_id, create_dto)

    assert item.id is not None
    assert item.tenant_id == tenant_id
    assert item.sku == "COP-WIRE-122"
    assert item.unit_cost_minor == 8500
    assert item.default_markup_bps == 2500

    # Verify event structure
    assert event["eventName"] == "pricebook.item.upserted"
    assert event["tenantId"] == str(tenant_id)
    assert event["payload"]["unitCost"]["amountMinor"] == 8500

    # Test retrieval
    fetched = services.get_item(db_session, tenant_id, item.id)
    assert fetched.name == "Copper Wire 12/2 AWG 100ft"


def test_duplicate_sku_raises_error(db_session, tenant_id):
    create_dto = PricebookItemCreate(
        kind=ItemKind.EQUIPMENT,
        sku="PANEL-200A",
        name="200A Main Breaker Panel",
        unit_cost_minor=15000,
    )
    services.create_item(db_session, tenant_id, create_dto)

    with pytest.raises(DuplicateSKUError):
        services.create_item(db_session, tenant_id, create_dto)


def test_regional_price_override_calculation(db_session, tenant_id):
    create_dto = PricebookItemCreate(
        kind=ItemKind.LABOR,
        sku="LABOR-ELEC-JOURNEY",
        name="Journeyman Electrician Labor",
        unit="hour",
        unit_cost_minor=6500,  # $65/hr base cost
        default_markup_bps=3000,  # 30% markup
    )
    item, _ = services.create_item(db_session, tenant_id, create_dto)

    # Base price calculation: $65 * 1.30 = $84.50 (8450 minor units)
    base_calc = services.get_effective_price(db_session, tenant_id, item.id)
    assert base_calc.unit_cost_minor == 6500
    assert base_calc.calculated_price_minor == 8450
    assert base_calc.region_code is None

    # Set regional override for California (US-CA) -> $85/hr base cost
    services.set_region_price(db_session, tenant_id, item.id, "US-CA", 8500)

    # Regional price calculation: $85 * 1.30 = $110.50 (11050 minor units)
    ca_calc = services.get_effective_price(db_session, tenant_id, item.id, region_code="US-CA")
    assert ca_calc.unit_cost_minor == 8500
    assert ca_calc.calculated_price_minor == 11050
    assert ca_calc.region_code == "US-CA"


def test_csv_import(db_session, tenant_id):
    csv_data = """kind,name,sku,description,unit,unit_cost_minor,default_markup_bps,currency
material,Romex 14/2 250ft,ROMEX-142,14/2 Wire,roll,12000,2000,USD
labor,Apprentice Hourly,LAB-APP,,hour,3500,2500,USD
package,Standard Outlet Swap,PKG-OUTLET,Swap 15A outlet,package,4500,5000,USD
"""
    summary = services.import_items_from_csv(db_session, tenant_id, csv_data)

    assert summary["total_rows"] == 3
    assert summary["created"] == 3
    assert summary["updated"] == 0
    assert len(summary["errors"]) == 0

    items = services.list_items(db_session, tenant_id)
    assert len(items) == 3


def test_update_and_delete_item(db_session, tenant_id):
    item, _ = services.create_item(
        db_session,
        tenant_id,
        PricebookItemCreate(kind=ItemKind.CONSUMABLE, name="Wire Nuts Red 100pk", unit_cost_minor=1200),
    )

    updated, _ = services.update_item(
        db_session,
        tenant_id,
        item.id,
        PricebookItemUpdate(name="Wire Nuts Red 100pk (Ideal)", unit_cost_minor=1350),
    )
    assert updated.name == "Wire Nuts Red 100pk (Ideal)"
    assert updated.unit_cost_minor == 1350

    services.delete_item(db_session, tenant_id, item.id)
    fetched = services.get_item(db_session, tenant_id, item.id)
    assert fetched.is_active is False
