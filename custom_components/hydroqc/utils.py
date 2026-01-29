"""Utility functions for the HydroQc integration."""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Toronto")


def is_winter_season(dt: datetime.datetime | datetime.date | None = None) -> bool:
    """Check if date is within winter season (Dec 1 - Mar 31).

    Winter season spans from December 1st to March 31st of the following year.
    This is when Hydro-Québec's dynamic rate periods (DPC, DCPC) are active.

    Args:
        dt: Date or datetime to check. Defaults to current time in Montreal timezone.

    Returns:
        True if the date is within winter season, False otherwise.
    """
    if dt is None:
        dt = datetime.datetime.now(TZ)

    if isinstance(dt, datetime.datetime):
        month, day = dt.month, dt.day
    else:
        month, day = dt.month, dt.day

    # Winter season: Dec 1 to Mar 31
    # (month, day) >= (12, 1) covers Dec 1 to Dec 31
    # (month, day) <= (3, 31) covers Jan 1 to Mar 31
    return (month, day) >= (12, 1) or (month, day) <= (3, 31)


def get_winter_season_bounds(
    reference_date: datetime.date | None = None,
) -> tuple[datetime.date, datetime.date]:
    """Get the start and end dates of the winter season containing the reference date.

    Args:
        reference_date: Date to find the winter season for. Defaults to today.

    Returns:
        Tuple of (winter_start, winter_end) dates.
        Returns the bounds of the current/previous winter season if in Apr-Nov,
        or the current winter season if in Dec-Mar.
    """
    if reference_date is None:
        reference_date = datetime.datetime.now(TZ).date()

    # If we're in December, winter season is Dec of this year to Mar of next year
    if reference_date.month >= 12:
        winter_start = datetime.date(reference_date.year, 12, 1)
        winter_end = datetime.date(reference_date.year + 1, 3, 31)
    # If we're in Jan-Mar, winter season started in Dec of previous year
    elif reference_date.month <= 3:
        winter_start = datetime.date(reference_date.year - 1, 12, 1)
        winter_end = datetime.date(reference_date.year, 3, 31)
    # If we're in Apr-Nov, return the upcoming winter season
    else:
        winter_start = datetime.date(reference_date.year, 12, 1)
        winter_end = datetime.date(reference_date.year + 1, 3, 31)

    return winter_start, winter_end
