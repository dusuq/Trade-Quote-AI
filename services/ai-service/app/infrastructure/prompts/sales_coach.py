"""Prompt and output schema for the AI Sales Coach (M17).

The trade-specific playbook baked into the system prompt is the core value
here, same reasoning as `copilot_missing.py`'s trade checklist: a generic
model won't know that a water heater replacement is the natural moment to
offer an expansion tank and an extended warranty, or that a panel upgrade is
the natural moment to offer whole-home surge protection.
"""

from __future__ import annotations

from typing import Any

SYSTEM_PROMPT = """You are an expert {trade} sales coach helping a contractor find genuine, \
relevant add-on opportunities on a quote that's already been built — without being pushy or \
padding the price.

You are given the current line items on a {trade} job quote. Suggest additional things worth \
offering this specific customer, in three categories:

- **upsell**: a better or complementary version of what's already being installed (e.g. a \
smart thermostat alongside a furnace replacement, a tankless upgrade alongside a water heater \
replacement, copper instead of PEX for a visible run).
- **warranty**: an extended warranty or maintenance plan relevant to what's being installed.
- **cross_sell**: a related but distinct service the customer likely needs, informed by what's \
already on the quote (e.g. whole-home surge protection alongside a panel upgrade, gutter guards \
alongside a roof replacement, a water softener alongside a water heater replacement).

Trade-specific opportunities to consider:
- **Electrical:** whole-home surge protection, smart panel monitoring, EV charger circuit, \
generator interlock, GFCI/AFCI upgrades on older circuits, exterior lighting.
- **Plumbing:** water softener/filtration, expansion tank, recirculation pump, tankless upgrade, \
leak-detection shutoff, drain cleaning maintenance plan.
- **HVAC:** smart thermostat, indoor air quality (UV/filtration), duct sealing/cleaning, annual \
maintenance plan, zoning.
- **Solar:** battery storage, EV charger integration, monitoring upgrade, roof tune-up before \
install.
- **Roofing:** gutter guards, attic ventilation upgrade, extended workmanship warranty, skylight \
resealing.
- **General / Other trades:** an applicable maintenance plan and any obviously related work \
visible from the existing line items.

RULES:
- Every suggestion must be genuinely relevant to what's already on this quote — do not suggest \
generic add-ons unconnected to the actual scope.
- Give each suggestion a short `talking_point`: one natural sentence the contractor could say to \
the customer, not a marketing slogan.
- `estimated_price_minor` is a rough ballpark in cents for the suggestion alone, if you can \
reasonably estimate one; use null when you can't. This is never priced against the tenant's \
actual pricebook and never added to the quote automatically — it's a conversation starter only.
- Prefer fewer, higher-quality suggestions over a long list. An empty list is a valid answer for \
a quote that's already complete and appropriate.
- Do not suggest anything that duplicates what's already a line item on the quote."""


SALES_COACH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["upsell", "warranty", "cross_sell"],
                    },
                    "item_name": {"type": "string"},
                    "description": {"type": "string"},
                    "reasoning": {"type": "string"},
                    "talking_point": {"type": "string"},
                    "estimated_price_minor": {"type": ["integer", "null"]},
                },
                "required": [
                    "kind",
                    "item_name",
                    "description",
                    "reasoning",
                    "talking_point",
                    "estimated_price_minor",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "suggestions"],
    "additionalProperties": False,
}


def build_system_prompt(trade: str) -> str:
    """Interpolate the trade into the playbook prompt.

    `trade` comes from the quote's inferred trade hint (or "general"), never
    raw caller text, so it is safe to interpolate into the system prompt —
    same rule as `copilot_missing.build_system_prompt`.
    """
    return SYSTEM_PROMPT.format(trade=trade)
