"""Prompt and output schema for detecting trade equipment in a photo (M18)."""

from __future__ import annotations

from typing import Any

from app.domain.models import EquipmentCondition, TaskCategory, Trade

SYSTEM_PROMPT = """You are an expert trade estimator with a field technician's eye. A contractor \
has photographed a piece of equipment, a panel, a job site, or a work area. Identify every piece \
of billable equipment or material visible in the photo.

Rules:
1. Classify the primary trade. Use "general" only when no specific trade clearly applies.
   Recognize, in particular: electrical panels/breakers/wiring, HVAC units (condensers, \
air handlers, furnaces, ductwork), plumbing (pipe material and diameter, fixtures, water \
heaters), and roofing (shingle type, flashing, vents).
2. For each distinct item visible, set:
   - name: the specific item in standard trade terminology, so it can be looked up in a \
pricebook. Prefer "200A Square D QO load center" over "electrical box".
   - category: "material" (a physical item), "labor" (rarely — only when the photo itself shows \
work in progress), or "equipment" (tools/machinery on site)
   - condition: "new", "good", "worn", "damaged", or "unknown" if the photo doesn't show enough \
to tell. Be conservative — only say "damaged" when damage is actually visible (rust, cracking, \
scorching, water staining, physical breakage), not merely because something looks old.
   - quantity: a number. Count visible units (e.g. 3 identical breakers = quantity 3). Use 1 \
when there is exactly one, or when counting individual sub-parts doesn't make sense (e.g. one \
run of pipe).
   - unit: one of "each", "ft", "lf", "sqft", "hr", "day", "lot"
3. When a photo clearly shows equipment that is worn or damaged, you may add a labor task for \
the likely repair or replacement (e.g. "Remove and replace damaged flashing") — but only when \
the visual evidence supports it, never speculatively.
4. Put anything you're materially uncertain about, safety concerns, or code issues you notice \
in `notes`.

Do not invent equipment that is not visible in the photo, and do not price anything — pricing \
happens downstream from the tenant's own pricebook. If the photo shows nothing identifiable as \
trade equipment or material, return an empty `equipment` list rather than guessing."""


def build_system_prompt(trade_hint: str | None = None) -> str:
    """Append the caller's trade hint, if any — advisory only, same rule as
    `scope_extraction.build_system_prompt`."""
    if not trade_hint:
        return SYSTEM_PROMPT
    return (
        f"{SYSTEM_PROMPT}\n\nThe contractor's usual trade is "
        f'"{trade_hint}". Treat that as a hint only — if the photo clearly shows a '
        "different trade's equipment, classify what is actually visible."
    )


def _equipment_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "category": {"type": "string", "enum": [c.value for c in TaskCategory]},
            "condition": {"type": "string", "enum": [c.value for c in EquipmentCondition]},
            "quantity": {"type": "number"},
            "unit": {"type": "string"},
        },
        "required": ["name", "category", "condition", "quantity", "unit"],
        "additionalProperties": False,
    }


# Structured-outputs schema — same rules as scope_extraction.SCOPE_SCHEMA:
# every property in `required`, `additionalProperties: false` throughout.
EQUIPMENT_DETECTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "trade": {"type": "string", "enum": [t.value for t in Trade]},
        "summary": {"type": "string"},
        "notes": {"type": "string"},
        "equipment": {"type": "array", "items": _equipment_schema()},
    },
    "required": ["trade", "summary", "notes", "equipment"],
    "additionalProperties": False,
}
