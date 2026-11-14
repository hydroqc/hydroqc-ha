"""Tarif D low/high price split.

Tarif D charges the low price for the first ``40 kWh x days`` of every billing
period and the high price beyond that. This module holds the one and only
implementation of that rule, so the daily sync, the CSV history import and the
one-time re-split service can never disagree.

It is pure Python (no Home Assistant imports) so it can be tested directly.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable

from .const import TARIF_D_THRESHOLD_KWH_PER_DAY

# Maps a calendar day to (billing period start date, billing period length in days)
PeriodLookup = Callable[[datetime.date], tuple[datetime.date, int]]


class TarifDSplitter:
    """Split hourly consumption into low-price (reg) and high-price (haut) kWh.

    Feed it hours in chronological order. The allowance starts over every time
    the hour falls in a new billing period, so a long run of hours (a CSV import
    chunk, or the whole history) is split period by period rather than against a
    single allowance.
    """

    def __init__(self, period_for_date: PeriodLookup, consumed_before: float = 0.0) -> None:
        """Initialize the splitter.

        Args:
            period_for_date: Returns (period start, period length in days) for a day.
            consumed_before: kWh already consumed in the period of the *first* hour
                that will be fed in (when the run starts in the middle of a period).
                Later periods always start at zero.
        """
        self._period_for_date = period_for_date
        self._initial_consumed = consumed_before
        self._period_start: datetime.date | None = None
        self._threshold = 0.0
        self._consumed = 0.0

    def split(self, day: datetime.date, kwh: float) -> tuple[float, float]:
        """Return (low price kWh, high price kWh) for one hour of ``day``."""
        period_start, duration = self._period_for_date(day)

        if period_start != self._period_start:
            is_first_period = self._period_start is None
            self._period_start = period_start
            self._threshold = duration * TARIF_D_THRESHOLD_KWH_PER_DAY
            self._consumed = self._initial_consumed if is_first_period else 0.0

        remaining = max(0.0, self._threshold - self._consumed)
        self._consumed += kwh
        return min(kwh, remaining), max(0.0, kwh - remaining)
