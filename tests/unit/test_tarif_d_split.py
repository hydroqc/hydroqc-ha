"""Unit tests for the Tarif D low/high price split feature (PR3).

Tests cover:
- _get_period_start_for_date: billing period boundary detection
- reg/haut split calculation with known consumption sequences
- Threshold reset at billing period boundaries
- 60-day fallback approximation anchored to oldest known period
- The 40 kWh/day constant is used (not hardcoded)
"""

from __future__ import annotations

import datetime
import itertools
import random
import zoneinfo
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

# Import constants directly — changes here should break tests intentionally
from custom_components.hydroqc.const import (
    TARIF_D_HISTORY_PERIOD_DAYS,
    TARIF_D_THRESHOLD_KWH_PER_DAY,
)
from custom_components.hydroqc.consumption_history import ConsumptionHistoryImporter
from custom_components.hydroqc.coordinator.consumption_sync import ConsumptionSyncMixin
from custom_components.hydroqc.tarif_d_split import TarifDSplitter

# ── Helpers ───────────────────────────────────────────────────────────────────


def make_stats_manager(
    rate: str = "D",
    billing_duration_entity: str | None = None,
    contract=None,
):
    """Create a minimal StatisticsManager for testing without HA dependencies."""
    from unittest.mock import MagicMock, patch

    with (
        patch("custom_components.hydroqc.statistics_manager.get_instance"),
        patch("custom_components.hydroqc.statistics_manager.statistics"),
    ):
        from custom_components.hydroqc.statistics_manager import StatisticsManager

        hass = MagicMock()
        mgr = StatisticsManager.__new__(StatisticsManager)
        mgr.hass = hass
        mgr._rate = rate
        mgr._contract = contract
        mgr._contract_name = "maison"
        mgr._billing_duration_entity = billing_duration_entity
        mgr._get_statistic_id = lambda t: f"hydroqc:maison_{t}_hourly_consumption"
        return mgr


# ── Constants tests ───────────────────────────────────────────────────────────


def test_threshold_constant_value() -> None:
    """TARIF_D_THRESHOLD_KWH_PER_DAY must be 40."""
    assert TARIF_D_THRESHOLD_KWH_PER_DAY == 40


def test_history_period_constant_value() -> None:
    """TARIF_D_HISTORY_PERIOD_DAYS must be 60."""
    assert TARIF_D_HISTORY_PERIOD_DAYS == 60


# ── _get_period_start_for_date tests ─────────────────────────────────────────


class TestGetPeriodStartForDate:
    """Tests for _get_period_start_for_date method."""

    def setup_method(self):
        self.mgr = make_stats_manager()

    def test_date_within_known_period(self) -> None:
        """Date within a known period should return that period's start."""
        period_start = datetime.date(2026, 3, 20)
        period_durations = {period_start: 62}

        result = self.mgr._get_period_start_for_date(datetime.date(2026, 4, 15), period_durations)
        assert result == period_start

    def test_date_at_period_start(self) -> None:
        """Date exactly at period start should return that period."""
        period_start = datetime.date(2026, 3, 20)
        period_durations = {period_start: 62}

        result = self.mgr._get_period_start_for_date(period_start, period_durations)
        assert result == period_start

    def test_date_at_period_end_goes_to_next(self) -> None:
        """Date exactly at period end (exclusive) should go to next period."""
        period_start = datetime.date(2026, 3, 20)
        next_start = datetime.date(2026, 5, 21)
        period_durations = {
            period_start: 62,
            next_start: 58,
        }
        # May 21 is start of next period (exclusive end of first)
        result = self.mgr._get_period_start_for_date(next_start, period_durations)
        assert result == next_start

    def test_date_before_all_known_periods_extrapolates_backward(self) -> None:
        """Date before all known periods should extrapolate back in 60-day blocks."""
        oldest_known = datetime.date(2026, 2, 22)
        period_durations = {oldest_known: 57}

        # 65 days before the oldest known period is more than one 60-day block away,
        # so the block that contains it starts TWO blocks back (not one).
        test_date = oldest_known - datetime.timedelta(days=65)
        result = self.mgr._get_period_start_for_date(test_date, period_durations)

        expected = oldest_known - datetime.timedelta(days=2 * TARIF_D_HISTORY_PERIOD_DAYS)
        assert result == expected

        # Invariant that matters: the returned block must actually contain the date.
        block_end = result + datetime.timedelta(days=TARIF_D_HISTORY_PERIOD_DAYS)
        assert result <= test_date < block_end

    def test_date_just_before_oldest_extrapolates_one_block(self) -> None:
        """Date 1 day before oldest known period should be one block back."""
        oldest_known = datetime.date(2026, 2, 22)
        period_durations = {oldest_known: 57}

        test_date = oldest_known - datetime.timedelta(days=1)
        result = self.mgr._get_period_start_for_date(test_date, period_durations)

        expected = oldest_known - datetime.timedelta(days=TARIF_D_HISTORY_PERIOD_DAYS)
        assert result == expected

    def test_empty_period_durations_uses_fixed_blocks(self) -> None:
        """Empty period_durations should use fixed 60-day blocks from reference."""
        test_date = datetime.date(2024, 3, 20)
        result = self.mgr._get_period_start_for_date(test_date, {})
        # Result should be a date, not None
        assert result is not None
        # Result should be within one period of test_date
        assert (test_date - result).days < TARIF_D_HISTORY_PERIOD_DAYS

    def test_multiple_periods_finds_correct_one(self) -> None:
        """Multiple periods — should find the correct containing period."""
        period_durations = {
            datetime.date(2025, 11, 1): 57,
            datetime.date(2025, 12, 28): 62,
            datetime.date(2026, 2, 28): 58,
            datetime.date(2026, 4, 27): 60,
        }
        # Test date in second period
        result = self.mgr._get_period_start_for_date(datetime.date(2026, 1, 15), period_durations)
        assert result == datetime.date(2025, 12, 28)

    def test_extrapolation_is_anchored_to_oldest_known(self) -> None:
        """Extrapolation backward must be anchored to oldest known period,
        not an arbitrary date like 2020-01-01.

        This was the original bug — wrong anchor caused misaligned periods.
        """
        oldest_known = datetime.date(2026, 2, 22)
        period_durations = {oldest_known: 62}

        # Test multiple dates before oldest — all should align with oldest_known
        for days_back in [30, 60, 90, 120, 180, 365]:
            test_date = oldest_known - datetime.timedelta(days=days_back)
            result = self.mgr._get_period_start_for_date(test_date, period_durations)

            # The result should be a multiple of TARIF_D_HISTORY_PERIOD_DAYS
            # before oldest_known
            assert result is not None
            days_from_result_to_oldest = (oldest_known - result).days
            assert days_from_result_to_oldest % TARIF_D_HISTORY_PERIOD_DAYS == 0, (
                f"Period boundary for {test_date} ({result}) is not aligned "
                f"to oldest_known ({oldest_known}): "
                f"{days_from_result_to_oldest} days gap"
            )


# ── Split calculation tests ───────────────────────────────────────────────────


class TestSplitCalculation:
    """Tests for the reg/haut split of a single billing period.

    They run the real TarifDSplitter that the daily sync, the CSV import and
    the re-split service all share.
    """

    def _apply_split(
        self,
        hourly_kwh: list[float],
        threshold: float,
        period_consumed_before: float = 0.0,
    ) -> tuple[list[float], list[float]]:
        """Split hourly values that all fall in one billing period.

        Args:
            hourly_kwh: List of hourly consumption in kWh
            threshold: Total low-price threshold in kWh for this period
            period_consumed_before: kWh already consumed before this sequence

        Returns:
            Tuple of (reg_list, haut_list)
        """
        day = datetime.date(2026, 3, 1)
        # Express the threshold as a (possibly fractional) number of 40 kWh days
        days = threshold / TARIF_D_THRESHOLD_KWH_PER_DAY
        splitter = TarifDSplitter(lambda _day: (day, days), period_consumed_before)  # type: ignore[arg-type,return-value]

        reg: list[float] = []
        haut: list[float] = []
        for kwh in hourly_kwh:
            r, h = splitter.split(day, kwh)
            reg.append(r)
            haut.append(h)
        return reg, haut

    def test_all_consumption_within_threshold(self) -> None:
        """When total consumption is below threshold, all goes to reg."""
        threshold = TARIF_D_THRESHOLD_KWH_PER_DAY * 62  # 2480 kWh
        hourly = [0.5] * 100  # 50 kWh total — well within threshold

        reg, haut = self._apply_split(hourly, threshold)

        assert sum(reg) == pytest.approx(50.0)
        assert sum(haut) == pytest.approx(0.0)
        assert all(h == 0.0 for h in haut)

    def test_all_consumption_beyond_threshold(self) -> None:
        """When threshold is already exhausted, all goes to haut."""
        threshold = 100.0
        hourly = [1.0] * 50  # 50 kWh

        reg, haut = self._apply_split(hourly, threshold, period_consumed_before=100.0)

        assert sum(reg) == pytest.approx(0.0)
        assert sum(haut) == pytest.approx(50.0)

    def test_split_at_threshold_boundary(self) -> None:
        """Consumption crossing threshold should split correctly at the boundary."""
        threshold = 10.0  # Simple round number for easy verification
        # 8 hours at 1 kWh, then 1 hour at 5 kWh that crosses threshold
        hourly = [1.0] * 8 + [5.0] + [1.0] * 5

        reg, haut = self._apply_split(hourly, threshold)

        # First 8 hours: all reg (8 kWh consumed, 2 remaining)
        assert reg[:8] == [1.0] * 8
        assert haut[:8] == [0.0] * 8

        # 9th hour: 2 kWh reg (fills threshold), 3 kWh haut
        assert reg[8] == pytest.approx(2.0)
        assert haut[8] == pytest.approx(3.0)

        # Remaining hours: all haut
        assert reg[9:] == [0.0] * 5
        assert haut[9:] == [1.0] * 5

    def test_reg_plus_haut_equals_total(self) -> None:
        """reg + haut must always equal total for every hour."""
        threshold = 500.0
        random.seed(42)
        hourly = [random.uniform(0.1, 3.0) for _ in range(200)]

        reg, haut = self._apply_split(hourly, threshold, period_consumed_before=400.0)

        for i, (r, h, total) in enumerate(zip(reg, haut, hourly, strict=True)):
            assert r + h == pytest.approx(total, abs=1e-9), (
                f"Hour {i}: reg({r}) + haut({h}) != total({total})"
            )

    def test_zero_consumption_hours(self) -> None:
        """Hours with zero consumption should produce zero reg and haut."""
        threshold = 100.0
        hourly = [0.0] * 24 + [5.0] * 5

        reg, haut = self._apply_split(hourly, threshold)

        assert reg[:24] == [0.0] * 24
        assert haut[:24] == [0.0] * 24
        assert sum(reg[24:]) == pytest.approx(25.0)
        assert sum(haut[24:]) == pytest.approx(0.0)

    def test_threshold_exactly_met(self) -> None:
        """When consumption exactly meets threshold, haut should be 0."""
        threshold = 100.0
        hourly = [1.0] * 100  # Exactly 100 kWh

        reg, haut = self._apply_split(hourly, threshold)

        assert sum(reg) == pytest.approx(100.0)
        assert sum(haut) == pytest.approx(0.0)

    def test_typical_billing_period(self) -> None:
        """Simulate a realistic 62-day billing period with varied consumption."""
        period_days = 62
        threshold = TARIF_D_THRESHOLD_KWH_PER_DAY * period_days  # 2480 kWh

        # Simulate ~40 kWh/day average (right at threshold boundary)
        # Some days above, some below
        daily_kwh = [35.0] * 30 + [45.0] * 32  # 30 days x 35 + 32 days x 45
        hourly = []
        for day_kwh in daily_kwh:
            # Spread evenly across 24 hours
            hourly.extend([day_kwh / 24] * 24)

        reg, haut = self._apply_split(hourly, threshold)

        total_reg = sum(reg)
        total_haut = sum(haut)
        total_consumption = sum(hourly)

        # reg should not exceed threshold
        assert total_reg <= threshold + 1e-6

        # reg + haut should equal total
        assert total_reg + total_haut == pytest.approx(total_consumption, abs=1e-6)

        # Since average is right at threshold, both reg and haut should have data
        assert total_reg > 0
        # 30x35 = 1050, 32x45 = 1440, total = 2490 > 2480 threshold
        # So there should be some haut
        assert total_haut > 0


# ── Statistics display name tests ─────────────────────────────────────────────


class TestStatisticsDisplayNames:
    """Tests for build_statistics_metadata display name logic."""

    def setup_method(self):
        self.mgr = make_stats_manager(rate="D")

    def test_tarif_d_reg_display_name(self) -> None:
        """Tarif D reg stream should show 'Low Price' not 'Reg'."""
        self.mgr._rate = "D"
        metadata = self.mgr.build_statistics_metadata("reg")
        assert "Low Price" in metadata.get("name", "")
        assert "Reg" not in metadata.get("name", "")

    def test_tarif_d_haut_display_name(self) -> None:
        """Tarif D haut stream should show 'High Price' not 'Haut'."""
        self.mgr._rate = "D"
        metadata = self.mgr.build_statistics_metadata("haut")
        assert "High Price" in metadata.get("name", "")
        assert "Haut" not in metadata.get("name", "")

    def test_tarif_d_total_display_name(self) -> None:
        """Tarif D total stream should show 'Total'."""
        self.mgr._rate = "D"
        metadata = self.mgr.build_statistics_metadata("total")
        assert "Total" in metadata.get("name", "")

    def test_tarif_dt_reg_display_name_unchanged(self) -> None:
        """Tarif DT reg stream should still show 'Reg' (backward compatibility)."""
        self.mgr._rate = "DT"
        metadata = self.mgr.build_statistics_metadata("reg")
        assert "Reg" in metadata.get("name", "")
        assert "Low Price" not in metadata.get("name", "")

    def test_tarif_dt_haut_display_name_unchanged(self) -> None:
        """Tarif DT haut stream should still show 'Haut' (backward compatibility)."""
        self.mgr._rate = "DT"
        metadata = self.mgr.build_statistics_metadata("haut")
        assert "Haut" in metadata.get("name", "")
        assert "High Price" not in metadata.get("name", "")


# ── Shared fixtures for the tests below ───────────────────────────────────────

D = datetime.date
TZ = zoneinfo.ZoneInfo("America/Toronto")
STATISTICS_MANAGER = "custom_components.hydroqc.statistics_manager"


def contract_for(start: D, days: int) -> SimpleNamespace:
    """A contract whose current billing period is ``days`` long and began on ``start``."""
    return SimpleNamespace(cp_start_date=start, cp_duration=days)


def day_of_hours(kwh: float) -> list[dict[str, object]]:
    """The 24 hourly entries the portal returns for one day."""
    return [{"heure": f"{hour:02d}:00:00", "consoTotal": kwh} for hour in range(24)]


# ── TarifDSplitter across billing periods ─────────────────────────────────────


class TestSplitterAcrossPeriods:
    """The allowance must restart at every billing period boundary within one run."""

    @staticmethod
    def lookup(boundaries: dict[D, int]):
        """Period lookup from {period start: length}; a day belongs to the latest start <= it."""

        def find(day: D) -> tuple[D, int]:
            start = max(s for s in boundaries if s <= day)
            return start, boundaries[start]

        return find

    def test_allowance_restarts_at_each_boundary_in_a_single_run(self) -> None:
        # Two 5-day periods => 200 kWh allowance each; 48 kWh/day => 240 kWh per period
        first, second = D(2026, 1, 1), D(2026, 1, 6)
        splitter = TarifDSplitter(self.lookup({first: 5, second: 5}))

        results: dict[D, list[tuple[float, float]]] = {}
        for offset in range(10):
            day = first + datetime.timedelta(days=offset)
            results[day] = [splitter.split(day, 2.0) for _ in range(24)]

        def totals(start: D) -> tuple[float, float]:
            hours = [
                h
                for d, r in results.items()
                if start <= d < start + datetime.timedelta(5)
                for h in r
            ]
            return sum(r for r, _ in hours), sum(h for _, h in hours)

        assert totals(first) == pytest.approx((200.0, 40.0))
        assert totals(second) == pytest.approx((200.0, 40.0))
        # The first hour of the new period is low price again, even though the
        # previous period ended deep into the high price tier
        assert results[second][0] == (2.0, 0.0)
        assert results[second - datetime.timedelta(days=1)][-1] == (0.0, 2.0)

    def test_consumed_before_applies_to_the_first_period_only(self) -> None:
        first, second = D(2026, 1, 1), D(2026, 1, 6)
        splitter = TarifDSplitter(self.lookup({first: 5, second: 5}), consumed_before=190.0)

        # 10 kWh of allowance left in the first period...
        assert splitter.split(first, 10.0) == (10.0, 0.0)
        assert splitter.split(first, 1.0) == (0.0, 1.0)
        # ...and a full 200 kWh in the next one
        assert splitter.split(second, 200.0) == (200.0, 0.0)
        assert splitter.split(second, 1.0) == (0.0, 1.0)

    @pytest.mark.parametrize("days", [57, 61, 64])
    def test_allowance_follows_the_length_of_the_period(self, days: int) -> None:
        start = D(2026, 1, 1)
        splitter = TarifDSplitter(self.lookup({start: days}))

        reg = haut = 0.0
        for offset in range(days):  # 100 kWh/day: always well above the allowance
            r, h = splitter.split(start + datetime.timedelta(days=offset), 100.0)
            reg += r
            haut += h

        assert reg == pytest.approx(days * TARIF_D_THRESHOLD_KWH_PER_DAY)
        assert reg + haut == pytest.approx(days * 100.0)

    def test_reg_plus_haut_always_equals_total_across_periods(self) -> None:
        random.seed(7)
        boundaries = {D(2026, 1, 1): 6, D(2026, 1, 7): 4, D(2026, 1, 11): 8}
        splitter = TarifDSplitter(self.lookup(boundaries), consumed_before=50.0)

        for offset in range(18):
            day = D(2026, 1, 1) + datetime.timedelta(days=offset)
            for _ in range(24):
                kwh = random.uniform(0.0, 4.0)
                reg, haut = splitter.split(day, kwh)
                assert reg >= 0.0
                assert haut >= 0.0
                assert reg + haut == pytest.approx(kwh, abs=1e-9)


# ── build_period_lookup ───────────────────────────────────────────────────────


class TestBuildPeriodLookup:
    def test_days_in_the_current_period_use_the_contract_period(self) -> None:
        start = D(2026, 3, 1)
        lookup = make_stats_manager(contract=contract_for(start, 61)).build_period_lookup({})

        assert lookup(start) == (start, 61)
        assert lookup(start + datetime.timedelta(days=60)) == (start, 61)

    def test_day_before_the_current_period_is_not_treated_as_its_start(self) -> None:
        """Regression: the last day of the previous period must not look like a fresh allowance."""
        start = D(2026, 3, 1)
        lookup = make_stats_manager(contract=contract_for(start, 61)).build_period_lookup({})

        previous_start, previous_days = lookup(start - datetime.timedelta(days=1))

        assert previous_start != start
        assert previous_start == start - datetime.timedelta(days=TARIF_D_HISTORY_PERIOD_DAYS)
        assert previous_days == TARIF_D_HISTORY_PERIOD_DAYS

    def test_known_period_history_wins_over_the_contract(self) -> None:
        history = {D(2026, 1, 1): 57}
        lookup = make_stats_manager(contract=contract_for(D(2026, 3, 1), 61)).build_period_lookup(
            history
        )

        assert lookup(D(2026, 1, 10)) == (D(2026, 1, 1), 57)

    @pytest.mark.parametrize(
        "cp_start",
        [D(2026, 3, 1), datetime.datetime(2026, 3, 1, 8, 30), "2026-03-01"],
        ids=["date", "datetime", "iso-string"],
    )
    def test_contract_start_date_formats(self, cp_start: object) -> None:
        contract = SimpleNamespace(cp_start_date=cp_start, cp_duration=61)
        lookup = make_stats_manager(contract=contract).build_period_lookup({})

        assert lookup(D(2026, 3, 5)) == (D(2026, 3, 1), 61)

    @pytest.mark.parametrize(
        "contract",
        [
            None,
            SimpleNamespace(cp_start_date=None, cp_duration=61),
            SimpleNamespace(cp_start_date=D(2026, 3, 1), cp_duration=None),
            SimpleNamespace(cp_start_date="not a date", cp_duration=61),
        ],
        ids=["no-contract", "no-start", "no-duration", "garbage-start"],
    )
    def test_missing_contract_data_falls_back_to_the_approximation(self, contract: object) -> None:
        lookup = make_stats_manager(contract=contract).build_period_lookup({})

        start, days = lookup(D(2026, 3, 5))

        assert days == TARIF_D_HISTORY_PERIOD_DAYS
        assert start <= D(2026, 3, 5) < start + datetime.timedelta(days=days)


# ── Daily sync path ───────────────────────────────────────────────────────────


class TestDailySync:
    def manager(self, contract: object, consumed_before: float, base_sum: float = 100.0):
        mgr = make_stats_manager(contract=contract)
        mgr._get_period_consumption_before_date = AsyncMock(return_value=consumed_before)
        mgr.get_base_sum = AsyncMock(return_value=base_sum)
        return mgr

    async def test_day_crossing_the_allowance_splits_hour_by_hour(self) -> None:
        start = D(2026, 3, 1)  # 60 days => 2400 kWh allowance
        mgr = self.manager(contract_for(start, 60), consumed_before=2388.5)

        reg = await mgr._split_day_for_tarif_d(D(2026, 3, 11), day_of_hours(1.0), "reg", TZ)
        haut = await mgr._split_day_for_tarif_d(D(2026, 3, 11), day_of_hours(1.0), "haut", TZ)

        # 11.5 kWh of allowance left: 11 full hours, a half hour, then high price
        assert [h["state"] for h in reg] == [1.0] * 11 + [0.5] + [0.0] * 12
        assert [h["state"] for h in haut] == [0.0] * 11 + [0.5] + [1.0] * 12
        # Cumulative sums continue from the previous day's base sum
        assert reg[-1]["sum"] == pytest.approx(100.0 + 11.5)
        assert haut[-1]["sum"] == pytest.approx(100.0 + 12.5)
        assert reg[0]["start"] == datetime.datetime(2026, 3, 11, 0, 0, tzinfo=TZ)
        assert reg[-1]["start"] == datetime.datetime(2026, 3, 11, 23, 0, tzinfo=TZ)

    async def test_consumption_is_counted_from_the_start_of_the_current_period(self) -> None:
        start = D(2026, 3, 1)
        mgr = self.manager(contract_for(start, 60), consumed_before=0.0)

        await mgr._split_day_for_tarif_d(D(2026, 3, 11), day_of_hours(1.0), "reg", TZ)

        mgr._get_period_consumption_before_date.assert_awaited_once_with(
            "hydroqc:maison_total_hourly_consumption", D(2026, 3, 11), start
        )

    async def test_last_day_of_the_previous_period_is_split_against_that_period(self) -> None:
        """Regression: once the contract rolled over, yesterday still belongs to the old period.

        Counting from the new period's start gave "nothing consumed yet" and sent the
        whole day to the low price tier, overwriting correct statistics.
        """
        new_start = D(2026, 3, 1)
        mgr = self.manager(contract_for(new_start, 60), consumed_before=2390.0)

        reg = await mgr._split_day_for_tarif_d(D(2026, 2, 28), day_of_hours(1.0), "reg", TZ)

        period_start_used = mgr._get_period_consumption_before_date.await_args.args[2]
        assert period_start_used < new_start
        # 2390 already consumed in that period: only 10 kWh of allowance remain
        assert sum(h["state"] for h in reg) == pytest.approx(10.0)

    async def test_process_day_writes_split_streams_that_add_up_to_the_total(self) -> None:
        mgr = self.manager(contract_for(D(2026, 3, 1), 60), consumed_before=2390.0, base_sum=0.0)
        written: dict[str, list[dict[str, object]]] = {}

        def capture(_hass: object, metadata: dict[str, str], batch: list[dict[str, object]]):
            written[metadata["statistic_id"]] = batch

        instance = MagicMock()

        async def run(func, *args):
            return func(*args)

        instance.async_add_executor_job = run
        with (
            patch(f"{STATISTICS_MANAGER}.get_instance", return_value=instance),
            patch(f"{STATISTICS_MANAGER}.statistics.async_add_external_statistics", capture),
        ):
            await mgr._process_day_consumption(
                D(2026, 3, 11), day_of_hours(3.0), ["total", "reg", "haut"], TZ
            )

        total = written["hydroqc:maison_total_hourly_consumption"]
        reg = written["hydroqc:maison_reg_hourly_consumption"]
        haut = written["hydroqc:maison_haut_hourly_consumption"]
        assert len(total) == len(reg) == len(haut) == 24
        for t, r, h in zip(total, reg, haut, strict=True):
            assert r["state"] + h["state"] == pytest.approx(t["state"])
        assert sum(r["state"] for r in reg) == pytest.approx(10.0)  # allowance left
        assert sum(h["state"] for h in haut) == pytest.approx(72.0 - 10.0)


# ── CSV history import path ───────────────────────────────────────────────────


class TestCsvImportSplit:
    def importer(self, contract: object, consumed_before: float):
        mgr = make_stats_manager(contract=contract)
        mgr._get_period_consumption_before_date = AsyncMock(return_value=consumed_before)
        imp = ConsumptionHistoryImporter.__new__(ConsumptionHistoryImporter)
        imp._statistics_manager = mgr
        imp._get_statistic_id = mgr._get_statistic_id
        return imp

    @staticmethod
    def hours(first: D, days: int, kwh: float) -> list[dict[str, object]]:
        return [
            {
                "start": datetime.datetime.combine(
                    first + datetime.timedelta(days=d), datetime.time(h), tzinfo=TZ
                ),
                "state": kwh,
            }
            for d in range(days)
            for h in range(24)
        ]

    async def test_chunk_spanning_two_periods_restarts_the_allowance(self) -> None:
        """Regression: one allowance for the whole chunk made everything after it high price."""
        current_start = D(2026, 3, 1)
        previous_start = current_start - datetime.timedelta(days=TARIF_D_HISTORY_PERIOD_DAYS)
        # 4 days at the end of the previous period (10 kWh of allowance left),
        # then 3 days in the current one: 48 kWh/day
        chunk = self.hours(current_start - datetime.timedelta(days=4), 7, 2.0)
        imp = self.importer(contract_for(current_start, 60), consumed_before=2390.0)

        reg = await imp._apply_tarif_d_split(chunk, "reg")
        haut = await imp._apply_tarif_d_split(chunk, "haut")

        first_period = [i for i, r in enumerate(chunk) if r["start"].date() < current_start]
        second_period = [i for i, r in enumerate(chunk) if r["start"].date() >= current_start]
        assert previous_start < current_start
        assert sum(reg[i]["state"] for i in first_period) == pytest.approx(10.0)
        assert sum(haut[i]["state"] for i in first_period) == pytest.approx(4 * 48.0 - 10.0)
        # New period: the whole 3 days (144 kWh) fit in the fresh 2400 kWh allowance
        assert sum(reg[i]["state"] for i in second_period) == pytest.approx(3 * 48.0)
        assert sum(haut[i]["state"] for i in second_period) == pytest.approx(0.0)
        assert [r["start"] for r in reg] == [r["start"] for r in chunk]

    async def test_chunk_starts_from_what_the_period_already_consumed(self) -> None:
        start = D(2026, 3, 1)
        imp = self.importer(contract_for(start, 60), consumed_before=2380.0)
        chunk = self.hours(D(2026, 3, 11), 1, 2.0)

        reg = await imp._apply_tarif_d_split(chunk, "reg")

        assert sum(r["state"] for r in reg) == pytest.approx(20.0)
        imp._statistics_manager._get_period_consumption_before_date.assert_awaited_with(
            "hydroqc:maison_total_hourly_consumption", D(2026, 3, 11), start
        )

    async def test_empty_chunk_is_returned_untouched(self) -> None:
        imp = self.importer(contract_for(D(2026, 3, 1), 60), consumed_before=0.0)

        assert await imp._apply_tarif_d_split([], "reg") == []


# ── One-time history re-split ─────────────────────────────────────────────────


class TestResplitHistory:
    @staticmethod
    def total_rows(first: D, days: int, kwh: float) -> list[dict[str, float]]:
        start = datetime.datetime.combine(first, datetime.time.min, tzinfo=TZ)
        return [
            {"start": (start + datetime.timedelta(hours=h)).timestamp(), "state": kwh, "sum": 0.0}
            for h in range(days * 24)
        ]

    def run_resplit(self, mgr, rows: list[dict[str, float]] | None):
        """Run resplit_tarif_d_history against fakes; return what was written per statistic."""
        written: dict[str, list[dict[str, object]]] = {}
        total_id = mgr._get_statistic_id("total")

        def query(*_args: object) -> dict[str, list[dict[str, float]]]:
            return {total_id: rows} if rows is not None else {}

        def capture(_hass: object, metadata: dict[str, str], batch: list[dict[str, object]]):
            written.setdefault(metadata["statistic_id"], []).extend(batch)

        instance = MagicMock()

        async def run(func, *args):
            return func(*args)

        instance.async_add_executor_job = run
        patches = (
            patch(f"{STATISTICS_MANAGER}.get_instance", return_value=instance),
            patch(f"{STATISTICS_MANAGER}.statistics.statistics_during_period", query),
            patch(f"{STATISTICS_MANAGER}.statistics.async_add_external_statistics", capture),
            patch(f"{STATISTICS_MANAGER}.asyncio.sleep", AsyncMock()),
            freeze_time("2026-01-15 12:00:00"),
        )
        return written, patches

    async def test_every_period_gets_its_own_allowance(self) -> None:
        mgr = make_stats_manager(billing_duration_entity="sensor.duration")
        mgr._get_billing_period_durations = AsyncMock(
            return_value={D(2026, 1, 1): 5, D(2026, 1, 6): 5}
        )
        rows = self.total_rows(D(2026, 1, 1), 10, 2.0)  # 240 kWh per 5-day period
        written, patches = self.run_resplit(mgr, rows)

        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            await mgr.resplit_tarif_d_history()

        reg = written["hydroqc:maison_reg_hourly_consumption"]
        haut = written["hydroqc:maison_haut_hourly_consumption"]
        assert len(reg) == len(haut) == 240
        assert sum(r["state"] for r in reg[:120]) == pytest.approx(200.0)
        assert sum(h["state"] for h in haut[:120]) == pytest.approx(40.0)
        assert sum(r["state"] for r in reg[120:]) == pytest.approx(200.0)
        assert sum(h["state"] for h in haut[120:]) == pytest.approx(40.0)
        assert reg[120]["state"] == 2.0  # first hour of period 2 is low price again
        for r, h in zip(reg, haut, strict=True):
            assert r["state"] + h["state"] == pytest.approx(2.0)
        # Cumulative sums never go backwards and end at the stream totals
        assert all(a["sum"] <= b["sum"] for a, b in itertools.pairwise(reg))
        assert reg[-1]["sum"] == pytest.approx(400.0)
        assert haut[-1]["sum"] == pytest.approx(80.0)

    async def test_the_total_stream_is_never_modified(self) -> None:
        mgr = make_stats_manager(billing_duration_entity="sensor.duration")
        mgr._get_billing_period_durations = AsyncMock(return_value={D(2026, 1, 1): 5})
        written, patches = self.run_resplit(mgr, self.total_rows(D(2026, 1, 1), 2, 1.0))

        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            await mgr.resplit_tarif_d_history()

        assert set(written) == {
            "hydroqc:maison_reg_hourly_consumption",
            "hydroqc:maison_haut_hourly_consumption",
        }

    async def test_without_period_history_the_contract_period_is_the_anchor(self) -> None:
        # Current period: 5 days from Jan 6. Jan 1-5 is approximated as the previous period.
        mgr = make_stats_manager(contract=contract_for(D(2026, 1, 6), 5))
        mgr._get_billing_period_durations = AsyncMock(return_value={})
        rows = self.total_rows(D(2026, 1, 6), 5, 2.0)  # 240 kWh in a 200 kWh period
        written, patches = self.run_resplit(mgr, rows)

        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            await mgr.resplit_tarif_d_history()

        reg = written["hydroqc:maison_reg_hourly_consumption"]
        assert sum(r["state"] for r in reg) == pytest.approx(200.0)

    @pytest.mark.parametrize("rows", [None, []], ids=["no-stream", "empty-stream"])
    async def test_nothing_to_split_writes_nothing(self, rows: list | None) -> None:
        mgr = make_stats_manager()
        mgr._get_billing_period_durations = AsyncMock(return_value={})
        written, patches = self.run_resplit(mgr, rows)

        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            await mgr.resplit_tarif_d_history()

        assert written == {}


# ── Service entry point ───────────────────────────────────────────────────────


class FakeCoordinator(ConsumptionSyncMixin):
    """Just enough coordinator for the re-split entry point."""

    def __init__(self, rate: str, portal: bool = True) -> None:
        self.is_portal_mode = portal  # type: ignore[misc]
        self._rate = rate
        self._resplit_task = None
        self._ensure_helper_modules = MagicMock()
        self._statistics_manager = MagicMock()
        self._statistics_manager.resplit_tarif_d_history = AsyncMock()


class TestResplitService:
    async def test_tarif_d_in_portal_mode_runs_the_resplit(self) -> None:
        coordinator = FakeCoordinator("D")

        coordinator.async_resplit_tarif_d_history()
        assert coordinator._resplit_task is not None  # a reference is kept
        await coordinator._resplit_task

        coordinator._statistics_manager.resplit_tarif_d_history.assert_awaited_once()

    async def test_tarif_d_with_the_cpc_option_runs_the_resplit(self) -> None:
        """DCPC is rate D plus the CPC option: the coordinator's base rate is still "D"."""
        coordinator = FakeCoordinator("D")
        coordinator._rate_option = "CPC"

        coordinator.async_resplit_tarif_d_history()
        await coordinator._resplit_task

        coordinator._statistics_manager.resplit_tarif_d_history.assert_awaited_once()

    @pytest.mark.parametrize("rate", ["DT", "DPC", "M"])
    async def test_other_rates_do_nothing(self, rate: str) -> None:
        coordinator = FakeCoordinator(rate)

        coordinator.async_resplit_tarif_d_history()

        assert coordinator._resplit_task is None
        coordinator._statistics_manager.resplit_tarif_d_history.assert_not_called()

    async def test_opendata_mode_does_nothing(self) -> None:
        coordinator = FakeCoordinator("D", portal=False)

        coordinator.async_resplit_tarif_d_history()

        assert coordinator._resplit_task is None

    async def test_a_failing_resplit_is_logged_not_raised(self) -> None:
        coordinator = FakeCoordinator("D")
        coordinator._statistics_manager.resplit_tarif_d_history.side_effect = RuntimeError("boom")

        coordinator.async_resplit_tarif_d_history()
        await coordinator._resplit_task  # must not raise
