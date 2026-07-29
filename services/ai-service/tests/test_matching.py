"""Pricebook match scoring."""

from __future__ import annotations

from app.application.matching import MIN_CONFIDENCE, Candidate, best_match, score_candidate


def test_exact_sku_beats_everything() -> None:
    assert score_candidate("PNL-200A", Candidate(name="Something else", sku="pnl-200a")) == 1.0


def test_exact_name_scores_just_below_sku() -> None:
    exact = score_candidate("200A panel", Candidate(name="200A Panel"))
    assert 0.9 <= exact < 1.0


def test_substring_match_scores_below_exact() -> None:
    exact = score_candidate("200A panel", Candidate(name="200A panel"))
    substring = score_candidate("200A panel", Candidate(name="200A panel, outdoor rated"))
    assert substring < exact
    assert substring >= MIN_CONFIDENCE


def test_token_overlap_matches_reordered_wording() -> None:
    """Transcribed speech rarely matches catalog word order."""
    score = score_candidate("panel main breaker 200A", Candidate(name="200A main breaker panel"))
    assert score >= MIN_CONFIDENCE


def test_unrelated_items_fall_below_the_threshold() -> None:
    assert score_candidate("200A panel", Candidate(name="Bathroom faucet")) < MIN_CONFIDENCE


def test_best_match_returns_none_rather_than_a_bad_guess() -> None:
    """A wrong price attached to a real line is harder to notice than a $0 line."""
    candidates = [Candidate(name="Bathroom faucet"), Candidate(name="Kitchen sink")]

    assert best_match("200A main breaker panel", candidates) is None


def test_best_match_picks_the_strongest_candidate() -> None:
    candidates = [
        Candidate(name="Panel accessory kit"),
        Candidate(name="200A main breaker panel"),
        Candidate(name="100A panel"),
    ]

    found = best_match("200A main breaker panel", candidates)

    assert found is not None
    assert found[0] == 1


def test_ties_resolve_to_the_first_candidate() -> None:
    """Stable upstream ordering should give a stable match, not a coin flip."""
    candidates = [Candidate(name="200A panel"), Candidate(name="200A panel")]

    found = best_match("200A panel", candidates)

    assert found is not None and found[0] == 0


def test_description_can_rescue_a_weak_name_match() -> None:
    with_description = score_candidate(
        "breaker panel",
        Candidate(name="MLO-2", description="Main breaker panel, 200 amp service"),
    )
    without = score_candidate("breaker panel", Candidate(name="MLO-2"))

    assert with_description > without


def test_empty_query_scores_zero() -> None:
    assert score_candidate("   ", Candidate(name="200A panel")) == 0.0
