"""Domain value objects for the quotes summary read model — framework-free."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class RangeBounds:
    """UTC instants bounding a tz-local day and a tz-local reporting range.

    range_end always equals day_end — "to date" includes everything created
    today, and keeping the two windows aligned means a quote created minutes
    ago counts toward both quotes_today and the cohort totals.
    """

    timezone: str
    day_start: datetime
    day_end: datetime
    range_start: datetime
    range_end: datetime


@dataclass(frozen=True)
class CurrencyTotal:
    currency: str
    accepted_value_minor: int


@dataclass(frozen=True)
class QuoteSummary:
    bounds: RangeBounds
    quotes_today: int
    pending_count: int
    accepted_count: int
    decided_count: int
    totals: list[CurrencyTotal] = field(default_factory=list)

    @property
    def conversion_bps(self) -> int:
        """accepted / decided in basis points. 0 when nothing has been decided —
        callers must check decided_count before treating this as a real rate."""
        if self.decided_count == 0:
            return 0
        return round((self.accepted_count / self.decided_count) * 10000)
