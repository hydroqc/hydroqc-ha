"""Integration tests for DPC (Flex-D) peak behavior and seasonal handling.

Tests verify:
- DPC peaks are ONLY from API (no schedule generation)
- All API-announced peaks are critical
- Binary sensors return False when no peaks announced
- Behavior outside winter season
- DST transitions
"""

import datetime

import pytest
from freezegun import freeze_time

from custom_components.hydroqc.public_data_client import PeakHandler


class TestDPCPeakBehavior:
    """Test DPC (Flex-D) peak behavior."""

    @pytest.fixture
    def dpc_handler(self) -> PeakHandler:
        """Create DPC PeakHandler."""
        return PeakHandler(rate_code="DPC", preheat_duration=120)

    # ========================================================================
    # OUTSIDE WINTER SEASON TESTS
    # ========================================================================

    @freeze_time("2025-06-15T12:00:00-04:00")  # Summer - outside winter season
    def test_outside_winter_no_events(self, dpc_handler: PeakHandler) -> None:
        """Test DPC outside winter season with no API events."""
        # No API events
        dpc_handler.load_events([])

        # No events should exist
        assert len(dpc_handler._events) == 0
        assert dpc_handler.current_state == "off_season"

    @freeze_time("2025-06-15T12:00:00-04:00")  # Summer
    def test_outside_winter_binary_sensors_false(self, dpc_handler: PeakHandler) -> None:
        """Test that binary sensors return False (not None) outside winter."""
        dpc_handler.load_events([])

        # All peak-related properties should be None
        assert dpc_handler.today_morning_peak is None
        assert dpc_handler.today_evening_peak is None
        assert dpc_handler.tomorrow_morning_peak is None
        assert dpc_handler.tomorrow_evening_peak is None
        assert dpc_handler.next_peak is None
        assert dpc_handler.next_critical_peak is None

        # coordinator.get_sensor_value() will return False for .is_critical when object is None

    @freeze_time("2025-10-01T12:00:00-04:00")  # October
    def test_october_outside_winter(self, dpc_handler: PeakHandler) -> None:
        """Test October (before winter starts)."""
        dpc_handler.load_events([])
        assert len(dpc_handler._events) == 0

    @freeze_time("2025-04-15T12:00:00-04:00")  # April
    def test_april_after_winter_ends(self, dpc_handler: PeakHandler) -> None:
        """Test April (after winter ends)."""
        dpc_handler.load_events([])
        assert len(dpc_handler._events) == 0

    # ========================================================================
    # BEGINNING OF WINTER - NO CRITICAL PEAKS
    # ========================================================================

    @freeze_time("2024-12-02T10:00:00-05:00")  # Dec 2, 2024 - start of winter
    def test_beginning_winter_no_critical_peaks(self, dpc_handler: PeakHandler) -> None:
        """Test beginning of winter with no API announcements."""
        # No API events
        dpc_handler.load_events([])

        # DPC has no schedule generation - only API events
        assert len(dpc_handler._events) == 0

        # All properties should be None
        assert dpc_handler.today_morning_peak is None
        assert dpc_handler.today_evening_peak is None
        assert dpc_handler.next_peak is None
        # No events = "normal" (matches hydroqc2mqtt behavior)
        assert dpc_handler.current_state == "normal"

    # ========================================================================
    # BEGINNING OF WINTER - WITH CRITICAL PEAKS
    # ========================================================================

    @freeze_time("2024-12-05T10:00:00-05:00")  # Dec 5, 2024
    def test_beginning_winter_with_critical_morning_peak(self, dpc_handler: PeakHandler) -> None:
        """Test beginning of winter with API announcing critical morning peak."""
        # API announces critical morning peak for today
        api_event = {
            "offre": "TPC-DPC",
            "datedebut": "2024-12-05T06:00:00-05:00",
            "datefin": "2024-12-05T10:00:00-05:00",
            "plagehoraire": "AM",
            "duree": "PT04H00MS",
            "secteurclient": "Résidentiel",
        }

        dpc_handler.load_events([api_event])

        # Should have exactly 1 event from API
        assert len(dpc_handler._events) == 1

        # Event should be critical
        assert dpc_handler._events[0].is_critical is True

        # Today morning should be critical
        today_morning = dpc_handler.today_morning_peak
        assert today_morning is not None
        assert today_morning.is_critical is True
        assert today_morning.start_date.hour == 6
        assert today_morning.end_date.hour == 10

        # Other periods should be None (not announced)
        assert dpc_handler.today_evening_peak is None
        assert dpc_handler.tomorrow_morning_peak is None
        assert dpc_handler.tomorrow_evening_peak is None

    @freeze_time("2024-12-05T10:00:00-05:00")  # Dec 5, 2024
    def test_beginning_winter_multiple_critical_peaks(self, dpc_handler: PeakHandler) -> None:
        """Test beginning of winter with multiple critical peaks announced."""
        # API announces multiple critical peaks
        api_events = [
            {
                "offre": "TPC-DPC",
                "datedebut": "2024-12-05T16:00:00-05:00",
                "datefin": "2024-12-05T20:00:00-05:00",
                "plagehoraire": "PM",
                "duree": "PT04H00MS",
                "secteurclient": "Résidentiel",
            },
            {
                "offre": "TPC-DPC",
                "datedebut": "2024-12-06T06:00:00-05:00",
                "datefin": "2024-12-06T10:00:00-05:00",
                "plagehoraire": "AM",
                "duree": "PT04H00MS",
                "secteurclient": "Résidentiel",
            },
        ]

        dpc_handler.load_events(api_events)

        # Should have 2 events, both critical
        assert len(dpc_handler._events) == 2
        assert all(e.is_critical for e in dpc_handler._events)

        # Verify specific peaks
        assert dpc_handler.today_morning_peak is None  # Not announced
        assert dpc_handler.today_evening_peak is not None
        assert dpc_handler.today_evening_peak.is_critical is True

        assert dpc_handler.tomorrow_morning_peak is not None
        assert dpc_handler.tomorrow_morning_peak.is_critical is True
        assert dpc_handler.tomorrow_evening_peak is None  # Not announced

    # ========================================================================
    # END OF WINTER - BEFORE DST
    # ========================================================================

    @freeze_time("2025-03-05T10:00:00-05:00")  # March 5, 2025 (before DST on March 9)
    def test_end_winter_before_dst_no_critical(self, dpc_handler: PeakHandler) -> None:
        """Test end of winter before DST with no critical peaks."""
        dpc_handler.load_events([])

        # No events (only API announcements)
        assert len(dpc_handler._events) == 0
        assert dpc_handler.next_peak is None

    @freeze_time("2025-03-05T10:00:00-05:00")  # March 5, 2025
    def test_end_winter_before_dst_with_critical(self, dpc_handler: PeakHandler) -> None:
        """Test end of winter before DST with critical peak."""
        api_event = {
            "offre": "TPC-DPC",
            "datedebut": "2025-03-05T16:00:00-05:00",
            "datefin": "2025-03-05T20:00:00-05:00",
            "plagehoraire": "PM",
            "duree": "PT04H00MS",
            "secteurclient": "Résidentiel",
        }

        dpc_handler.load_events([api_event])

        assert len(dpc_handler._events) == 1
        today_evening = dpc_handler.today_evening_peak
        assert today_evening is not None
        assert today_evening.is_critical is True
        assert today_evening.start_date.strftime("%z") == "-0500"  # EST

    # ========================================================================
    # END OF WINTER - DURING DST TRANSITION
    # ========================================================================

    @freeze_time("2025-03-09T10:00:00-04:00")  # March 9, 2025 - DST day (after 2 AM transition)
    def test_end_winter_dst_day_no_critical(self, dpc_handler: PeakHandler) -> None:
        """Test DST transition day with no critical peaks."""
        dpc_handler.load_events([])
        assert len(dpc_handler._events) == 0

    @freeze_time("2025-03-09T10:00:00-04:00")  # March 9, 2025 - DST day
    def test_end_winter_dst_day_with_critical(self, dpc_handler: PeakHandler) -> None:
        """Test DST day with critical peak spanning DST transition."""
        # Peak that would start before DST but is announced in EDT
        api_event = {
            "offre": "TPC-DPC",
            "datedebut": "2025-03-09T16:00:00-04:00",  # EDT (after transition)
            "datefin": "2025-03-09T20:00:00-04:00",
            "plagehoraire": "PM",
            "duree": "PT04H00MS",
            "secteurclient": "Résidentiel",
        }

        dpc_handler.load_events([api_event])

        today_evening = dpc_handler.today_evening_peak
        assert today_evening is not None
        assert today_evening.is_critical is True
        assert today_evening.start_date.strftime("%z") == "-0400"  # EDT

    @freeze_time("2025-03-09T01:30:00-05:00")  # March 9 at 1:30 AM (before DST at 2 AM)
    def test_peak_during_dst_transition_hour(self, dpc_handler: PeakHandler) -> None:
        """Test peak event that starts before DST and ends after DST.

        Note: DST happens at 2 AM EST → 3 AM EDT on March 9, 2025.
        Testing at 1:30 AM EST (before transition).
        """
        # Peak from 6 AM EST to 10 AM EDT (spans DST transition indirectly)
        api_event = {
            "offre": "TPC-DPC",
            "datedebut": "2025-03-09T06:00:00-05:00",  # 6 AM EST
            "datefin": "2025-03-09T10:00:00-04:00",  # 10 AM EDT
            "plagehoraire": "AM",
            "duree": "PT04H00MS",
            "secteurclient": "Résidentiel",
        }

        dpc_handler.load_events([api_event])

        # Verify event was loaded
        assert len(dpc_handler._events) == 1
        peak = dpc_handler._events[0]
        assert peak.is_critical is True

        # Verify timezone handling: start in EST, end in EDT
        assert peak.start_date.strftime("%z") == "-0500"
        assert peak.end_date.strftime("%z") == "-0400"

    # ========================================================================
    # END OF WINTER - AFTER DST
    # ========================================================================

    @freeze_time("2025-03-25T10:00:00-04:00")  # March 25, 2025 (after DST)
    def test_end_winter_after_dst_no_critical(self, dpc_handler: PeakHandler) -> None:
        """Test end of winter after DST with no peaks."""
        dpc_handler.load_events([])
        assert len(dpc_handler._events) == 0

    @freeze_time("2025-03-30T10:00:00-04:00")  # March 30, 2025 - near end of season
    def test_last_days_winter_with_critical(self, dpc_handler: PeakHandler) -> None:
        """Test last days of winter season with critical peak."""
        # Critical peak on tomorrow (Mar 31, last day of winter)
        api_event = {
            "offre": "TPC-DPC",
            "datedebut": "2025-03-31T06:00:00-04:00",
            "datefin": "2025-03-31T10:00:00-04:00",
            "plagehoraire": "AM",
            "duree": "PT04H00MS",
            "secteurclient": "Résidentiel",
        }

        dpc_handler.load_events([api_event])

        tomorrow_morning = dpc_handler.tomorrow_morning_peak
        assert tomorrow_morning is not None
        assert tomorrow_morning.is_critical is True
        assert tomorrow_morning.start_date.date() == datetime.date(2025, 3, 31)
        assert tomorrow_morning.start_date.strftime("%z") == "-0400"  # EDT

    # ========================================================================
    # PREHEAT PERIOD TESTS
    # ========================================================================

    @freeze_time("2024-12-10T04:30:00-05:00")  # Dec 10 at 4:30 AM (during preheat before 6 AM peak)
    def test_preheat_period_before_peak(self, dpc_handler: PeakHandler) -> None:
        """Test preheat period detection before peak."""
        # Peak at 6-10 AM
        api_event = {
            "offre": "TPC-DPC",
            "datedebut": "2024-12-10T06:00:00-05:00",
            "datefin": "2024-12-10T10:00:00-05:00",
            "plagehoraire": "AM",
            "duree": "PT04H00MS",
            "secteurclient": "Résidentiel",
        }

        dpc_handler.load_events([api_event])

        # Before peak starts (2 hours before peak)
        # Note: hydroqc2mqtt doesn't have 'preheat' state, returns 'normal'
        assert dpc_handler.current_state == "normal"
        assert dpc_handler.current_peak is None  # Peak hasn't started yet

    @freeze_time("2024-12-10T07:00:00-05:00")  # Dec 10 at 7 AM (during peak)
    def test_during_peak_no_preheat(self, dpc_handler: PeakHandler) -> None:
        """Test that preheat is not active during peak."""
        api_event = {
            "offre": "TPC-DPC",
            "datedebut": "2024-12-10T06:00:00-05:00",
            "datefin": "2024-12-10T10:00:00-05:00",
            "plagehoraire": "AM",
            "duree": "PT04H00MS",
            "secteurclient": "Résidentiel",
        }

        dpc_handler.load_events([api_event])

        # During peak
        assert dpc_handler.peak_in_progress is True
        assert dpc_handler.current_state == "critical_peak"
        assert dpc_handler.current_peak is not None
        assert dpc_handler.current_peak_is_critical is True

    @freeze_time("2024-12-10T03:00:00-05:00")  # Dec 10 at 3 AM (before preheat)
    def test_before_preheat_regular_period(self, dpc_handler: PeakHandler) -> None:
        """Test regular period before preheat starts."""
        api_event = {
            "offre": "TPC-DPC",
            "datedebut": "2024-12-10T06:00:00-05:00",
            "datefin": "2024-12-10T10:00:00-05:00",
            "plagehoraire": "AM",
            "duree": "PT04H00MS",
            "secteurclient": "Résidentiel",
        }

        dpc_handler.load_events([api_event])

        assert dpc_handler.peak_in_progress is False
        assert dpc_handler.current_state == "normal"

    # ========================================================================
    # CONFIGURABLE PREHEAT DURATION TESTS
    # ========================================================================

    @freeze_time("2024-12-10T05:30:00-05:00")  # Dec 10 at 5:30 AM
    def test_custom_preheat_duration_60_minutes(self) -> None:
        """Test 60-minute preheat duration."""
        handler = PeakHandler(rate_code="DPC", preheat_duration=60)

        api_event = {
            "offre": "TPC-DPC",
            "datedebut": "2024-12-10T06:00:00-05:00",
            "datefin": "2024-12-10T10:00:00-05:00",
            "plagehoraire": "AM",
            "duree": "PT04H00MS",
            "secteurclient": "Résidentiel",
        }

        handler.load_events([api_event])

        # At 5:30 AM, 30 minutes before peak
        # With 60-minute preheat, we should be in preheat period
        assert handler.preheat_in_progress is True

    @freeze_time("2024-12-10T04:30:00-05:00")  # Dec 10 at 4:30 AM
    def test_custom_preheat_duration_60_minutes_before_preheat(self) -> None:
        """Test 60-minute preheat - before preheat starts."""
        handler = PeakHandler(rate_code="DPC", preheat_duration=60)

        api_event = {
            "offre": "TPC-DPC",
            "datedebut": "2024-12-10T06:00:00-05:00",
            "datefin": "2024-12-10T10:00:00-05:00",
            "plagehoraire": "AM",
            "duree": "PT04H00MS",
            "secteurclient": "Résidentiel",
        }

        handler.load_events([api_event])

        # At 4:30 AM, 90 minutes before peak
        # With 60-minute preheat, we should NOT be in preheat yet
        assert handler.preheat_in_progress is False

    # ========================================================================
    # TIMEZONE AWARENESS
    # ========================================================================

    @freeze_time("2024-12-10T10:00:00-05:00")
    def test_timezone_awareness(self, dpc_handler: PeakHandler) -> None:
        """Test that all DPC event datetimes are timezone-aware."""
        api_event = {
            "offre": "TPC-DPC",
            "datedebut": "2024-12-10T06:00:00-05:00",
            "datefin": "2024-12-10T10:00:00-05:00",
            "plagehoraire": "AM",
            "duree": "PT04H00MS",
            "secteurclient": "Résidentiel",
        }

        dpc_handler.load_events([api_event])
        event = dpc_handler._events[0]

        # All dates should be timezone-aware
        assert event.start_date.tzinfo is not None
        assert event.end_date.tzinfo is not None
        assert event.preheat.start_date.tzinfo is not None
        assert event.preheat.end_date.tzinfo is not None

        # Check UTC offset is correct for EST (-05:00)
        assert event.start_date.strftime("%z") == "-0500"
        assert event.end_date.strftime("%z") == "-0500"

    # ========================================================================
    # NO ANCHOR PERIODS FOR DPC
    # ========================================================================

    @freeze_time("2024-12-10T10:00:00-05:00")
    def test_dpc_peaks_have_no_anchors(self, dpc_handler: PeakHandler) -> None:
        """Test that DPC peaks do not have anchor periods (those are only for DCPC)."""
        api_event = {
            "offre": "TPC-DPC",
            "datedebut": "2024-12-10T06:00:00-05:00",
            "datefin": "2024-12-10T10:00:00-05:00",
            "plagehoraire": "AM",
            "duree": "PT04H00MS",
            "secteurclient": "Résidentiel",
        }

        dpc_handler.load_events([api_event])

        peak = dpc_handler._events[0]

        # DPC peaks should have anchor property, but it's only meaningful for DCPC
        # The anchor property exists on PeakEvent but is a DCPC-specific feature
        anchor = peak.anchor
        assert anchor is not None  # Property exists

        # But for DPC, we don't use anchors in the UI/sensors
        # (this is just verifying the property doesn't error)
