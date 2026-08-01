"""Anthropic Claude document-extraction adapter (M19 / T305).

The only place this service sends a photographed document to Claude.
Everything above this layer talks to `DocumentExtractor`, so no test needs an
API key or a real document.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import anthropic

from app.application.line_items import normalize_quantity
from app.domain.errors import DocumentExtractionError
from app.domain.models import (
    AiFeature,
    AiUsage,
    DocumentKind,
    OcrDocumentResult,
    OcrLineItem,
    TaskCategory,
    Trade,
)
from app.infrastructure.costs import estimate_token_cost_minor
from app.infrastructure.prompts import document_extraction

_MAX_TOKENS_EXTRACTION = 4_000


def _text_of(response: Any) -> str:
    """Concatenate the text blocks of a Messages API response.

    Same refusal handling as `claude_vision_adapter._text_of` — a refusal
    (e.g. the model declines to read a document) leaves the content array
    empty or partial rather than raising directly.
    """
    if getattr(response, "stop_reason", None) == "refusal":
        raise DocumentExtractionError(
            "the model declined to read this document; try a clearer photo"
        )
    parts = [block.text for block in response.content if getattr(block, "type", None) == "text"]
    if not parts:
        raise DocumentExtractionError("the model returned no text content")
    return "".join(parts)


def _usage_from(response: Any, model_id: str) -> AiUsage:
    input_tokens = int(getattr(response.usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(response.usage, "output_tokens", 0) or 0)
    return AiUsage(
        feature=AiFeature.OCR,
        model_id=model_id,
        input_kind="ocr",
        tokens_used=input_tokens + output_tokens,
        cost_minor=estimate_token_cost_minor(model_id, input_tokens, output_tokens),
        metadata={"input_tokens": input_tokens, "output_tokens": output_tokens},
    )


def parse_extraction(payload: dict[str, Any]) -> OcrDocumentResult:
    """Map the model's JSON into domain types, validating as we go.

    Mirrors `claude_vision_adapter.parse_detection`: structured outputs
    constrain shape, not semantics, so a zero/negative quantity is rejected
    here even though it satisfies the schema.
    """
    try:
        document_kind = DocumentKind(payload["document_kind"])
        trade = Trade(payload["trade"])
        raw_line_items = payload["line_items"]
    except (KeyError, ValueError) as exc:
        raise DocumentExtractionError(f"model returned an unusable extraction: {exc}") from exc

    if not isinstance(raw_line_items, list):
        raise DocumentExtractionError("model returned a non-list `line_items` field")

    line_items: list[OcrLineItem] = []
    for index, raw in enumerate(raw_line_items):
        try:
            raw_cost = raw["unit_cost_minor"]
            line_items.append(
                OcrLineItem(
                    description=str(raw["description"]).strip(),
                    category=TaskCategory(raw["category"]),
                    item_name=str(raw["item_name"]).strip(),
                    quantity=normalize_quantity(raw["quantity"]),
                    unit=str(raw["unit"]).strip() or "each",
                    unit_cost_minor=int(raw_cost) if raw_cost is not None else None,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DocumentExtractionError(f"line item {index} is unusable: {exc}") from exc

    return OcrDocumentResult(
        document_kind=document_kind,
        trade=trade,
        summary=str(payload.get("summary", "")).strip(),
        line_items=tuple(line_items),
        vendor_name=str(payload.get("vendor_name", "") or "").strip(),
        document_date=str(payload.get("document_date", "") or "").strip(),
        reference_number=str(payload.get("reference_number", "") or "").strip(),
        notes=str(payload.get("notes", "") or "").strip(),
    )


class ClaudeDocumentExtractor:
    """Implements `DocumentExtractor` using the Messages API with an image
    content block and structured outputs."""

    def __init__(self, api_key: str, model: str, client: Any | None = None) -> None:
        self._api_key = api_key
        self._model = model
        self._client = client

    def _require_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise DocumentExtractionError(
                "ANTHROPIC_API_KEY is not configured; AI OCR is unavailable"
            )
        self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def extract_document(
        self, document_bytes: bytes, mime_type: str, document_kind_hint: str | None = None
    ) -> tuple[OcrDocumentResult, AiUsage]:
        client = self._require_client()
        encoded = base64.standard_b64encode(document_bytes).decode("ascii")

        response = client.messages.create(
            model=self._model,
            max_tokens=_MAX_TOKENS_EXTRACTION,
            system=document_extraction.build_system_prompt(document_kind_hint),
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": document_extraction.DOCUMENT_EXTRACTION_SCHEMA,
                }
            },
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": encoded,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Extract the structured data from this document.",
                        },
                    ],
                }
            ],
        )

        raw = _text_of(response)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DocumentExtractionError(f"model returned malformed JSON: {exc}") from exc

        extraction = parse_extraction(payload)
        return extraction, _usage_from(response, self._model)
