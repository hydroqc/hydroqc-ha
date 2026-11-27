"""Unit tests for the seasonal gating of peak sensors."""

from __future__ import annotations

from types import SimpleNamespace

from freezegun import freeze_time

from custom_components.hydroqc.coordinator.calendar_sync import CalendarSyncMixin

STATE_SOURCE = "calendar_peak_handler.current_state"
NEXT_PEAK_SOURCE = "calendar_peak_handler.next_peak.start_date"


def _coordinator(rate_option: str) -> SimpleNamespace:
    """Return the minimal coordinator state the mixin method reads."""
    return SimpleNamespace(rate_option=rate_option)


class TestIsSensorSeasonal:
    """Only the sensors that carry season-specific data are gated."""

    @freeze_time("2026-07-15 12:00:00")
    def test_dcpc_state_available_off_season(self) -> None:
        """The winter credit state reports off_season rather than going unknown."""
        assert CalendarSyncMixin.is_sensor_seasonal(_coordinator("CPC"), STATE_SOURCE) is True

    @freeze_time("2026-07-15 12:00:00")
    def test_dcpc_peak_dates_hidden_off_season(self) -> None:
        """Peak dates stay hidden outside the winter season for DCPC."""
        assert CalendarSyncMixin.is_sensor_seasonal(_coordinator("CPC"), NEXT_PEAK_SOURCE) is False

    @freeze_time("2026-07-15 12:00:00")
    def test_dpc_is_never_seasonal(self) -> None:
        """Flex-D peaks exist outside the winter credit season."""
        assert CalendarSyncMixin.is_sensor_seasonal(_coordinator(""), NEXT_PEAK_SOURCE) is True
        assert CalendarSyncMixin.is_sensor_seasonal(_coordinator(""), STATE_SOURCE) is True

    @freeze_time("2026-12-15 12:00:00")
    def test_dcpc_peak_dates_in_season(self) -> None:
        """Inside the winter season every calendar sensor is available."""
        assert CalendarSyncMixin.is_sensor_seasonal(_coordinator("CPC"), NEXT_PEAK_SOURCE) is True

    @freeze_time("2026-07-15 12:00:00")
    def test_opendata_sources_always_available(self) -> None:
        """Public feed sources are not gated at all."""
        assert (
            CalendarSyncMixin.is_sensor_seasonal(
                _coordinator("CPC"), "public_client.peak_handler.current_state"
            )
            is True
        )
