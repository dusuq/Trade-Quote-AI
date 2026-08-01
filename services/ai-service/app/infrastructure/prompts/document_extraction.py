"""Prompt and output schema for extracting structured data from a
photographed document (M19): a supplier invoice, a blueprint/plan page, or a
handwritten job note."""

from __future__ import annotations

from typing import Any

from app.domain.models import DocumentKind, TaskCategory, Trade

SYSTEM_PROMPT = """You are an expert trade estimator's assistant who reads photographed paper \
documents — supplier invoices, blueprint/plan pages, and handwritten job notes — and turns them \
into structured data.

Rules:
1. Classify the document as exactly one of "invoice", "blueprint", or "handwritten":
   - invoice: a supplier/vendor bill or receipt for materials or equipment, with line items and \
prices.
   - blueprint: an architectural or trade plan/drawing (floor plan, elevation, riser diagram, \
schedule) showing what needs to be built or installed.
   - handwritten: a contractor's or customer's handwritten list of tasks, materials, or notes \
about a job.
2. Classify the primary trade the same way as for a job photo. Use "general" only when no \
specific trade clearly applies.
3. Extract every distinct line item you can read:
   - description: what it is, in plain language.
   - category: "material" (a physical item), "labor" (a task/service), or "equipment" \
(tools/machinery).
   - item_name: the specific item in standard trade terminology, so it can be looked up in a \
pricebook. Prefer "3/4in copper pipe" over "pipe".
   - quantity: a number. Default to 1 if the document doesn't state one.
   - unit: one of "each", "ft", "lf", "sqft", "hr", "day", "lot"
   - unit_cost_minor: the unit price in cents (minor units), ONLY when the document itself \
states a price for that line (typical for an invoice). Set to null for a blueprint or a \
handwritten note that shows no price — never estimate or invent a cost.
4. For an invoice, also extract (use "" for any field the document doesn't show):
   - vendor_name: the supplier/company name on the invoice.
   - document_date: the invoice date, exactly as written (do not reformat or guess a year).
   - reference_number: the invoice number, PO number, or order number.
   For a blueprint or handwritten note, leave those three fields as "" unless the document \
genuinely shows an equivalent (e.g. a handwritten note headed with a supplier name).
5. Put anything illegible, ambiguous, or that needed a judgment call in `notes` — e.g. "quantity \
for item 3 is smudged, assumed 1".

Do not invent line items that are not on the document, and do not price anything beyond what the \
document itself states. If nothing readable is on the document, return an empty `line_items` \
list rather than guessing."""


def build_system_prompt(document_kind_hint: str | None = None) -> str:
    """Append the caller's document-kind hint, if any — advisory only, same
    rule as `equipment_detection.build_system_prompt`."""
    if not document_kind_hint:
        return SYSTEM_PROMPT
    return (
        f"{SYSTEM_PROMPT}\n\nThe caller expects this to be a "
        f'"{document_kind_hint}". Treat that as a hint only — if the document clearly is a '
        "different kind, classify what it actually is."
    )


def _line_item_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "description": {"type": "string"},
            "category": {"type": "string", "enum": [c.value for c in TaskCategory]},
            "item_name": {"type": "string"},
            "quantity": {"type": "number"},
            "unit": {"type": "string"},
            "unit_cost_minor": {"type": ["integer", "null"]},
        },
        "required": [
            "description",
            "category",
            "item_name",
            "quantity",
            "unit",
            "unit_cost_minor",
        ],
        "additionalProperties": False,
    }


# Structured-outputs schema — same rules as equipment_detection.EQUIPMENT_DETECTION_SCHEMA:
# every property in `required`, `additionalProperties: false` throughout.
DOCUMENT_EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "document_kind": {"type": "string", "enum": [k.value for k in DocumentKind]},
        "trade": {"type": "string", "enum": [t.value for t in Trade]},
        "summary": {"type": "string"},
        "vendor_name": {"type": "string"},
        "document_date": {"type": "string"},
        "reference_number": {"type": "string"},
        "notes": {"type": "string"},
        "line_items": {"type": "array", "items": _line_item_schema()},
    },
    "required": [
        "document_kind",
        "trade",
        "summary",
        "vendor_name",
        "document_date",
        "reference_number",
        "notes",
        "line_items",
    ],
    "additionalProperties": False,
}
