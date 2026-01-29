"""Calendar-based peak handler for Hydro-Québec winter peaks.

This module provides a peak handler that reads events from a Home Assistant
calendar entity instead of the OpenData API. This makes sensors resilient
to restarts and API timing issues since the calendar is the persistent
source of truth.
"""

from __future__ import annotations

import datetime
import logging
import re
import zoneinfo
from typing import TYPE_CHECKING, Any

from homeassistant.components.calendar import CalendarEntity

from .public_data.models import AnchorPeriod
from .utils import get_winter_season_bounds, is_winter_season

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Timezone for all peak events
TZ = zoneinfo.ZoneInfo("America/Toronto")


class CalendarPeakEvent:
    """Represents a peak event parsed from a calendar event."""

    def __init__(
        self,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
        is_critical: bool,
        rate: str,
        preheat_duration: int = 120,
    ) -> None:
        """Initialize calendar peak event.

        Args:
            start_date: Event start datetime (timezone-aware)
            end_date: Event end datetime (timezone-aware)
            is_critical: Whether this is a critical peak
            rate: Rate code (DPC or DCPC)
            preheat_duration: Pre-heat duration in minutes
        """
        self.start_date = start_date
        self.end_date = end_date
        self._is_critical = is_critical
        self.rate = rate
        self._preheat_duration = preheat_duration

        # Determine time slot (AM or PM) based on start hour
        self.time_slot = "AM" if start_date.hour < 12 else "PM"

        # For compatibility with PeakEvent
        self.offer = "CPC-D" if rate == "DCPC" else "TPC-DPC"
        self.sector = "Résidentiel"

    @property
    def is_critical(self) -> bool:
        """Return whether this is a critical peak."""
        return self._is_critical

    @property
    def preheat(self) -> PreHeatPeriod:
        """Get pre-heat period for this peak."""
        return PreHeatPeriod(self.start_date, self._preheat_duration)

    @property
    def anchor(self) -> AnchorPeriod:
        """Get anchor period for this peak (Winter Credits)."""
        is_morning = self.time_slot == "AM"
        return AnchorPeriod(self.start_date, is_morning, self.is_critical)


class PreHeatPeriod:
    """Represents a pre-heat period before a peak."""

    def __init__(self, peak_start: datetime.datetime, duration_minutes: int) -> None:
        """Initialize pre-heat period."""
        self.start_date = peak_start - datetime.timedelta(minutes=duration_minutes)
        self.end_date = peak_start


class CalendarPeakHandler:
    """Handles peak events read from a Home Assistant calendar entity.

    This handler reads critical peak events from a calendar and generates
    non-critical DCPC schedule locally. It provides the same interface as
    PeakHandler for sensor compatibility.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        calendar_entity_id: str,
        rate_code: str,
        preheat_duration: int = 120,
    ) -> None:
        """Initialize calendar peak handler.

        Args:
            hass: Home Assistant instance
            calendar_entity_id: Entity ID of the calendar to read from
            rate_code: Rate code (DCPC, DPC, etc.)
            preheat_duration: Pre-heat duration in minutes (default 120)
        """
        self.hass = hass
        self.calendar_entity_id = calendar_entity_id
        self.rate_code = rate_code
        self.preheat_duration = preheat_duration
        self._events: list[CalendarPeakEvent] = []
        self._calendar_name: str | None = None
        self._last_load: datetime.datetime | None = None

    @property
    def calendar_name(self) -> str | None:
        """Return the friendly name of the calendar entity."""
        return self._calendar_name

    async def async_load_events(self) -> bool:
        """Load peak events from the calendar entity.

        Queries the calendar for the next 7 days and parses hydroqc events.
        For DCPC, also generates non-critical schedule for today/tomorrow.

        Returns:
            True if events were loaded successfully, False otherwise.
        """
        try:
            # Get calendar component
            component = self.hass.data.get("calendar")
            if not component:
                _LOGGER.debug("Calendar component not loaded")
                return False

            # Find calendar entity
            calendar_entity: CalendarEntity | None = None
            for entity in component.entities:
                if entity.entity_id == self.calendar_entity_id:
                    calendar_entity = entity
                    break

            if not calendar_entity or not isinstance(calendar_entity, CalendarEntity):
                _LOGGER.debug(
                    "Calendar entity %s not found or not a CalendarEntity",
                    self.calendar_entity_id,
                )
                return False

            # Store calendar friendly name for attribution
            self._calendar_name = (
                str(calendar_entity.name) if calendar_entity.name else self.calendar_entity_id
            )

            # Query calendar for next 7 days
            now = datetime.datetime.now(TZ)
            end_date = now + datetime.timedelta(days=7)

            calendar_events = await calendar_entity.async_get_events(self.hass, now, end_date)

            # Parse calendar events to extract hydroqc peak events
            critical_events: list[CalendarPeakEvent] = []
            for event in calendar_events:
                peak = self._parse_calendar_event(event)
                if peak:
                    critical_events.append(peak)

            _LOGGER.debug(
                "[Calendar] Found %d hydroqc events in calendar %s",
                len(critical_events),
                self.calendar_entity_id,
            )

            # For DCPC, generate non-critical schedule and merge
            if self.rate_code == "DCPC":
                generated_peaks = self._generate_dcpc_schedule()

                # Track critical event date+timeslot for deduplication
                critical_slots = {(e.start_date.date(), e.time_slot) for e in critical_events}

                # Merge: critical events from calendar + non-critical generated
                merged_events: list[CalendarPeakEvent] = list(critical_events)
                for gen_peak in generated_peaks:
                    key = (gen_peak.start_date.date(), gen_peak.time_slot)
                    if key not in critical_slots:
                        merged_events.append(gen_peak)

                self._events = sorted(merged_events, key=lambda e: e.start_date)

                _LOGGER.debug(
                    "[Calendar] DCPC: %d critical (calendar) + %d non-critical (generated) = %d total",
                    len(critical_events),
                    len([e for e in self._events if not e.is_critical]),
                    len(self._events),
                )
            else:
                # For DPC, only use calendar events (all critical)
                self._events = sorted(critical_events, key=lambda e: e.start_date)

            self._last_load = now
            return True

        except Exception as err:
            _LOGGER.warning("Failed to load events from calendar: %s", err)
            return False

    def _parse_calendar_event(self, event: Any) -> CalendarPeakEvent | None:
        """Parse a calendar event to extract hydroqc peak data.

        Args:
            event: Calendar event from async_get_events

        Returns:
            CalendarPeakEvent if this is a hydroqc event, None otherwise.
        """
        description = event.description or ""

        # Check if this is a hydroqc event by looking for our UID pattern
        if "ID: hydroqc_" not in description:
            return None

        try:
            # Extract criticality from description
            # Format: "Critique: Oui" or "Critique: Non"
            is_critical = "Critique: Oui" in description

            # Extract rate from description or location
            # Format in description: "Tarif: DPC" or "Tarif: DCPC"
            rate = self.rate_code  # Default to configured rate
            rate_match = re.search(r"Tarif:\s*(DPC|DCPC)", description)
            if rate_match:
                rate = rate_match.group(1)

            # Get start and end times from event
            start_date = event.start
            end_date = event.end

            # Ensure timezone awareness
            if start_date.tzinfo is None:
                start_date = start_date.replace(tzinfo=TZ)
            if end_date.tzinfo is None:
                end_date = end_date.replace(tzinfo=TZ)

            return CalendarPeakEvent(
                start_date=start_date,
                end_date=end_date,
                is_critical=is_critical,
                rate=rate,
                preheat_duration=self.preheat_duration,
            )

        except Exception as err:
            _LOGGER.warning("Failed to parse calendar event: %s", err)
            return None

    def _generate_dcpc_schedule(self) -> list[CalendarPeakEvent]:
        """Generate DCPC (Winter Credits) peak schedule for today and tomorrow.

        Winter Credits has a fixed schedule during winter season (Dec 1 - Mar 31):
        - Morning Peak: 6:00-10:00 (4 hours)
        - Evening Peak: 16:00-20:00 (4 hours)

        Returns empty list if outside winter season.
        """
        now = datetime.datetime.now(TZ)
        today = now.date()

        # Check if we're in winter season (Dec 1 - Mar 31)
        if not is_winter_season(today):
            winter_start, winter_end = get_winter_season_bounds(today)
            _LOGGER.debug(
                "[Calendar] Outside winter season (%s to %s), no DCPC schedule generated",
                winter_start,
                winter_end,
            )
            return []

        generated_peaks: list[CalendarPeakEvent] = []

        for day_offset in [0, 1]:  # 0=today, 1=tomorrow
            target_date = today + datetime.timedelta(days=day_offset)

            # Morning peak: 6:00-10:00
            morning_start = datetime.datetime.combine(target_date, datetime.time(6, 0), tzinfo=TZ)
            morning_end = datetime.datetime.combine(target_date, datetime.time(10, 0), tzinfo=TZ)
            generated_peaks.append(
                CalendarPeakEvent(
                    start_date=morning_start,
                    end_date=morning_end,
                    is_critical=False,
                    rate="DCPC",
                    preheat_duration=self.preheat_duration,
                )
            )

            # Evening peak: 16:00-20:00
            evening_start = datetime.datetime.combine(target_date, datetime.time(16, 0), tzinfo=TZ)
            evening_end = datetime.datetime.combine(target_date, datetime.time(20, 0), tzinfo=TZ)
            generated_peaks.append(
                CalendarPeakEvent(
                    start_date=evening_start,
                    end_date=evening_end,
                    is_critical=False,
                    rate="DCPC",
                    preheat_duration=self.preheat_duration,
                )
            )

        return generated_peaks

    # =========================================================================
    # Properties matching PeakHandler interface for sensor compatibility
    # =========================================================================

    @property
    def next_peak(self) -> CalendarPeakEvent | None:
        """Get next upcoming peak event."""
        now = datetime.datetime.now(TZ)
        upcoming = [e for e in self._events if e.end_date > now]
        return min(upcoming, key=lambda e: e.start_date, default=None) if upcoming else None

    @property
    def next_critical_peak(self) -> CalendarPeakEvent | None:
        """Get next critical peak event."""
        now = datetime.datetime.now(TZ)
        upcoming = [e for e in self._events if e.end_date > now and e.is_critical]
        return min(upcoming, key=lambda e: e.start_date, default=None) if upcoming else None

    @property
    def current_peak(self) -> CalendarPeakEvent | None:
        """Get current active peak if any."""
        now = datetime.datetime.now(TZ)
        for event in self._events:
            if event.start_date <= now <= event.end_date:
                return event
        return None

    @property
    def current_state(self) -> str:
        """Get current state description.

        Returns hydroqc2mqtt-compatible values:
        - "off_season": Outside winter season
        - "critical_peak": During a critical peak
        - "peak": During a non-critical peak
        - "critical_anchor": During an anchor period before a critical peak
        - "anchor": During an anchor period before a non-critical peak
        - "normal": Regular period
        """
        now = datetime.datetime.now(TZ)

        # Check if we're in winter season (Dec 1 - Mar 31)
        if not is_winter_season(now):
            return "off_season"

        # Check if currently in a peak
        current = self.current_peak
        if current:
            return "critical_peak" if current.is_critical else "peak"

        # Check if currently in an anchor period (DCPC only)
        if self.rate_code == "DCPC":
            for event in self._events:
                anchor = event.anchor
                if anchor.start_date <= now < anchor.end_date:
                    return "critical_anchor" if anchor.is_critical else "anchor"

        return "normal"

    @property
    def current_peak_is_critical(self) -> bool:
        """Check if current peak is critical."""
        current = self.current_peak
        return current.is_critical if current else False

    @property
    def preheat_in_progress(self) -> bool:
        """Check if pre-heat is in progress."""
        now = datetime.datetime.now(TZ)
        next_event = self.next_peak
        if not next_event:
            return False

        preheat_start = next_event.start_date - datetime.timedelta(minutes=self.preheat_duration)
        return preheat_start <= now < next_event.start_date

    @property
    def peak_in_progress(self) -> bool:
        """Check if a peak is currently in progress."""
        return self.current_peak is not None

    @property
    def is_any_critical_peak_coming(self) -> bool:
        """Check if any critical peak is coming."""
        return self.next_critical_peak is not None

    def _get_peak_for_period(self, period_start: datetime.datetime) -> CalendarPeakEvent | None:
        """Get peak event for a specific period."""
        # Ensure timezone-aware
        if period_start.tzinfo is None:
            period_start = period_start.replace(tzinfo=TZ)

        for event in self._events:
            if event.start_date <= period_start < event.end_date:
                return event
        return None

    @property
    def today_morning_peak(self) -> CalendarPeakEvent | None:
        """Get today's morning peak (6AM-10AM)."""
        now = datetime.datetime.now(TZ)
        morning_start = now.replace(hour=6, minute=0, second=0, microsecond=0)
        return self._get_peak_for_period(morning_start)

    @property
    def today_evening_peak(self) -> CalendarPeakEvent | None:
        """Get today's evening peak (4PM-8PM)."""
        now = datetime.datetime.now(TZ)
        evening_start = now.replace(hour=16, minute=0, second=0, microsecond=0)
        return self._get_peak_for_period(evening_start)

    @property
    def tomorrow_morning_peak(self) -> CalendarPeakEvent | None:
        """Get tomorrow's morning peak (6AM-10AM)."""
        now = datetime.datetime.now(TZ)
        tomorrow = now + datetime.timedelta(days=1)
        morning_start = tomorrow.replace(hour=6, minute=0, second=0, microsecond=0)
        return self._get_peak_for_period(morning_start)

    @property
    def tomorrow_evening_peak(self) -> CalendarPeakEvent | None:
        """Get tomorrow's evening peak (4PM-8PM)."""
        now = datetime.datetime.now(TZ)
        tomorrow = now + datetime.timedelta(days=1)
        evening_start = tomorrow.replace(hour=16, minute=0, second=0, microsecond=0)
        return self._get_peak_for_period(evening_start)

    @property
    def next_anchor(self) -> AnchorPeriod | None:
        """Get next anchor period (for Winter Credits)."""
        next_event = self.next_peak
        if not next_event:
            return None
        return next_event.anchor
