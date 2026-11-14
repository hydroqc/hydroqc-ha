"""Unit tests for the year-over-year rolling window sensors."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydroqc.const import SENSORS
from custom_components.hydroqc.coordinator import HydroQcDataCoordinator, yoy_stats
from custom_components.hydroqc.coordinator.yoy_stats import (
    _TZ,
    YOY_METRICS,
    YoYStatsMixin,
    _one_year_earlier,
)
from custom_components.hydroqc.sensor import HydroQcSensor

D = datetime.date
UTC = datetime.UTC
COMPONENT = Path(yoy_stats.__file__).parent.parent


# ── In-memory recorder ────────────────────────────────────────────────────────


class FakeRecorder:
    """Stores hourly values keyed by their UTC start and answers range queries."""

    def __init__(self) -> None:
        self.rows: dict[datetime.datetime, float] = {}
        self.queries: list[tuple[datetime.datetime, datetime.datetime]] = []
        self.fail = False

    def fill(self, first_day: D, last_day: D, kwh: float) -> None:
        """Add one row per real elapsed hour from local midnight of first_day to last_day."""
        t = datetime.datetime.combine(first_day, datetime.time.min, tzinfo=_TZ).astimezone(UTC)
        end = datetime.datetime.combine(
            last_day + datetime.timedelta(days=1), datetime.time.min, tzinfo=_TZ
        ).astimezone(UTC)
        while t < end:
            self.rows[t] = kwh
            t += datetime.timedelta(hours=1)

    def drop(self, local_hour: datetime.datetime) -> None:
        del self.rows[local_hour.astimezone(UTC)]

    def statistics_during_period(
        self, _hass: Any, start: datetime.datetime, end: datetime.datetime, ids: set[str], *_: Any
    ) -> dict[str, list[dict[str, Any]]]:
        """Mimic recorder semantics: start inclusive, end exclusive."""
        if self.fail:
            raise RuntimeError("recorder unavailable")
        self.queries.append((start, end))
        s, e = start.astimezone(UTC), end.astimezone(UTC)
        found = [
            {"start": t.timestamp(), "state": v} for t, v in sorted(self.rows.items()) if s <= t < e
        ]
        return {next(iter(ids)): found} if found else {}


class Harness(YoYStatsMixin):
    """Minimal stand-in for the coordinator."""

    is_portal_mode = True

    def __init__(self) -> None:
        self.hass = MagicMock()
        self.async_update_listeners = MagicMock()
        self._init_yoy_stats()

    def _get_statistic_id(self, consumption_type: str) -> str:
        return f"hydroqc:test_{consumption_type}_hourly_consumption"


@pytest.fixture
def recorder():
    """Patch the recorder access used by the mixin with an in-memory fake."""
    fake = FakeRecorder()
    instance = MagicMock()

    async def run(func: Any, *args: Any) -> Any:
        return func(*args)

    instance.async_add_executor_job = run
    with (
        patch.object(yoy_stats, "get_instance", return_value=instance),
        patch.object(
            yoy_stats.statistics, "statistics_during_period", fake.statistics_during_period
        ),
    ):
        yield fake


# 2026-06-10 12:00 local, so "yesterday" is 2026-06-09
NOW = "2026-06-10 16:00:00"


def fill_normal_year(rec: FakeRecorder) -> None:
    """Current year at 1.0 kWh/h, last year at 0.5 kWh/h, both covering the 30-day windows."""
    rec.fill(D(2026, 5, 1), D(2026, 6, 9), 1.0)
    rec.fill(D(2025, 5, 1), D(2025, 6, 9), 0.5)


# ── Values ────────────────────────────────────────────────────────────────────


@freeze_time(NOW)
async def test_full_history_computes_every_metric(recorder: FakeRecorder) -> None:
    fill_normal_year(recorder)
    h = Harness()

    await h.async_maybe_recompute_yoy()

    assert h.get_yoy_value("computed_yoy.last_7_days_kwh") == 168.0
    assert h.get_yoy_value("computed_yoy.same_7_days_last_year_kwh") == 84.0
    assert h.get_yoy_value("computed_yoy.yoy_7day_delta_kwh") == 84.0
    assert h.get_yoy_value("computed_yoy.last_30_days_kwh") == 720.0
    assert h.get_yoy_value("computed_yoy.same_30_days_last_year_kwh") == 360.0
    assert h.get_yoy_value("computed_yoy.yoy_30day_delta_kwh") == 360.0
    h.async_update_listeners.assert_called_once()


@freeze_time(NOW)
async def test_delta_can_be_negative(recorder: FakeRecorder) -> None:
    recorder.fill(D(2026, 5, 1), D(2026, 6, 9), 0.5)
    recorder.fill(D(2025, 5, 1), D(2025, 6, 9), 1.0)
    h = Harness()

    await h.async_maybe_recompute_yoy()

    assert h.get_yoy_value("computed_yoy.yoy_7day_delta_kwh") == -84.0


@freeze_time(NOW)
async def test_no_last_year_history_keeps_current_and_blanks_comparison(
    recorder: FakeRecorder,
) -> None:
    recorder.fill(D(2026, 5, 1), D(2026, 6, 9), 1.0)
    h = Harness()

    await h.async_maybe_recompute_yoy()

    assert h.get_yoy_value("computed_yoy.last_7_days_kwh") == 168.0
    assert h.get_yoy_value("computed_yoy.same_7_days_last_year_kwh") is None
    assert h.get_yoy_value("computed_yoy.yoy_7day_delta_kwh") is None
    assert h.get_yoy_value("computed_yoy.same_30_days_last_year_kwh") is None
    assert h.get_yoy_value("computed_yoy.yoy_30day_delta_kwh") is None


@freeze_time(NOW)
async def test_partial_last_year_history_is_none_not_a_partial_sum(recorder: FakeRecorder) -> None:
    """History starting mid-window must not produce a misleadingly small total."""
    recorder.fill(D(2026, 5, 1), D(2026, 6, 9), 1.0)
    # Last year only has the last 4 days of the 7-day window
    recorder.fill(D(2025, 6, 6), D(2025, 6, 9), 0.5)
    h = Harness()

    await h.async_maybe_recompute_yoy()

    assert h.get_yoy_value("computed_yoy.same_7_days_last_year_kwh") is None
    assert h.get_yoy_value("computed_yoy.yoy_7day_delta_kwh") is None


@freeze_time(NOW)
async def test_gap_in_current_window_blanks_current_and_delta_only(recorder: FakeRecorder) -> None:
    fill_normal_year(recorder)
    recorder.drop(datetime.datetime(2026, 6, 5, 14, 0, tzinfo=_TZ))
    h = Harness()

    await h.async_maybe_recompute_yoy()

    assert h.get_yoy_value("computed_yoy.last_7_days_kwh") is None
    assert h.get_yoy_value("computed_yoy.yoy_7day_delta_kwh") is None
    assert h.get_yoy_value("computed_yoy.same_7_days_last_year_kwh") == 84.0


# ── Leap years ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (D(2026, 6, 9), D(2025, 6, 9)),
        (D(2024, 3, 1), D(2023, 3, 1)),  # leap year, after Feb 29
        (D(2025, 3, 1), D(2024, 3, 1)),  # last year was a leap year
        (D(2024, 2, 28), D(2023, 2, 28)),
        (D(2024, 2, 29), D(2023, 2, 28)),  # Feb 29 has no equivalent: use Feb 28
        (D(2028, 2, 29), D(2027, 2, 28)),
        (D(2025, 12, 31), D(2024, 12, 31)),
    ],
)
def test_one_year_earlier(day: D, expected: D) -> None:
    assert _one_year_earlier(day) == expected


@pytest.mark.parametrize(
    ("yesterday", "last_year_first", "last_year_last"),
    [
        # timedelta(days=365) would give 2023-03-02 here (off by one)
        (D(2024, 3, 1), D(2023, 2, 23), D(2023, 3, 1)),
        # Window containing Feb 29: last year must still be 7 days wide
        (D(2028, 2, 29), D(2027, 2, 22), D(2027, 2, 28)),
        # Last year was a leap year: still 7 days, ending on the same date
        (D(2029, 3, 1), D(2028, 2, 24), D(2028, 3, 1)),
        (D(2026, 6, 9), D(2025, 6, 3), D(2025, 6, 9)),
    ],
)
async def test_last_year_window_is_same_width_and_anchored_on_same_date(
    recorder: FakeRecorder, yesterday: D, last_year_first: D, last_year_last: D
) -> None:
    h = Harness()

    await h._async_compute_window(yesterday, 7)

    # Queries are made in order: current window, then last year's window
    ly_start, ly_end = recorder.queries[1]
    assert ly_start.date() == last_year_first
    assert (ly_end - datetime.timedelta(seconds=1)).date() == last_year_last
    assert (last_year_last - last_year_first).days == 6


async def test_leap_day_window_total_uses_seven_full_days(recorder: FakeRecorder) -> None:
    """End to end: a Feb 29 window must compare 7 days with 7 days."""
    recorder.fill(D(2028, 2, 23), D(2028, 2, 29), 1.0)
    recorder.fill(D(2027, 2, 22), D(2027, 2, 28), 0.5)
    h = Harness()

    result = await h._async_compute_window(D(2028, 2, 29), 7)

    assert result["last_7_days_kwh"] == 168.0
    assert result["same_7_days_last_year_kwh"] == 84.0  # 6 days would give 72.0


# ── DST ───────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("yesterday", "expected_current_hours"),
    [
        (D(2025, 11, 5), 169),  # window contains the 25-hour fall-back day (2025-11-02)
        (D(2026, 3, 10), 167),  # window contains the 23-hour spring-forward day (2026-03-08)
    ],
)
async def test_window_with_dst_change_is_complete(
    recorder: FakeRecorder, yesterday: D, expected_current_hours: int
) -> None:
    recorder.fill(yesterday - datetime.timedelta(days=6), yesterday, 1.0)
    last_year_end = yesterday.replace(year=yesterday.year - 1)
    recorder.fill(last_year_end - datetime.timedelta(days=6), last_year_end, 1.0)
    h = Harness()

    result = await h._async_compute_window(yesterday, 7)

    assert result["last_7_days_kwh"] == float(expected_current_hours)


# ── Trigger ───────────────────────────────────────────────────────────────────


@freeze_time(NOW)
async def test_waits_for_yesterdays_last_hour(recorder: FakeRecorder) -> None:
    fill_normal_year(recorder)
    last_hour = datetime.datetime(2026, 6, 9, 23, 0, tzinfo=_TZ)
    saved = recorder.rows[last_hour.astimezone(UTC)]
    recorder.drop(last_hour)
    h = Harness()

    await h.async_maybe_recompute_yoy()

    assert h.get_yoy_value("computed_yoy.last_7_days_kwh") is None
    assert h._yoy_last_computed_date is None
    h.async_update_listeners.assert_not_called()

    # The 23:00 row shows up on a later sync: values are computed then
    recorder.rows[last_hour.astimezone(UTC)] = saved
    await h.async_maybe_recompute_yoy()

    assert h.get_yoy_value("computed_yoy.last_7_days_kwh") == 168.0
    h.async_update_listeners.assert_called_once()


async def test_computed_once_per_day_then_again_the_next_day(recorder: FakeRecorder) -> None:
    fill_normal_year(recorder)
    recorder.fill(D(2026, 6, 10), D(2026, 6, 10), 1.0)
    h = Harness()

    with freeze_time(NOW):
        await h.async_maybe_recompute_yoy()
        queries_after_first = len(recorder.queries)
        await h.async_maybe_recompute_yoy()
        await h.async_maybe_recompute_yoy()
        assert len(recorder.queries) == queries_after_first  # nothing re-queried
        assert h.async_update_listeners.call_count == 1

    # Yesterday (June 10) was a heavy day, so the values really change
    recorder.fill(D(2026, 6, 10), D(2026, 6, 10), 3.0)
    recorder.fill(D(2026, 6, 11), D(2026, 6, 11), 1.0)
    with freeze_time("2026-06-11 16:00:00"):
        await h.async_maybe_recompute_yoy()

    assert len(recorder.queries) > queries_after_first
    assert h.async_update_listeners.call_count == 2
    assert h._yoy_last_computed_date == D(2026, 6, 11)


async def test_sensors_are_not_notified_when_values_did_not_change(
    recorder: FakeRecorder,
) -> None:
    """A recompute that yields the same numbers must not trigger useless state writes."""
    fill_normal_year(recorder)
    h = Harness()

    with freeze_time(NOW):
        await h.async_maybe_recompute_yoy()
    assert h.async_update_listeners.call_count == 1

    # Recompute against identical data, as if a new day began with nothing new
    h._yoy_last_computed_date = None
    with freeze_time(NOW):
        await h.async_maybe_recompute_yoy()

    assert h._yoy_last_computed_date == D(2026, 6, 10)  # it did recompute
    assert h.async_update_listeners.call_count == 1  # but told nobody


@freeze_time(NOW)
async def test_hole_in_recent_window_is_retried_after_the_next_sync(
    recorder: FakeRecorder,
) -> None:
    """An hour not published yet must not freeze the sensors for the whole day."""
    fill_normal_year(recorder)
    hole = datetime.datetime(2026, 6, 5, 14, 0, tzinfo=_TZ)
    recorder.drop(hole)
    h = Harness()

    await h.async_maybe_recompute_yoy()
    assert h.get_yoy_value("computed_yoy.last_7_days_kwh") is None
    assert h._yoy_last_computed_date is None  # not marked done

    recorder.rows[hole.astimezone(UTC)] = 1.0  # the missing hour finally shows up
    await h.async_maybe_recompute_yoy()

    assert h.get_yoy_value("computed_yoy.last_7_days_kwh") == 168.0
    assert h._yoy_last_computed_date == D(2026, 6, 10)


@freeze_time(NOW)
async def test_missing_last_year_does_not_cause_a_query_every_sync(
    recorder: FakeRecorder,
) -> None:
    """During the first year there is never last-year data; do not keep retrying."""
    recorder.fill(D(2026, 5, 1), D(2026, 6, 9), 1.0)
    h = Harness()

    await h.async_maybe_recompute_yoy()
    queries = len(recorder.queries)
    await h.async_maybe_recompute_yoy()

    assert h._yoy_last_computed_date == D(2026, 6, 10)
    assert len(recorder.queries) == queries


@freeze_time(NOW)
async def test_opendata_mode_does_nothing(recorder: FakeRecorder) -> None:
    fill_normal_year(recorder)
    h = Harness()
    h.is_portal_mode = False

    await h.async_maybe_recompute_yoy()

    assert recorder.queries == []
    h.async_update_listeners.assert_not_called()


@freeze_time(NOW)
async def test_recorder_failure_is_not_fatal(recorder: FakeRecorder) -> None:
    fill_normal_year(recorder)
    recorder.fail = True
    h = Harness()

    await h.async_maybe_recompute_yoy()  # must not raise

    assert h.get_yoy_value("computed_yoy.last_7_days_kwh") is None
    h.async_update_listeners.assert_not_called()


def test_unknown_or_uncomputed_metric_is_none() -> None:
    h = Harness()
    assert h.get_yoy_value("computed_yoy.last_7_days_kwh") is None
    assert h.get_yoy_value("computed_yoy.nope") is None


# ── Wiring into the real coordinator ──────────────────────────────────────────


async def test_coordinator_serves_cached_values_to_sensors(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    with patch("custom_components.hydroqc.coordinator.base.WebUser"):
        coordinator = HydroQcDataCoordinator(hass, mock_config_entry)

    assert coordinator.get_sensor_value("computed_yoy.last_7_days_kwh") is None
    coordinator._yoy_metrics["last_7_days_kwh"] = 12.34
    assert coordinator.get_sensor_value("computed_yoy.last_7_days_kwh") == 12.34


async def test_consumption_sync_refreshes_yoy_and_survives_its_failure(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    with patch("custom_components.hydroqc.coordinator.base.WebUser"):
        coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
    coordinator._contract = MagicMock()
    coordinator._ensure_helper_modules = MagicMock()
    coordinator._statistics_manager = MagicMock(fetch_and_import_hourly_consumption=AsyncMock())

    with (
        patch.object(HydroQcDataCoordinator, "is_portal_mode", new_callable=PropertyMock) as portal,
        patch.object(coordinator, "async_maybe_recompute_yoy", new=AsyncMock()) as recompute,
    ):
        portal.return_value = True
        await coordinator.async_fetch_hourly_consumption(D(2026, 6, 9), D(2026, 6, 10))
        recompute.assert_awaited_once()

        recompute.side_effect = RuntimeError("boom")
        await coordinator.async_fetch_hourly_consumption(D(2026, 6, 9), D(2026, 6, 10))  # no raise


# ── Sensor definitions and translations ───────────────────────────────────────


def test_every_metric_has_a_well_formed_sensor_definition() -> None:
    for metric in YOY_METRICS:
        config = SENSORS[metric]
        assert config["data_source"] == f"computed_yoy.{metric}"
        assert config["rates"] == ["ALL"]
        assert config["unit"] == "kWh"
        # Rolling totals rise and fall: an energy device class or a total state
        # class would make HA record bogus long-term statistics.
        assert config["state_class"] == "measurement"
        assert "device_class" not in config
        # Opt-in: a new set of sensors should not appear on every installation
        assert config["disabled_by_default"] is True


@pytest.mark.parametrize(
    "path", ["strings.json", "translations/en.json", "translations/fr.json", "translations/es.json"]
)
def test_every_metric_is_translated(path: str) -> None:
    sensors = json.loads((COMPONENT / path).read_text(encoding="utf-8"))["entity"]["sensor"]
    for metric in YOY_METRICS:
        assert sensors[metric]["name"].strip()


@pytest.mark.parametrize("metric", YOY_METRICS)
def test_entities_start_disabled_in_the_registry(metric: str) -> None:
    """The flag in SENSORS must reach the entity, or HA would enable the sensor."""
    entry = MagicMock()
    entry.data = {"contract_name": "Home", "contract_id": "contract123", "rate": "D"}
    entity = HydroQcSensor(MagicMock(), entry, metric, SENSORS[metric], "1.0")

    assert entity.entity_registry_enabled_default is False
