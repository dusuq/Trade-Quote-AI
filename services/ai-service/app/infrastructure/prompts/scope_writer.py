"""Prompt for generating customer-facing scope-of-work prose."""

from __future__ import annotations

SYSTEM_PROMPT = """You are a professional trade proposal writer. Given a structured scope of work, \
write the scope-of-work section of a proposal that a homeowner will read.

Rules:
- Write in a {tone} tone.
- Cover what work will be done and the key materials involved.
- Mention permits, access requirements, or conditions the customer needs to know about.
- Do NOT include any pricing, costs, or totals. Pricing lives elsewhere in the proposal.
- Do NOT invent work that isn't in the scope you were given.
- 2-4 short paragraphs. No headings, no bullet lists, no preamble — return only the prose."""


def build_system_prompt(tone: str) -> str:
    """Interpolate the tone.

    `tone` is constrained to an allowlist by the use case before it reaches
    here (`application/scope_writer.normalize_tone`) — it is caller-supplied
    text going into a system prompt, so it must not be free-form.
    """
    return SYSTEM_PROMPT.format(tone=tone)
