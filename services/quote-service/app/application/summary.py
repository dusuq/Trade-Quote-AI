"""Use cases for the quotes summary read model (T206 / M20 Dashboard)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.domain.summary import RangeBounds

RangeKey = Literal["mtd", "ytd"]


class InvalidTimezoneError(ValueError):
    """Raised when tz_name is not a recognized IANA zone."""


def resolve_range(
    tz_name: str | None,
    range_key: RangeKey,
    *,
    now: datetime | None = None,
) -> RangeBounds:
    """Compute UTC instants for the tz-local day and tz-local reporting range.

    Absent tz_name defaults to UTC. An invalid tz_name raises
    InvalidTimezoneError — silently falling back would hand the caller
    confidently wrong day boundaries with no signal anything went wrong.

    `now` is injectable so callers (tests) can pin the reference instant;
    production code omits it and gets the real current time.
    """
    resolved_name = tz_name or "UTC"
    try:
        zone = ZoneInfo(resolved_name)
    except ZoneInfoNotFoundError as exc:
        raise InvalidTimezoneError(f"unknown timezone: {resolved_name}") from exc

    reference = now if now is not None else datetime.now(UTC)
    now_local = reference.astimezone(zone)
    day_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end_local = day_start_local + timedelta(days=1)

    if range_key == "mtd":
        range_start_local = day_start_local.replace(day=1)
    else:  # ytd
        range_start_local = day_start_local.replace(month=1, day=1)

    return RangeBounds(
        timezone=resolved_name,
        day_start=day_start_local.astimezone(UTC),
        day_end=day_end_local.astimezone(UTC),
        range_start=range_start_local.astimezone(UTC),
        range_end=day_end_local.astimezone(UTC),
    )
