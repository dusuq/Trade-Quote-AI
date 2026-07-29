"""Scoring an extracted item name against pricebook candidates.

Pure functions, no I/O — the HTTP fetching lives in
`infrastructure/pricebook_client.py`, so the ranking rules can be tested
exhaustively without a network or a database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Below this, a "match" is worse than no match: a wrong price silently
# attached to a real line item is harder for a contractor to notice than an
# obvious $0 line asking to be filled in.
MIN_CONFIDENCE = 0.35

_SCORE_SKU_EXACT = 1.0
_SCORE_NAME_EXACT = 0.95
_SCORE_NAME_SUBSTRING = 0.80
_WEIGHT_NAME_OVERLAP = 0.75
_WEIGHT_DESCRIPTION_OVERLAP = 0.40

_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(slots=True, frozen=True)
class Candidate:
    """A pricebook item as far as scoring is concerned."""

    name: str
    sku: str | None = None
    description: str | None = None


def tokenize(text: str) -> frozenset[str]:
    """Lowercase alphanumeric tokens. `"200A Panel"` -> `{"200a", "panel"}`."""
    return frozenset(_TOKEN_RE.findall(text.lower()))


def _overlap(left: frozenset[str], right: frozenset[str]) -> float:
    """Jaccard similarity. 0.0 when either side is empty."""
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def score_candidate(query: str, candidate: Candidate) -> float:
    """Confidence that `candidate` is what `query` meant, 0.0–1.0.

    Ordered strongest signal first — an exact SKU is unambiguous, an exact
    name nearly so, and everything below that is fuzzy.
    """
    query_normalized = query.strip().lower()
    if not query_normalized:
        return 0.0

    if candidate.sku and candidate.sku.strip().lower() == query_normalized:
        return _SCORE_SKU_EXACT

    name_normalized = candidate.name.strip().lower()
    if name_normalized and name_normalized == query_normalized:
        return _SCORE_NAME_EXACT

    if name_normalized and (
        query_normalized in name_normalized or name_normalized in query_normalized
    ):
        return _SCORE_NAME_SUBSTRING

    query_tokens = tokenize(query)
    best = _WEIGHT_NAME_OVERLAP * _overlap(query_tokens, tokenize(candidate.name))
    if candidate.description:
        best = max(
            best,
            _WEIGHT_DESCRIPTION_OVERLAP * _overlap(query_tokens, tokenize(candidate.description)),
        )
    return best


def best_match(
    query: str, candidates: list[Candidate], *, min_confidence: float = MIN_CONFIDENCE
) -> tuple[int, float] | None:
    """Index and score of the best candidate, or None if nothing clears the bar.

    Ties resolve to the earliest candidate, so a stable upstream ordering
    produces a stable match rather than an arbitrary one.
    """
    best_index: int | None = None
    best_score = 0.0

    for index, candidate in enumerate(candidates):
        score = score_candidate(query, candidate)
        if score > best_score:
            best_index, best_score = index, score

    if best_index is None or best_score < min_confidence:
        return None
    return best_index, best_score
