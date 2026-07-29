"""Prompt and output schema for turning a job description into a structured scope."""

from __future__ import annotations

from typing import Any

from app.domain.models import TaskCategory, Trade

SYSTEM_PROMPT = """You are an expert trade estimator assistant. A contractor has described a job \
— either typed, or transcribed from speech, so expect informal phrasing, filler words, and \
transcription errors. Extract the billable scope.

Rules:
1. Classify the primary trade. Use "general" only when no specific trade clearly applies.
2. Break the job into individual tasks. Each task is one billable line item.
3. For each task set:
   - category: "material" (a physical item), "labor" (work time), or "equipment" (tools/machinery)
   - item_name: the specific item or service, in standard trade terminology, so it can be looked \
up in a pricebook. Prefer "200A main breaker panel" over "the panel he mentioned".
   - quantity: a number. Use 1 when the contractor didn't say.
   - unit: one of "each", "ft", "lf", "sqft", "hr", "day", "lot"
4. Add the labor to install or remove something whenever materials are mentioned and labor is \
implied — a contractor saying "replace the panel" is billing for the work as well as the part.
5. Include standard consumables (wire, fittings, connectors) where the trade would normally \
bill them.
6. Put permit requirements, safety concerns, and anything ambiguous in `notes`.

Do not invent work that was not described, and do not price anything — pricing happens \
downstream from the tenant's own pricebook. Extract only what the contractor actually said."""


def build_system_prompt(trade_hint: str | None = None) -> str:
    """Append the caller's trade hint, if any.

    The hint is advisory: a contractor's account may be set to "electrical"
    while a given job is plumbing, so the model is told to override it when
    the description disagrees.
    """
    if not trade_hint:
        return SYSTEM_PROMPT
    return (
        f"{SYSTEM_PROMPT}\n\nThe contractor's usual trade is "
        f'"{trade_hint}". Treat that as a hint only — if the description is clearly '
        "a different trade, classify what was actually described."
    )


def _task_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "description": {"type": "string"},
            "category": {"type": "string", "enum": [c.value for c in TaskCategory]},
            "item_name": {"type": "string"},
            "quantity": {"type": "number"},
            "unit": {"type": "string"},
        },
        "required": ["description", "category", "item_name", "quantity", "unit"],
        "additionalProperties": False,
    }


# Structured-outputs schema. Every property must appear in `required` and
# `additionalProperties` must be false — the API rejects schemas otherwise.
# `notes` is a plain string ("" when there's nothing to say) rather than a
# nullable, which keeps the schema inside the supported subset.
SCOPE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "trade": {"type": "string", "enum": [t.value for t in Trade]},
        "summary": {"type": "string"},
        "notes": {"type": "string"},
        "tasks": {"type": "array", "items": _task_schema()},
    },
    "required": ["trade", "summary", "notes", "tasks"],
    "additionalProperties": False,
}
