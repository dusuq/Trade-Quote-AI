"""Anthropic Claude adapters for the copilot (T202).

Like `claude_adapter`, this is the only place the Anthropic SDK is touched for
these features — everything above talks to the `CopilotAnalyzer` /
`TextRewriter` ports, so no test needs an API key.

The margin numbers are NOT asked of the model: `analyze_pricing` computes them
with the pure functions in `application/margin.py` and lets the LLM contribute
only per-line markup suggestions and prose (M16 plan §Key Design Decisions #2).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal
from typing import Any
from uuid import UUID

import anthropic

from app.application.line_items import normalize_quantity
from app.application.margin import compute_margin
from app.domain.errors import CopilotAnalysisError
from app.domain.models import (
    AiFeature,
    AiUsage,
    MissingItem,
    MissingItemsResult,
    PricebookMatch,
    PricingAnalysisResult,
    PricingSuggestion,
    QuoteSnapshot,
    Trade,
)
from app.infrastructure.costs import estimate_token_cost_minor
from app.infrastructure.prompts import copilot_missing, copilot_pricing, copilot_rewrite

_MAX_TOKENS_PRICING = 4_000
_MAX_TOKENS_MISSING = 4_000
_MAX_TOKENS_REWRITE = 4_000


def _text_of(response: Any) -> str:
    """Concatenate the text blocks of a Messages API response.

    Mirrors `claude_adapter._text_of` but raises `CopilotAnalysisError` so the
    copilot routes map a model refusal to 422, not the assistant's error type.
    """
    if getattr(response, "stop_reason", None) == "refusal":
        raise CopilotAnalysisError(
            "the model declined to process this request; try rephrasing"
        )
    parts = [block.text for block in response.content if getattr(block, "type", None) == "text"]
    if not parts:
        raise CopilotAnalysisError("the model returned no text content")
    return "".join(parts)


def _usage_from(response: Any, model_id: str) -> AiUsage:
    input_tokens = int(getattr(response.usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(response.usage, "output_tokens", 0) or 0)
    return AiUsage(
        feature=AiFeature.COPILOT,
        model_id=model_id,
        input_kind="text",
        tokens_used=input_tokens + output_tokens,
        cost_minor=estimate_token_cost_minor(model_id, input_tokens, output_tokens),
        metadata={"input_tokens": input_tokens, "output_tokens": output_tokens},
    )


def _loads(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CopilotAnalysisError(f"model returned malformed JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise CopilotAnalysisError("model returned a non-object JSON body")
    return payload


def _estimate_quantity(value: object) -> Decimal:
    """Coerce an LLM-estimated quantity to Decimal, defaulting to 1.

    A missing-item quantity is a soft estimate the contractor will adjust, so a
    zero or unparseable value shouldn't fail the whole analysis — it becomes 1.
    """
    try:
        return normalize_quantity(value)
    except ValueError:
        return Decimal(1)


# ── Pure parsers (tested directly, no SDK) ───────────────────────────────────


def parse_pricing_suggestions(
    payload: dict[str, Any],
    quote: QuoteSnapshot,
    matches: Mapping[UUID, PricebookMatch],
) -> tuple[tuple[PricingSuggestion, ...], str]:
    """Merge the model's per-line advice with our own current + pricebook data.

    One suggestion is emitted for every line in the quote, in quote order —
    the model is trusted only for `suggested_markup_bps` and `reasoning`.
    """
    raw_suggestions = payload.get("suggestions", [])
    if not isinstance(raw_suggestions, list):
        raise CopilotAnalysisError("model returned a non-list `suggestions` field")

    by_id: dict[UUID, dict[str, Any]] = {}
    for raw in raw_suggestions:
        if not isinstance(raw, dict):
            continue
        try:
            by_id[UUID(str(raw["line_item_id"]))] = raw
        except (KeyError, ValueError):
            continue

    suggestions: list[PricingSuggestion] = []
    for item in quote.line_items:
        advice = by_id.get(item.id)
        suggested_markup: int | None = None
        reasoning = ""
        if advice is not None:
            raw_markup = advice.get("suggested_markup_bps")
            suggested_markup = int(raw_markup) if raw_markup is not None else None
            reasoning = str(advice.get("reasoning", "")).strip()
        match = matches.get(item.id)
        suggestions.append(
            PricingSuggestion(
                line_item_id=item.id,
                current_unit_cost_minor=item.unit_cost_minor,
                current_markup_bps=item.markup_bps,
                current_unit_price_minor=item.unit_price_minor,
                # MVP suggests a markup change, never a cost change: the cost is
                # the contractor's real supplier price, not ours to override.
                suggested_unit_cost_minor=None,
                suggested_markup_bps=suggested_markup,
                pricebook_unit_cost_minor=match.unit_cost_minor if match else None,
                reasoning=reasoning,
            )
        )

    recommendation = str(payload.get("margin_recommendation", "")).strip()
    return tuple(suggestions), recommendation


def parse_missing_items(
    payload: dict[str, Any], *, model_id: str, tokens_used: int
) -> MissingItemsResult:
    raw_missing = payload.get("missing", [])
    if not isinstance(raw_missing, list):
        raise CopilotAnalysisError("model returned a non-list `missing` field")

    try:
        trade = Trade(payload["trade"])
    except (KeyError, ValueError):
        # The model may name a trade we don't bucket; "general" keeps the
        # per-trade analytics honest rather than inventing a one-off bucket.
        trade = Trade.GENERAL

    items: list[MissingItem] = []
    for index, raw in enumerate(raw_missing):
        try:
            items.append(
                MissingItem(
                    description=str(raw["description"]).strip(),
                    category=str(raw["category"]).strip(),
                    item_name=str(raw["item_name"]).strip(),
                    estimated_quantity=_estimate_quantity(raw.get("estimated_quantity")),
                    unit=str(raw.get("unit") or "each").strip(),
                    reasoning=str(raw.get("reasoning", "")).strip(),
                    priority=str(raw["priority"]).strip(),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CopilotAnalysisError(f"missing item {index} is unusable: {exc}") from exc

    raw_score = payload.get("completeness_score", 0)
    try:
        score = max(0, min(100, int(raw_score)))
    except (TypeError, ValueError):
        score = 0

    return MissingItemsResult(
        missing=tuple(items),
        trade=trade,
        completeness_score=score,
        summary=str(payload.get("summary", "")).strip(),
        model_id=model_id,
        tokens_used=tokens_used,
    )


def parse_rewrite(payload: dict[str, Any], *, expected_count: int) -> list[str]:
    raw = payload.get("rewritten")
    if not isinstance(raw, list):
        raise CopilotAnalysisError("model did not return a `rewritten` list")
    rewritten = [str(text) for text in raw]
    if len(rewritten) != expected_count:
        # A count mismatch means the 1:1 contract is broken — returning it
        # anyway would silently misalign descriptions with their line items.
        raise CopilotAnalysisError(
            f"model returned {len(rewritten)} texts for {expected_count} inputs"
        )
    return rewritten


# ── User-content builders ─────────────────────────────────────────────────────


def _pricing_user_content(
    quote: QuoteSnapshot, matches: Mapping[UUID, PricebookMatch]
) -> str:
    lines = []
    for item in quote.line_items:
        match = matches.get(item.id)
        pricebook = (
            f"{match.unit_cost_minor} minor" if match is not None else "n/a"
        )
        lines.append(
            f"- line_item_id={item.id} | {item.description} | "
            f"qty {item.quantity} {item.unit} | unit_cost {item.unit_cost_minor} minor | "
            f"markup {item.markup_bps} bps | unit_price {item.unit_price_minor} minor | "
            f"line_total {item.line_total_minor} minor | pricebook_unit_cost {pricebook}"
        )
    body = "\n".join(lines)
    return (
        f"Currency: {quote.currency}\n"
        f"Line items:\n{body}\n"
        f"Quote subtotal (excl. tax): {quote.subtotal_minor} minor"
    )


def _missing_user_content(quote: QuoteSnapshot, job_description: str | None) -> str:
    if quote.line_items:
        lines = "\n".join(
            f"- {item.description} | {item.kind} | qty {item.quantity} {item.unit}"
            for item in quote.line_items
        )
    else:
        lines = "(the quote currently has no line items)"
    return (
        f"Trade hint: {quote.trade_hint or 'unknown'}\n"
        f"Current line items:\n{lines}\n"
        f"Original job description: {job_description or 'none provided'}"
    )


def _rewrite_user_content(texts: list[str]) -> str:
    numbered = "\n".join(f"{index + 1}. {text}" for index, text in enumerate(texts))
    return f"Rewrite these {len(texts)} texts, returning exactly {len(texts)}:\n{numbered}"


# ── Adapters ──────────────────────────────────────────────────────────────────


class _ClaudeBase:
    def __init__(self, api_key: str, model: str, client: Any | None = None) -> None:
        self._api_key = api_key
        self._model = model
        self._client = client

    def _require_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise CopilotAnalysisError(
                "ANTHROPIC_API_KEY is not configured; AI features are unavailable"
            )
        self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client


class ClaudeCopilotAnalyzer(_ClaudeBase):
    """Implements `CopilotAnalyzer` using Claude (Sonnet 5) structured outputs."""

    def analyze_pricing(
        self, quote: QuoteSnapshot, pricebook_matches: Mapping[UUID, PricebookMatch]
    ) -> tuple[PricingAnalysisResult, AiUsage]:
        client = self._require_client()
        response = client.messages.create(
            model=self._model,
            max_tokens=_MAX_TOKENS_PRICING,
            system=copilot_pricing.SYSTEM_PROMPT,
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": copilot_pricing.PRICING_ANALYSIS_SCHEMA,
                }
            },
            messages=[
                {"role": "user", "content": _pricing_user_content(quote, pricebook_matches)}
            ],
        )
        payload = _loads(_text_of(response))
        suggestions, recommendation = parse_pricing_suggestions(
            payload, quote, pricebook_matches
        )
        usage = _usage_from(response, self._model)
        result = PricingAnalysisResult(
            suggestions=suggestions,
            # The numbers are ours; only the recommendation prose is the model's.
            margin=compute_margin(quote, recommendation),
            model_id=self._model,
            tokens_used=usage.tokens_used,
        )
        return result, usage

    def find_missing_items(
        self, quote: QuoteSnapshot, job_description: str | None = None
    ) -> tuple[MissingItemsResult, AiUsage]:
        client = self._require_client()
        response = client.messages.create(
            model=self._model,
            max_tokens=_MAX_TOKENS_MISSING,
            system=copilot_missing.build_system_prompt(quote.trade_hint or "general"),
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": copilot_missing.MISSING_ITEMS_SCHEMA,
                }
            },
            messages=[
                {"role": "user", "content": _missing_user_content(quote, job_description)}
            ],
        )
        payload = _loads(_text_of(response))
        usage = _usage_from(response, self._model)
        result = parse_missing_items(
            payload, model_id=self._model, tokens_used=usage.tokens_used
        )
        return result, usage


class ClaudeTextRewriter(_ClaudeBase):
    """Implements `TextRewriter` using Claude (Sonnet 5)."""

    def rewrite(
        self, texts: list[str], tone: str, context_hint: str | None = None
    ) -> tuple[list[str], AiUsage]:
        client = self._require_client()
        response = client.messages.create(
            model=self._model,
            max_tokens=_MAX_TOKENS_REWRITE,
            system=copilot_rewrite.build_system_prompt(tone, context_hint),
            output_config={
                "format": {"type": "json_schema", "schema": copilot_rewrite.REWRITE_SCHEMA}
            },
            messages=[{"role": "user", "content": _rewrite_user_content(texts)}],
        )
        payload = _loads(_text_of(response))
        rewritten = parse_rewrite(payload, expected_count=len(texts))
        return rewritten, _usage_from(response, self._model)
