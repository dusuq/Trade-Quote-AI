"""Prompt and output schema for the missing-items copilot endpoint.

The trade-specific checklists baked into the system prompt are the core value
of this endpoint (M16 plan §Key Design Decisions #4): a generic model won't
know that a panel upgrade needs a permit and a ground rod.
"""

from __future__ import annotations

from typing import Any

SYSTEM_PROMPT = """You are an expert {trade} estimator reviewing a quote for completeness.

You are given the current line items on a {trade} job quote. Identify materials, labor, or \
equipment that a thorough estimate would include but are missing from this list.

Trade-specific knowledge to apply:
- **Electrical:** Check for wire/conduit for every fixture, breakers for every circuit, junction \
boxes, ground rods, permits, load calculations, wall patching after rough-in.
- **Plumbing:** Check for fittings/couplings for every pipe run, shut-off valves, Teflon tape, \
pipe hangers, drain assemblies, vent pipe, water testing, permits.
- **HVAC:** Check for refrigerant charge, condensate line, thermostat wire, duct transitions, \
flue pipe, permits, startup/commissioning labor, pad/platform.
- **Solar:** Check for rail/clamps, conduit run, disconnect, grounding, roof flashing/sealant, \
monitoring hardware, permit/inspection fees.
- **Roofing:** Check for underlayment, drip edge, flashing, ridge vent, starter strip, \
tear-off/disposal, ice & water shield, nails/staples.
- **General / Other trades:** Apply common construction sense — consumables, labor for \
installation, removal/disposal, permits, cleanup.

RULES:
- Only suggest items genuinely needed for this scope — don't pad the quote.
- Assign priority: "critical" (will fail inspection or cause callback), "recommended" (standard \
practice, likely needed), "optional" (nice to have, protects against surprises).
- Provide a completeness_score (0-100): how complete the quote already is.
- Quantities are estimates — the contractor will adjust.
- Classify the trade in your response; use "general" only when no specific trade applies."""


MISSING_ITEMS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "trade": {"type": "string"},
        "completeness_score": {"type": "integer"},
        "summary": {"type": "string"},
        "missing": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": ["material", "labor", "equipment"],
                    },
                    "item_name": {"type": "string"},
                    "estimated_quantity": {"type": "number"},
                    "unit": {"type": "string"},
                    "reasoning": {"type": "string"},
                    "priority": {
                        "type": "string",
                        "enum": ["critical", "recommended", "optional"],
                    },
                },
                "required": [
                    "description",
                    "category",
                    "item_name",
                    "estimated_quantity",
                    "unit",
                    "reasoning",
                    "priority",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["trade", "completeness_score", "summary", "missing"],
    "additionalProperties": False,
}


def build_system_prompt(trade: str) -> str:
    """Interpolate the trade into the checklist prompt.

    `trade` comes from the quote's inferred trade hint (or "general"), never
    raw caller text, so it is safe to interpolate into the system prompt.
    """
    return SYSTEM_PROMPT.format(trade=trade)
