"""Anthropic Claude adapter for the AI Sales Coach (T306 / M17).

Like `copilot_claude_adapter`, this is the only place the Anthropic SDK is
touched for this feature — everything above talks to the `SalesCoachAnalyzer`
port, so no test needs an API key.
"""

from __future__ import annotations

import json
from typing import Any

import anthropic

from app.domain.errors import SalesCoachError
from app.domain.models import (
    AiFeature,
    AiUsage,
    QuoteSnapshot,
    SalesCoachResult,
    SalesSuggestion,
    SalesSuggestionKind,
)
from app.infrastructure.costs import estimate_token_cost_minor
from app.infrastructure.prompts import sales_coach

_MAX_TOKENS_SALES_COACH = 4_000


def _text_of(response: Any) -> str:
    """Concatenate the text blocks of a Messages API response.

    Mirrors `copilot_claude_adapter._text_of`: a refusal maps to
    `SalesCoachError` so the route surfaces 422, not the assistant's
    internal error type.
    """
    if getattr(response, "stop_reason", None) == "refusal":
        raise SalesCoachError("the model declined to process this request; try rephrasing")
    parts = [block.text for block in response.content if getattr(block, "type", None) == "text"]
    if not parts:
        raise SalesCoachError("the model returned no text content")
    return "".join(parts)


def _usage_from(response: Any, model_id: str) -> AiUsage:
    input_tokens = int(getattr(response.usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(response.usage, "output_tokens", 0) or 0)
    return AiUsage(
        feature=AiFeature.SALES_COACH,
        model_id=model_id,
        input_kind="text",
        tokens_used=input_tokens + output_tokens,
        cost_minor=estimate_token_cost_minor(model_id, input_tokens, output_tokens),
        metadata={"input_tokens": input_tokens, "output_tokens": output_tokens},
    )


def parse_sales_coach(
    payload: dict[str, Any], *, model_id: str, tokens_used: int
) -> SalesCoachResult:
    """Map the model's JSON into domain types, validating as we go.

    Mirrors `copilot_claude_adapter.parse_missing_items`: structured outputs
    constrain shape, not semantics, so an unknown `kind` is rejected here
    even though the schema's enum should already have excluded it.
    """
    raw_suggestions = payload.get("suggestions", [])
    if not isinstance(raw_suggestions, list):
        raise SalesCoachError("model returned a non-list `suggestions` field")

    suggestions: list[SalesSuggestion] = []
    for index, raw in enumerate(raw_suggestions):
        try:
            raw_price = raw.get("estimated_price_minor")
            suggestions.append(
                SalesSuggestion(
                    kind=SalesSuggestionKind(raw["kind"]),
                    item_name=str(raw["item_name"]).strip(),
                    description=str(raw["description"]).strip(),
                    reasoning=str(raw["reasoning"]).strip(),
                    talking_point=str(raw["talking_point"]).strip(),
                    estimated_price_minor=int(raw_price) if raw_price is not None else None,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SalesCoachError(f"suggestion {index} is unusable: {exc}") from exc

    return SalesCoachResult(
        suggestions=tuple(suggestions),
        summary=str(payload.get("summary", "")).strip(),
        model_id=model_id,
        tokens_used=tokens_used,
    )


def _user_content(quote: QuoteSnapshot) -> str:
    if quote.line_items:
        lines = "\n".join(
            f"- {item.description} | {item.kind} | qty {item.quantity} {item.unit} | "
            f"unit_price {item.unit_price_minor} minor"
            for item in quote.line_items
        )
    else:
        lines = "(the quote currently has no line items)"
    return (
        f"Trade hint: {quote.trade_hint or 'unknown'}\n"
        f"Currency: {quote.currency}\n"
        f"Current line items:\n{lines}\n"
        f"Quote subtotal (excl. tax): {quote.subtotal_minor} minor"
    )


class ClaudeSalesCoachAnalyzer:
    """Implements `SalesCoachAnalyzer` using Claude (Sonnet 5) structured
    outputs — same tier as the rest of the copilot family: advisory prose and
    suggestions, not schema-critical output feeding real line items."""

    def __init__(self, api_key: str, model: str, client: Any | None = None) -> None:
        self._api_key = api_key
        self._model = model
        self._client = client

    def _require_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise SalesCoachError(
                "ANTHROPIC_API_KEY is not configured; AI Sales Coach is unavailable"
            )
        self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def suggest(self, quote: QuoteSnapshot) -> tuple[SalesCoachResult, AiUsage]:
        client = self._require_client()
        response = client.messages.create(
            model=self._model,
            max_tokens=_MAX_TOKENS_SALES_COACH,
            system=sales_coach.build_system_prompt(quote.trade_hint or "general"),
            output_config={
                "format": {"type": "json_schema", "schema": sales_coach.SALES_COACH_SCHEMA}
            },
            messages=[{"role": "user", "content": _user_content(quote)}],
        )
        payload_raw = _text_of(response)
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError as exc:
            raise SalesCoachError(f"model returned malformed JSON: {exc}") from exc

        usage = _usage_from(response, self._model)
        result = parse_sales_coach(payload, model_id=self._model, tokens_used=usage.tokens_used)
        return result, usage
