"""Anthropic Claude vision adapter for equipment detection (M18 / T304).

The only place this service sends an image to Claude. Everything above this
layer talks to `VisionDetector`, so no test needs an API key or a real photo.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import anthropic

from app.application.line_items import normalize_quantity
from app.domain.errors import EquipmentDetectionError
from app.domain.models import (
    AiFeature,
    AiUsage,
    DetectedEquipment,
    EquipmentCondition,
    EquipmentDetectionResult,
    TaskCategory,
    Trade,
)
from app.infrastructure.costs import estimate_token_cost_minor
from app.infrastructure.prompts import equipment_detection

_MAX_TOKENS_DETECTION = 4_000


def _text_of(response: Any) -> str:
    """Concatenate the text blocks of a Messages API response.

    Same refusal handling as `claude_adapter._text_of` — a vision refusal
    (e.g. the model declines to analyze a photo) leaves the content array
    empty or partial rather than raising directly.
    """
    if getattr(response, "stop_reason", None) == "refusal":
        raise EquipmentDetectionError(
            "the model declined to analyze this photo; try a clearer image"
        )
    parts = [block.text for block in response.content if getattr(block, "type", None) == "text"]
    if not parts:
        raise EquipmentDetectionError("the model returned no text content")
    return "".join(parts)


def _usage_from(response: Any, model_id: str) -> AiUsage:
    input_tokens = int(getattr(response.usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(response.usage, "output_tokens", 0) or 0)
    return AiUsage(
        feature=AiFeature.VISION,
        model_id=model_id,
        input_kind="vision",
        tokens_used=input_tokens + output_tokens,
        cost_minor=estimate_token_cost_minor(model_id, input_tokens, output_tokens),
        metadata={"input_tokens": input_tokens, "output_tokens": output_tokens},
    )


def parse_detection(payload: dict[str, Any]) -> EquipmentDetectionResult:
    """Map the model's JSON into domain types, validating as we go.

    Mirrors `claude_adapter.parse_scope`: structured outputs constrain shape,
    not semantics, so a zero/negative quantity is rejected here even though
    it satisfies the schema.
    """
    try:
        trade = Trade(payload["trade"])
        raw_equipment = payload["equipment"]
    except (KeyError, ValueError) as exc:
        raise EquipmentDetectionError(f"model returned an unusable detection: {exc}") from exc

    if not isinstance(raw_equipment, list):
        raise EquipmentDetectionError("model returned a non-list `equipment` field")

    equipment: list[DetectedEquipment] = []
    for index, raw in enumerate(raw_equipment):
        try:
            equipment.append(
                DetectedEquipment(
                    name=str(raw["name"]).strip(),
                    category=TaskCategory(raw["category"]),
                    condition=EquipmentCondition(raw["condition"]),
                    quantity=normalize_quantity(raw["quantity"]),
                    unit=str(raw["unit"]).strip() or "each",
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise EquipmentDetectionError(f"equipment {index} is unusable: {exc}") from exc

    return EquipmentDetectionResult(
        trade=trade,
        summary=str(payload.get("summary", "")).strip(),
        equipment=tuple(equipment),
        notes=str(payload.get("notes", "") or "").strip(),
    )


class ClaudeVisionDetector:
    """Implements `VisionDetector` using the Messages API with an image
    content block and structured outputs."""

    def __init__(self, api_key: str, model: str, client: Any | None = None) -> None:
        self._api_key = api_key
        self._model = model
        self._client = client

    def _require_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise EquipmentDetectionError(
                "ANTHROPIC_API_KEY is not configured; AI Vision is unavailable"
            )
        self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def detect_equipment(
        self, image_bytes: bytes, mime_type: str, trade_hint: str | None = None
    ) -> tuple[EquipmentDetectionResult, AiUsage]:
        client = self._require_client()
        encoded = base64.standard_b64encode(image_bytes).decode("ascii")

        response = client.messages.create(
            model=self._model,
            max_tokens=_MAX_TOKENS_DETECTION,
            system=equipment_detection.build_system_prompt(trade_hint),
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": equipment_detection.EQUIPMENT_DETECTION_SCHEMA,
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
                            "text": "Identify the trade equipment and material in this photo.",
                        },
                    ],
                }
            ],
        )

        raw = _text_of(response)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise EquipmentDetectionError(f"model returned malformed JSON: {exc}") from exc

        detection = parse_detection(payload)
        return detection, _usage_from(response, self._model)
