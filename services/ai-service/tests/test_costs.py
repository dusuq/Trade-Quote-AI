"""Token/transcription cost estimation — integer money math only."""

from __future__ import annotations

from app.infrastructure.costs import (
    estimate_token_cost_minor,
    estimate_transcription_cost_minor,
)


def test_known_model_uses_its_published_rate() -> None:
    # 1M input @ $5/MTok = 500 cents; 1M output @ $25/MTok = 2500 cents.
    assert estimate_token_cost_minor("claude-opus-5", 1_000_000, 1_000_000) == 3_000


def test_cost_is_always_an_integer_number_of_cents() -> None:
    cost = estimate_token_cost_minor("claude-opus-5", 1_234, 567)
    assert isinstance(cost, int)


def test_small_usage_rounds_up_rather_than_to_zero() -> None:
    """Billing a real call as free is the wrong direction to round."""
    assert estimate_token_cost_minor("claude-opus-5", 1, 1) == 1


def test_unknown_model_falls_back_to_the_most_expensive_tier() -> None:
    """Under-reporting spend would quietly let a tenant blow past its cap."""
    unknown = estimate_token_cost_minor("some-future-model", 1_000_000, 0)
    opus = estimate_token_cost_minor("claude-opus-5", 1_000_000, 0)
    assert unknown == opus


def test_cheaper_models_cost_less() -> None:
    assert estimate_token_cost_minor("claude-haiku-4-5", 1_000_000, 0) < estimate_token_cost_minor(
        "claude-opus-5", 1_000_000, 0
    )


def test_negative_token_counts_are_treated_as_zero() -> None:
    assert estimate_token_cost_minor("claude-opus-5", -5, -5) == 0


def test_transcription_costs_one_cent_per_100_seconds() -> None:
    assert estimate_transcription_cost_minor(100) == 1
    assert estimate_transcription_cost_minor(101) == 2


def test_short_recording_still_costs_something() -> None:
    assert estimate_transcription_cost_minor(3) == 1


def test_zero_duration_is_free() -> None:
    assert estimate_transcription_cost_minor(0) == 0
    assert estimate_transcription_cost_minor(-1) == 0
