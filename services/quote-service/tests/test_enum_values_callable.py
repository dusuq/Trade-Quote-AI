"""Tests asserting that SQLAlchemy Enum column mappings configure values_callable (T206b).

Guards against missing values_callable which causes SQLAlchemy to persist Python enum .name
('SENT', 'ACCEPTED') instead of Postgres lower-case enum labels ('sent', 'accepted').
"""

from __future__ import annotations

from sqlalchemy import Enum

from app.domain.models import ItemKind, QuoteCreatedVia, QuoteLineItemModel, QuoteModel, QuoteStatus


def test_quote_model_status_enum_values_callable():
    column = QuoteModel.__table__.columns["status"]
    assert isinstance(column.type, Enum)
    assert column.type.values_callable is not None
    extracted_values = column.type.values_callable(QuoteStatus)
    assert extracted_values == [e.value for e in QuoteStatus]
    assert "sent" in extracted_values
    assert "SENT" not in extracted_values


def test_quote_model_created_via_enum_values_callable():
    column = QuoteModel.__table__.columns["created_via"]
    assert isinstance(column.type, Enum)
    assert column.type.values_callable is not None
    extracted_values = column.type.values_callable(QuoteCreatedVia)
    assert extracted_values == [e.value for e in QuoteCreatedVia]
    assert "manual" in extracted_values
    assert "MANUAL" not in extracted_values


def test_quote_line_item_model_kind_enum_values_callable():
    column = QuoteLineItemModel.__table__.columns["kind"]
    assert isinstance(column.type, Enum)
    assert column.type.values_callable is not None
    extracted_values = column.type.values_callable(ItemKind)
    assert extracted_values == [e.value for e in ItemKind]
    assert "material" in extracted_values
    assert "MATERIAL" not in extracted_values
