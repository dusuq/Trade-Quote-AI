"""Pricebook matching over HTTP (ADR-0003 — on the critical path).

Fetching lives here; the ranking rules live in `application/matching.py` so
they can be tested exhaustively without a network.
"""

from __future__ import annotations

from uuid import UUID

from app.application.matching import MIN_CONFIDENCE, Candidate, best_match
from app.domain.errors import UpstreamServiceError
from app.domain.models import ExtractedTask, MatchedTask, PricebookMatch
from app.infrastructure.http import ServiceClient

# How many candidates to score per task. The endpoint caps at 500; 25 is
# plenty for a name lookup and keeps the payload small on a request the user
# is waiting on.
_CANDIDATE_LIMIT = 25


class HttpPricebookMatcher:
    """Implements `PricebookMatcher` against `GET /v1/pricebook/items`."""

    def __init__(self, client: ServiceClient, *, min_confidence: float = MIN_CONFIDENCE) -> None:
        self._client = client
        self._min_confidence = min_confidence

    def match(
        self, tenant_id: UUID, user_id: UUID | None, tasks: list[ExtractedTask]
    ) -> list[MatchedTask]:
        results: list[MatchedTask] = []
        for task in tasks:
            results.append(self._match_one(tenant_id, user_id, task))
        return results

    def _match_one(
        self, tenant_id: UUID, user_id: UUID | None, task: ExtractedTask
    ) -> MatchedTask:
        try:
            payload = self._client.request(
                "GET",
                "/v1/pricebook/items",
                tenant_id=tenant_id,
                user_id=user_id,
                params={
                    "search": task.item_name,
                    "kind": task.category.value,
                    "is_active": True,
                    "limit": _CANDIDATE_LIMIT,
                },
            )
        except UpstreamServiceError:
            # One item failing to look up should not lose the whole quote.
            # The task still becomes a line item, just an unpriced one the
            # contractor fills in — the same outcome as "no match", which is
            # already a first-class case.
            return MatchedTask(task=task, match=None)

        items = payload if isinstance(payload, list) else []
        if not items:
            return MatchedTask(task=task, match=None)

        candidates = [
            Candidate(
                name=str(item.get("name", "")),
                sku=item.get("sku"),
                description=item.get("description"),
            )
            for item in items
        ]
        found = best_match(task.item_name, candidates, min_confidence=self._min_confidence)
        if found is None:
            return MatchedTask(task=task, match=None)

        index, confidence = found
        item = items[index]
        try:
            match = PricebookMatch(
                pricebook_item_id=UUID(str(item["id"])),
                name=str(item["name"]),
                kind=str(item["kind"]),
                unit_cost_minor=int(item["unit_cost_minor"]),
                unit=str(item.get("unit") or task.unit),
                confidence=confidence,
                default_markup_bps=int(item.get("default_markup_bps") or 0),
            )
        except (KeyError, TypeError, ValueError):
            # A malformed catalog row is not worth failing the request over.
            return MatchedTask(task=task, match=None)

        return MatchedTask(task=task, match=match)
