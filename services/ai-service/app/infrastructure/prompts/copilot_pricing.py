"""Prompt and output schema for the analyze-pricing copilot endpoint.

The schema deliberately asks the model for *only* what it should decide —
per-line `suggested_markup_bps` + `reasoning`, and one overall
`margin_recommendation`. Every actual number (current values, pricebook cost,
the margin math) is supplied by our own code, not trusted to the LLM (M16 plan
§Key Design Decisions #2).
"""

from __future__ import annotations

from typing import Any

SYSTEM_PROMPT = """You are an expert trade estimator reviewing a contractor's quote for pricing \
accuracy and margin health.

You are given:
1. The quote's line items with current costs, markups, and prices.
2. The tenant's pricebook prices for matched items (where available).

Your job:
- Flag items where the quoted unit cost differs significantly (>15%) from the pricebook.
- Flag items with dangerously low markup (<15% / <1500 bps) that could lose money after overhead.
- Suggest markup adjustments that align with trade standards while remaining competitive.
- Give one overall margin recommendation for the quote.

RULES:
- All money values are in minor units (cents). Do not convert to dollars.
- Markups are in basis points (10000 = 100%). Think in bps.
- Never fabricate a pricebook price. If no pricebook data is available for an item, say so and \
base your advice on the markup alone.
- Be specific: name the item, state the current vs suggested values, and explain why.
- Set suggested_markup_bps to null for any line whose pricing is already fine.
- Return one entry in `suggestions` for every line item you were given, in the same order."""


PRICING_ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "line_item_id": {"type": "string"},
                    "suggested_markup_bps": {"type": ["integer", "null"]},
                    "reasoning": {"type": "string"},
                },
                "required": ["line_item_id", "suggested_markup_bps", "reasoning"],
                "additionalProperties": False,
            },
        },
        "margin_recommendation": {"type": "string"},
    },
    "required": ["suggestions", "margin_recommendation"],
    "additionalProperties": False,
}
