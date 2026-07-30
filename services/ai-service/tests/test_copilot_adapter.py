"""ClaudeCopilotAnalyzer / ClaudeTextRewriter with an injected fake SDK client.

`_ClaudeBase` accepts a `client=` so the adapter's orchestration (prompt wiring,
`output_config`, response parsing, usage accounting) is exercised end-to-end
with no network and no API key — the same seam T201's adapter uses.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.domain.errors import CopilotAnalysisError
from app.infrastructure.copilot_claude_adapter import (
    ClaudeCopilotAnalyzer,
    ClaudeTextRewriter,
)
from tests.fakes import make_line_item, make_snapshot


class _Block:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _Usage:
    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _Response:
    def __init__(self, payload: Any, *, stop_reason: str = "end_turn") -> None:
        self.content = [_Block(json.dumps(payload))]
        self.usage = _Usage(600, 300)
        self.stop_reason = stop_reason


class _FakeAnthropic:
    """Captures the create() kwargs and returns a canned response."""

    def __init__(self, response: _Response) -> None:
        self._response = response
        self.create_kwargs: dict[str, Any] = {}
        self.messages = self

    def create(self, **kwargs: Any) -> _Response:
        self.create_kwargs = kwargs
        return self._response


def _analyzer(response: _Response) -> tuple[ClaudeCopilotAnalyzer, _FakeAnthropic]:
    client = _FakeAnthropic(response)
    return ClaudeCopilotAnalyzer("", "claude-sonnet-5", client=client), client


def test_analyze_pricing_wires_schema_and_computes_margin() -> None:
    line = make_line_item(unit_cost_minor=10_000, unit_price_minor=20_000, quantity="1")
    quote = make_snapshot(line_items=(line,))
    payload = {
        "suggestions": [
            {"line_item_id": str(line.id), "suggested_markup_bps": 4000, "reasoning": "raise it"}
        ],
        "margin_recommendation": "healthy",
    }
    analyzer, client = _analyzer(_Response(payload))

    result, usage = analyzer.analyze_pricing(quote, {})

    # Prompt + structured-output schema were actually sent.
    assert client.create_kwargs["model"] == "claude-sonnet-5"
    assert client.create_kwargs["output_config"]["format"]["type"] == "json_schema"
    # Suggestion parsed, margin computed by OUR math (not the model).
    assert result.suggestions[0].suggested_markup_bps == 4000
    assert result.margin.gross_margin_bps == 5_000
    assert result.margin.recommendation == "healthy"
    # Usage accounted, feature = copilot, tokens summed (600 + 300).
    assert usage.feature.value == "copilot"
    assert usage.tokens_used == 900
    assert result.tokens_used == 900


def test_find_missing_items_parses_structured_output() -> None:
    quote = make_snapshot()
    payload = {
        "trade": "electrical",
        "completeness_score": 65,
        "summary": "needs a permit",
        "missing": [
            {
                "description": "Permit",
                "category": "labor",
                "item_name": "electrical permit",
                "estimated_quantity": 1,
                "unit": "each",
                "reasoning": "required",
                "priority": "critical",
            }
        ],
    }
    analyzer, client = _analyzer(_Response(payload))

    result, usage = analyzer.find_missing_items(quote, "200A upgrade")

    assert result.trade.value == "electrical"
    assert result.completeness_score == 65
    assert result.missing[0].item_name == "electrical permit"
    assert usage.feature.value == "copilot"
    # The trade hint was interpolated into the system prompt.
    assert "electrical estimator" in client.create_kwargs["system"]


def test_rewrite_returns_texts_and_accounts_usage() -> None:
    client = _FakeAnthropic(_Response({"rewritten": ["Install a 200A panel.", "Twelve LEDs."]}))
    rewriter = ClaudeTextRewriter("", "claude-sonnet-5", client=client)

    rewritten, usage = rewriter.rewrite(["install 200a", "12 led"], "professional")

    assert rewritten == ["Install a 200A panel.", "Twelve LEDs."]
    assert usage.tokens_used == 900


def test_rewrite_count_mismatch_raises() -> None:
    client = _FakeAnthropic(_Response({"rewritten": ["only one"]}))
    rewriter = ClaudeTextRewriter("", "claude-sonnet-5", client=client)

    with pytest.raises(CopilotAnalysisError):
        rewriter.rewrite(["a", "b"], "professional")


def test_model_refusal_becomes_analysis_error() -> None:
    analyzer, _ = _analyzer(_Response({"rewritten": []}, stop_reason="refusal"))
    with pytest.raises(CopilotAnalysisError):
        analyzer.find_missing_items(make_snapshot(), None)


def test_missing_api_key_is_a_clear_error() -> None:
    # No injected client and no key → the adapter refuses rather than crashing
    # deep in the SDK.
    analyzer = ClaudeCopilotAnalyzer("", "claude-sonnet-5")
    with pytest.raises(CopilotAnalysisError):
        analyzer.find_missing_items(make_snapshot(), None)
