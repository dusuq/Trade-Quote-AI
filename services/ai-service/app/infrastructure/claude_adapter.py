"""Anthropic Claude adapters for scope extraction and scope writing.

The only place the Anthropic SDK is imported. Everything above this layer
talks to `ScopeExtractor` / `ScopeNarrator`, so no test needs an API key.
"""

from __future__ import annotations

import json
from typing import Any

import anthropic

from app.application.line_items import normalize_quantity
from app.domain.errors import ScopeExtractionError
from app.domain.models import (
    AiFeature,
    AiUsage,
    ExtractedScope,
    ExtractedTask,
    TaskCategory,
    Trade,
)
from app.infrastructure.costs import estimate_token_cost_minor
from app.infrastructure.prompts import scope_extraction, scope_writer

_MAX_TOKENS_EXTRACTION = 8_000
_MAX_TOKENS_SCOPE_TEXT = 2_000


def _text_of(response: Any) -> str:
    """Concatenate the text blocks of a Messages API response.

    `stop_reason` is checked first: on a refusal the content array is empty or
    partial, so indexing into it would raise something unhelpful instead of
    reporting what actually happened.
    """
    if getattr(response, "stop_reason", None) == "refusal":
        raise ScopeExtractionError(
            "the model declined to process this request; try rephrasing the description"
        )
    parts = [block.text for block in response.content if getattr(block, "type", None) == "text"]
    if not parts:
        raise ScopeExtractionError("the model returned no text content")
    return "".join(parts)


def _usage_from(response: Any, model_id: str, feature: AiFeature) -> AiUsage:
    input_tokens = int(getattr(response.usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(response.usage, "output_tokens", 0) or 0)
    return AiUsage(
        feature=feature,
        model_id=model_id,
        input_kind="text",
        tokens_used=input_tokens + output_tokens,
        cost_minor=estimate_token_cost_minor(model_id, input_tokens, output_tokens),
        metadata={"input_tokens": input_tokens, "output_tokens": output_tokens},
    )


def parse_scope(payload: dict[str, Any]) -> ExtractedScope:
    """Map the model's JSON into domain types, validating as we go.

    Structured outputs constrain the *shape*, not the semantics — a quantity
    of 0 or -1 satisfies `{"type": "number"}` but is not a line item anyone
    can bill, so it is rejected here rather than sent on to quote-service.
    """
    try:
        trade = Trade(payload["trade"])
        raw_tasks = payload["tasks"]
    except (KeyError, ValueError) as exc:
        raise ScopeExtractionError(f"model returned an unusable scope: {exc}") from exc

    if not isinstance(raw_tasks, list):
        raise ScopeExtractionError("model returned a non-list `tasks` field")

    tasks: list[ExtractedTask] = []
    for index, raw in enumerate(raw_tasks):
        try:
            tasks.append(
                ExtractedTask(
                    description=str(raw["description"]).strip(),
                    category=TaskCategory(raw["category"]),
                    item_name=str(raw["item_name"]).strip(),
                    quantity=normalize_quantity(raw["quantity"]),
                    unit=str(raw["unit"]).strip() or "each",
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ScopeExtractionError(f"task {index} is unusable: {exc}") from exc

    return ExtractedScope(
        trade=trade,
        summary=str(payload.get("summary", "")).strip(),
        tasks=tuple(tasks),
        notes=str(payload.get("notes", "") or "").strip(),
    )


class _ClaudeBase:
    def __init__(self, api_key: str, model: str, client: Any | None = None) -> None:
        self._api_key = api_key
        self._model = model
        self._client = client

    def _require_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise ScopeExtractionError(
                "ANTHROPIC_API_KEY is not configured; AI features are unavailable"
            )
        self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client


class ClaudeScopeExtractor(_ClaudeBase):
    """Implements `ScopeExtractor` using the Messages API with structured outputs."""

    def extract_scope(
        self, text: str, trade_hint: str | None = None
    ) -> tuple[ExtractedScope, AiUsage]:
        client = self._require_client()
        response = client.messages.create(
            model=self._model,
            max_tokens=_MAX_TOKENS_EXTRACTION,
            system=scope_extraction.build_system_prompt(trade_hint),
            # Constrains the response to the schema, so no prompt-level
            # "reply with JSON only" pleading and no brace-counting parser.
            output_config={
                "format": {"type": "json_schema", "schema": scope_extraction.SCOPE_SCHEMA}
            },
            messages=[{"role": "user", "content": text}],
        )

        raw = _text_of(response)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ScopeExtractionError(f"model returned malformed JSON: {exc}") from exc

        scope = parse_scope(payload)
        return scope, _usage_from(response, self._model, AiFeature.VOICE)


class ClaudeScopeNarrator(_ClaudeBase):
    """Implements `ScopeNarrator` — structured scope to customer-facing prose."""

    def write_scope(self, scope: ExtractedScope, tone: str) -> tuple[str, AiUsage]:
        client = self._require_client()
        task_lines = "\n".join(
            f"- {task.description} ({task.category.value}, {task.quantity} {task.unit})"
            for task in scope.tasks
        )
        user_content = (
            f"Trade: {scope.trade.value}\n"
            f"Summary: {scope.summary}\n"
            f"Tasks:\n{task_lines}\n"
            f"Notes: {scope.notes or 'none'}"
        )

        response = client.messages.create(
            model=self._model,
            max_tokens=_MAX_TOKENS_SCOPE_TEXT,
            system=scope_writer.build_system_prompt(tone),
            messages=[{"role": "user", "content": user_content}],
        )
        return _text_of(response).strip(), _usage_from(
            response, self._model, AiFeature.SCOPE_WRITER
        )
