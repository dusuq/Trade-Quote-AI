"""Integration tests for trade seed pricebook CSV imports into pricebook-service."""

from __future__ import annotations

from pathlib import Path

from app.application import services

SEED_DIR = Path(__file__).parent.parent.parent.parent / "packages" / "seed-data" / "pricebooks"


def test_import_electrical_trade_seed(db_session, tenant_id) -> None:
    csv_path = SEED_DIR / "electrical.csv"
    assert csv_path.exists(), "Electrical seed file missing"

    csv_text = csv_path.read_text(encoding="utf-8")
    summary = services.import_items_from_csv(db_session, tenant_id, csv_text)

    assert summary["total_rows"] >= 15
    assert summary["created"] == summary["total_rows"]
    assert summary["errors"] == []


def test_import_plumbing_trade_seed(db_session, tenant_id) -> None:
    csv_path = SEED_DIR / "plumbing.csv"
    assert csv_path.exists(), "Plumbing seed file missing"

    csv_text = csv_path.read_text(encoding="utf-8")
    summary = services.import_items_from_csv(db_session, tenant_id, csv_text)

    assert summary["total_rows"] >= 15
    assert summary["created"] == summary["total_rows"]
    assert summary["errors"] == []


def test_import_hvac_trade_seed(db_session, tenant_id) -> None:
    csv_path = SEED_DIR / "hvac.csv"
    assert csv_path.exists(), "HVAC seed file missing"

    csv_text = csv_path.read_text(encoding="utf-8")
    summary = services.import_items_from_csv(db_session, tenant_id, csv_text)

    assert summary["total_rows"] >= 15
    assert summary["created"] == summary["total_rows"]
    assert summary["errors"] == []
