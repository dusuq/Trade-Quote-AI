"""Tests asserting that SQLAlchemy Enum column mappings configure values_callable (T206b).

Guards against missing values_callable which causes SQLAlchemy to persist Python enum .name
('MATERIAL', 'LABOR') instead of Postgres lower-case enum labels ('material', 'labor').
"""

from __future__ import annotations

from sqlalchemy import Enum

from app.domain.models import ItemKind, PricebookItemModel


def test_pricebook_item_model_kind_enum_values_callable():
    column = PricebookItemModel.__table__.columns["kind"]
    assert isinstance(column.type, Enum)
    assert column.type.values_callable is not None
    extracted_values = column.type.values_callable(ItemKind)
    assert extracted_values == [e.value for e in ItemKind]
    assert "material" in extracted_values
    assert "MATERIAL" not in extracted_values
