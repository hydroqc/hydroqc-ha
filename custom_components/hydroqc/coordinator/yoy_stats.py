"""Year-over-year consumption statistics for HydroQc coordinator.

Computes rolling 7-day and 30-day consumption totals from the recorder and
compares each window with the same window one year earlier.

The totals are derived from the hourly ``total`` statistic that the consumption
sync already writes, so they work for every rate (D, D+CPC, DT, DPC, M...).

Values are recomputed at most once per day, and only once yesterday's last hour
(23:00) is present in the recorder: Hydro-Québec publishes the previous day's
final hours at an unpredictable time, so we wait for the data rather than for a
fixed clock time.
"""

# mypy: disable-error-code="attr-defined"

from __future__ import annotations

import datetime
import logging
import zoneinfo
from typing import Any

from homeassistant.components.recorder import statistics
from homeassistant.helpers.recorder import get_instance

_LOGGER = logging.getLogger(__name__)

_TZ = zoneinfo.ZoneInfo("America/Toronto")

# Rolling window sizes, in days
YOY_WINDOWS: tuple[int, ...] = (7, 30)

# Share of a window's hours that may be missing, scaled from the hours present.
# Hydro-Québec marks the odd hour as unavailable; 2% allows 3 hours over 7 days
# and 14 over 30 days, while a real lack of history still gives no value.
YOY_MAX_MISSING_SHARE: float = 0.02

# Every metric this mixin can serve (also the sensor keys in const.py)
YOY_METRICS: tuple[str, ...] = tuple(
    name
    for window in YOY_WINDOWS
    for name in (
        f"last_{window}_days_kwh",
        f"same_{window}_days_last_year_kwh",
        f"yoy_{window}day_delta_kwh",
    )
)


def _local_midnight(day: datetime.date) -> datetime.datetime:
    """Return the timezone-aware local midnight that starts ``day``."""
    return datetime.datetime.combine(day, datetime.time.min, tzinfo=_TZ)


def _one_year_earlier(day: datetime.date) -> datetime.date:
    """Return the same calendar date one year earlier (Feb 29 becomes Feb 28).

    Equivalent to ``dateutil.relativedelta(years=1)`` for dates, without adding a
    dependency that neither this integration nor Home Assistant core declares.
    """
    try:
        return day.replace(year=day.year - 1)
    except ValueError:  # Feb 29, and the previous year has no Feb 29
        return day.replace(year=day.year - 1, day=28)


def _stored_hours(first_day: datetime.date, last_day: datetime.date) -> int:
    """Return how many hourly rows the integration stores for these days.

    The consumption sync and the history import both timestamp an hour by
    attaching the local timezone to Hydro-Québec's wall-clock hour. On the
    fall-back day the repeated 01:00 hour therefore lands on one timestamp, so
    that day holds 24 rows although it lasts 25 hours; the spring-forward day
    holds 23. Counting real elapsed hours instead made every window containing
    a fall-back day look incomplete, for about a month each autumn.
    """
    stamps: set[datetime.datetime] = set()
    day = first_day
    while day <= last_day:
        for hour in range(24):
            local = datetime.datetime.combine(day, datetime.time(hour), tzinfo=_TZ)
            stamps.add(local.astimezone(datetime.UTC))
        day += datetime.timedelta(days=1)
    return len(stamps)


class YoYStatsMixin:
    """Mixin adding year-over-year rolling window values to the coordinator."""

    def _init_yoy_stats(self) -> None:
        """Initialize year-over-year state. Call from the coordinator __init__."""
        # metric name -> kWh value, or None when it cannot be computed reliably
        self._yoy_metrics: dict[str, float | None] = {}
        # Local date for which the metrics were last computed
        self._yoy_last_computed_date: datetime.date | None = None
        # window -> True when every hour of the recent window was in the recorder
        self._yoy_recent_complete: dict[int, bool] = {}

    # ------------------------------------------------------------------
    # Accessor used by get_sensor_value()
    # ------------------------------------------------------------------

    def get_yoy_value(self, data_source: str) -> float | None:
        """Return a cached year-over-year value, or None if not available.

        Args:
            data_source: ``computed_yoy.<metric>`` where metric is one of YOY_METRICS.
        """
        metric = data_source.removeprefix("computed_yoy.")
        return self._yoy_metrics.get(metric)

    # ------------------------------------------------------------------
    # Trigger
    # ------------------------------------------------------------------

    async def async_maybe_recompute_yoy(self) -> None:
        """Recompute the year-over-year values if yesterday's data is complete.

        Called after every consumption sync, so it must be cheap when there is
        nothing to do: it returns immediately once today's values are computed.
        """
        if not self.is_portal_mode:
            return

        today = datetime.datetime.now(_TZ).date()
        if self._yoy_last_computed_date == today:
            return

        yesterday = today - datetime.timedelta(days=1)

        # Yesterday's final hour is the last one Hydro-Québec publishes. If it is
        # not in the recorder yet, try again after the next consumption sync.
        if not await self._async_is_last_hour_present(yesterday):
            _LOGGER.debug("[YoY] Data for %s is not complete yet, will retry", yesterday)
            return

        previous = dict(self._yoy_metrics)
        for window in YOY_WINDOWS:
            self._yoy_metrics.update(await self._async_compute_window(yesterday, window))

        # Done for today only if every hour of the recent windows was there. If one
        # has a hole (an hour not published yet), its value is scaled or blank, so
        # try again after the next sync instead of keeping that until tomorrow. A
        # missing *last-year* window is permanent for the first year, so it must
        # not cause endless retries.
        if all(self._yoy_recent_complete.get(window) for window in YOY_WINDOWS):
            self._yoy_last_computed_date = today
        _LOGGER.debug("[YoY] Recomputed year-over-year values: %s", self._yoy_metrics)

        # We run outside the normal coordinator refresh, so tell the sensors.
        if self._yoy_metrics != previous:
            self.async_update_listeners()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _async_hourly_rows(
        self, start: datetime.datetime, end: datetime.datetime
    ) -> list[Any]:
        """Return the hourly ``total`` statistic rows in [start, end).

        ``statistics_during_period`` takes timezone-aware datetimes and does the
        UTC conversion itself, so local-time bounds are correct here.
        """
        statistic_id = self._get_statistic_id("total")
        result = await get_instance(self.hass).async_add_executor_job(
            statistics.statistics_during_period,
            self.hass,
            start,
            end,
            {statistic_id},
            "hour",
            None,
            {"state"},
        )
        return list(result.get(statistic_id, [])) if result else []

    async def _async_is_last_hour_present(self, day: datetime.date) -> bool:
        """Return True if the 23:00-24:00 row of ``day`` is in the recorder."""
        start = datetime.datetime.combine(day, datetime.time(23, 0), tzinfo=_TZ)
        end = _local_midnight(day + datetime.timedelta(days=1))
        try:
            return len(await self._async_hourly_rows(start, end)) > 0
        except Exception as err:
            _LOGGER.debug("[YoY] Could not check whether %s is complete: %s", day, err)
            return False

    async def _async_sum_window(
        self, first_day: datetime.date, last_day: datetime.date
    ) -> tuple[float | None, bool]:
        """Sum the consumption of ``first_day`` to ``last_day`` inclusive.

        Returns ``(kWh, complete)``. ``complete`` is True when every hour is there.

        Up to YOY_MAX_MISSING_SHARE of the hours may be missing (Hydro-Québec
        marks the odd hour as unavailable): the sum is then scaled by expected
        over present hours. Beyond that, the value is None. A plain partial sum
        would silently understate the window and produce a misleading
        year-over-year difference, for example when last year's history only
        starts in the middle of the window. Showing nothing is better than
        showing a wrong number.
        """
        start = _local_midnight(first_day)
        end = _local_midnight(last_day + datetime.timedelta(days=1))
        expected_hours = _stored_hours(first_day, last_day)

        try:
            rows = await self._async_hourly_rows(start, end)
        except Exception as err:
            _LOGGER.warning("[YoY] Could not query %s to %s: %s", first_day, last_day, err)
            return None, False

        found = len(rows)
        total = sum(row.get("state") or 0.0 for row in rows)

        # More rows than expected can only be both fall-back 01:00 hours stored
        # separately, which is complete as well.
        if found >= expected_hours:
            return round(total, 2), True

        missing = expected_hours - found
        if found == 0 or missing > int(expected_hours * YOY_MAX_MISSING_SHARE):
            _LOGGER.debug(
                "[YoY] Window %s to %s incomplete: %d of %d hours",
                first_day,
                last_day,
                found,
                expected_hours,
            )
            return None, False

        _LOGGER.debug(
            "[YoY] Window %s to %s missing %d of %d hours, scaled from the hours present",
            first_day,
            last_day,
            missing,
            expected_hours,
        )
        return round(total * expected_hours / found, 2), False

    async def _async_compute_window(
        self, yesterday: datetime.date, window: int
    ) -> dict[str, float | None]:
        """Compute the three metrics of one rolling window ending ``yesterday``."""
        first_day = yesterday - datetime.timedelta(days=window - 1)

        # Same window one year earlier. Only the END date is shifted by one
        # calendar year; the start is then derived from it so both windows are
        # always exactly ``window`` days wide.
        #
        # Why not simply shift both ends:
        # - timedelta(days=365) is off by a day across a leap year
        #   (2024-03-01 - 365 days = 2023-03-02).
        # - Shifting both ends by one calendar year fixes the anchor, but a window
        #   containing Feb 29 then spans 6 or 8 days last year instead of 7:
        #   2028-02-23..2028-02-29 maps to 2027-02-23..2027-02-28 (6 days),
        #   making the comparison apples to oranges.
        last_year_last_day = _one_year_earlier(yesterday)
        last_year_first_day = last_year_last_day - datetime.timedelta(days=window - 1)

        current, self._yoy_recent_complete[window] = await self._async_sum_window(
            first_day, yesterday
        )
        last_year, _ = await self._async_sum_window(last_year_first_day, last_year_last_day)

        delta = (
            round(current - last_year, 2) if current is not None and last_year is not None else None
        )

        return {
            f"last_{window}_days_kwh": current,
            f"same_{window}_days_last_year_kwh": last_year,
            f"yoy_{window}day_delta_kwh": delta,
        }
