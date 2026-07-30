"""Prompt and output schema for the rewrite copilot endpoint."""

from __future__ import annotations

from typing import Any

SYSTEM_PROMPT = """You are a professional trade proposal writer. Rewrite each piece of text to be \
clear, grammatically correct, and {tone} in tone.

RULES:
- Preserve the technical meaning — do not add, remove, or change scope.
- Fix spelling and grammar. Convert trade shorthand to full terms the first time.
- Keep it concise: a line-item description should be one sentence (two max).
- Do NOT include pricing, quantities, or units — those are separate fields.
- Return exactly one rewritten string per input, in the same order."""


REWRITE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "rewritten": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["rewritten"],
    "additionalProperties": False,
}


def build_system_prompt(tone: str, context_hint: str | None = None) -> str:
    """Interpolate the (allowlisted) tone and optional trade context.

    `tone` is constrained to a known set by the use case before it reaches
    here; `context_hint` is caller text, so it is quoted as data ("context:
    ...") rather than woven into instructions.
    """
    prompt = SYSTEM_PROMPT.format(tone=tone)
    if context_hint:
        prompt += f'\n\nTrade context for these texts (for your understanding only): "{context_hint}"'
    return prompt
