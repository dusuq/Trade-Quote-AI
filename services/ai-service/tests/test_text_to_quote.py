"""The text-to-quote pipeline, end to end against fakes."""

from __future__ import annotations

import uuid

import pytest

from app.application.text_to_quote import TextToQuoteUseCase
from app.domain.errors import DailySpendCapExceededError, ScopeExtractionError
from app.domain.models import ExtractedScope, InputKind, Trade
from tests.fakes import (
    FakePricebookMatcher,
    FakeQuoteCreator,
    FakeScopeExtractor,
    InMemoryUsageRepository,
    make_match,
    make_scope,
    make_task,
)

TENANT = uuid.uuid4()
USER = uuid.uuid4()
CUSTOMER = uuid.uuid4()


def build(
    *,
    scope: ExtractedScope | None = None,
    matches: dict | None = None,
    spend_today: int = 0,
    cap: int = 0,
):
    extractor = FakeScopeExtractor(scope)
    matcher = FakePricebookMatcher(matches)
    creator = FakeQuoteCreator()
    usage = InMemoryUsageRepository(spend_today)
    use_case = TextToQuoteUseCase(extractor, matcher, creator, usage, daily_cap_minor=cap)
    return use_case, extractor, matcher, creator, usage


def run(use_case, **overrides):
    kwargs = {
        "tenant_id": TENANT,
        "user_id": USER,
        "text": "Replace the panel with a 200 amp and install 12 LED lights",
        "customer_id": CUSTOMER,
    }
    kwargs.update(overrides)
    return use_case.execute(**kwargs)


def test_happy_path_creates_a_draft_quote() -> None:
    use_case, _extractor, _matcher, creator, _usage = build(
        matches={"200A main breaker panel": make_match()}
    )

    result, _events = run(use_case)

    assert result.quote_id == creator.quote_id
    assert result.scope.trade is Trade.ELECTRICAL
    assert len(creator.calls[0]["line_items"]) == 2


def test_text_input_is_not_labelled_as_voice() -> None:
    """quote-service's enum has no "AI drafted from text" value, so text runs
    record `manual` — the AI provenance rides on `ai.quote.drafted.inputKind`
    instead of being faked into `created_via`."""
    use_case, _e, _m, creator, _u = build()

    result, events = run(use_case)

    assert creator.calls[0]["created_via"] == "manual"
    assert result.input_kind is InputKind.TEXT
    assert events[0].payload["inputKind"] == "text"


def test_emitted_events_match_the_canonical_registry() -> None:
    """Guards against drifting from packages/types (conventions §4)."""
    use_case, _e, _m, _c, _u = build()

    _result, events = run(use_case)

    drafted, usage_event = events
    assert drafted.event_name == "ai.quote.drafted"
    assert set(drafted.payload) == {"quoteId", "modelId", "inputKind", "tokensUsed"}
    assert usage_event.event_name == "ai.usage.recorded"
    assert set(usage_event.payload) == {"feature", "modelId", "tokensUsed", "costMinor"}


def test_unmatched_tasks_still_become_line_items() -> None:
    use_case, _e, _m, creator, _u = build(matches={})

    result, _events = run(use_case)

    assert result.unmatched_count == 2
    assert len(creator.calls[0]["line_items"]) == 2
    assert all(item.unit_cost_minor == 0 for item in creator.calls[0]["line_items"])


def test_partial_match_prices_what_it_found(  ) -> None:
    use_case, _e, _m, creator, _u = build(matches={"200A main breaker panel": make_match()})

    result, _events = run(use_case)

    line_items = creator.calls[0]["line_items"]
    assert result.unmatched_count == 1
    assert line_items[0].unit_cost_minor == 85_000
    assert line_items[1].unit_cost_minor == 0


def test_empty_scope_is_an_error_not_an_empty_quote() -> None:
    use_case, _e, _m, creator, _u = build(scope=make_scope(tasks=()))

    with pytest.raises(ScopeExtractionError, match="no billable tasks"):
        run(use_case)

    assert creator.calls == []


def test_title_falls_back_to_the_scope_summary() -> None:
    use_case, _e, _m, creator, _u = build()

    run(use_case)

    assert creator.calls[0]["title"] == "Panel upgrade and LED lighting"


def test_explicit_title_wins() -> None:
    use_case, _e, _m, creator, _u = build()

    run(use_case, title="Smith residence")

    assert creator.calls[0]["title"] == "Smith residence"


def test_overlong_title_is_truncated_to_the_upstream_limit() -> None:
    use_case, _e, _m, creator, _u = build()

    run(use_case, title="x" * 400)

    assert len(creator.calls[0]["title"]) == 255


def test_spend_cap_is_enforced_before_the_model_is_called() -> None:
    """A cost control that fires after you've spent the money isn't one."""
    use_case, extractor, _m, creator, _u = build(spend_today=1_000, cap=1_000)

    with pytest.raises(DailySpendCapExceededError):
        run(use_case)

    assert extractor.calls == []
    assert creator.calls == []


def test_spend_cap_of_zero_is_disabled() -> None:
    use_case, _e, _m, creator, _u = build(spend_today=999_999, cap=0)

    run(use_case)

    assert len(creator.calls) == 1


def test_usage_is_recorded_only_after_the_quote_exists() -> None:
    """Billing for a run that produced nothing would be the wrong way round."""
    use_case, _e, _m, _c, usage = build()

    run(use_case)

    assert len(usage.recorded) == 1
    assert usage.recorded[0].tokens_used == 1_200


def test_trade_hint_is_passed_to_the_extractor() -> None:
    use_case, extractor, _m, _c, _u = build()

    run(use_case, trade_hint="plumbing")

    assert extractor.calls[0][1] == "plumbing"


def test_tax_rate_is_forwarded_in_basis_points() -> None:
    use_case, _e, _m, creator, _u = build()

    run(use_case, tax_rate_bps=875)

    assert creator.calls[0]["tax_rate_bps"] == 875


def test_single_task_scope_still_works() -> None:
    use_case, _e, _m, creator, _u = build(scope=make_scope(tasks=(make_task("conduit"),)))

    result, _events = run(use_case)

    assert len(creator.calls[0]["line_items"]) == 1
    assert result.unmatched_count == 1
