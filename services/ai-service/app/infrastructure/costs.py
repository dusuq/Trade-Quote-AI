"""Token-cost estimation. Pure integer arithmetic — no floats near money.

Rates are **minor units (cents) per million tokens**, which keeps the whole
calculation in integers and matches conventions §5.
"""

from __future__ import annotations

_MILLION = 1_000_000

# (input, output) cents per million tokens.
_MODEL_RATES: dict[str, tuple[int, int]] = {
    "claude-opus-5": (500, 2500),  # $5 / $25 per MTok
    "claude-sonnet-5": (300, 1500),  # $3 / $15 per MTok
    "claude-haiku-4-5": (100, 500),  # $1 / $5 per MTok
}

# Used when a model isn't in the table. Deliberately the most expensive known
# tier: under-reporting spend would quietly let a tenant blow past its cap,
# whereas over-reporting only makes the cap conservative.
_FALLBACK_RATES = (500, 2500)

# Whisper bills per minute of audio, not per token: $0.006/min = 0.6 cents/min,
# which is exactly 1 cent per 100 seconds.
_WHISPER_SECONDS_PER_CENT = 100


def _ceil_div(numerator: int, denominator: int) -> int:
    """Integer ceiling division. Always round a charge up, never down."""
    return -(-numerator // denominator)


def estimate_token_cost_minor(model_id: str, input_tokens: int, output_tokens: int) -> int:
    """Cost in minor units for a completion, rounded up to the cent."""
    input_rate, output_rate = _MODEL_RATES.get(model_id, _FALLBACK_RATES)
    total = max(0, input_tokens) * input_rate + max(0, output_tokens) * output_rate
    return _ceil_div(total, _MILLION)


def estimate_transcription_cost_minor(duration_seconds: float) -> int:
    """Cost in minor units for transcribing `duration_seconds` of audio.

    At $0.006/min that is 1 cent per 100 seconds, rounded up — so any
    non-empty recording costs at least 1 cent rather than being billed as free.
    """
    if duration_seconds <= 0:
        return 0
    seconds = _ceil_div(int(duration_seconds * 1000), 1000)  # whole seconds, rounded up
    return _ceil_div(seconds, _WHISPER_SECONDS_PER_CENT)
