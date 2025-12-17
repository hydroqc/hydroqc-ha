"""Peak handler for Hydro-Québec winter peaks."""

from __future__ import annotations

import datetime
import logging
import zoneinfo
from typing import Any

from .models import AnchorPeriod, PeakEvent

_LOGGER = logging.getLogger(__name__)

# Rate mapping from HQ codes to internal codes
RATE_CODE_MAPPING = {
    "CPC-D": "DCPC",  # Rate D + Winter Credits
    "TPC-DPC": "DPC",  # Flex-D (dynamic pricing)
    "GDP-Affaires": "M-GDP",  # Commercial GDP
    "CPC-G": "M-CPC",  # Commercial CPC
    "TPC-GPC": "M-GPC",  # Commercial GPC
    "ENG01": "M-ENG",  # Commercial ENG01
    "OEA": "M-OEA",  # Commercial OEA
}


class PeakHandler:
    """Handles peak event logic and calculations."""

    def __init__(self, rate_code: str, preheat_duration: int = 120) -> None:
        """Initialize peak handler.

        Args:
            rate_code: Rate code (DCPC, DPC, etc.)
            preheat_duration: Pre-heat duration in minutes (default 120)
        """
        self.rate_code = rate_code
        self.preheat_duration = preheat_duration
        self._events: list[PeakEvent] = []

    def load_events(self, events: list[dict[str, Any]]) -> None:
        """Load peak events from API and generate schedule if needed.

        For DCPC (Winter Credits):
        - Generates daily schedule (today + tomorrow)
        - Marks API events as critical (force_critical=True)
        - Marks generated schedule as non-critical (force_critical=False)
        - If API event matches generated peak (same date+timeslot), uses API version

        For DPC and other rates:
        - Only uses API events (all marked as critical)
        """
        # Create API events with force_critical=True (all API announcements are critical)
        api_events = [
            PeakEvent(event, self.preheat_duration, force_critical=True) for event in events
        ]

        if self.rate_code == "DCPC":
            # Generate schedule for DCPC
            generated_peaks = self._generate_dcpc_schedule()

            # Merge: if API event matches generated peak (same date+time slot), keep API version
            merged_events: list[PeakEvent] = []
            api_dates_slots = {(e.start_date.date(), e.time_slot) for e in api_events}

            # Add all API events (critical)
            merged_events.extend(api_events)

            # Add generated peaks that don't have matching API event
            for gen_peak in generated_peaks:
                key = (gen_peak.start_date.date(), gen_peak.time_slot)
                if key not in api_dates_slots:
                    merged_events.append(gen_peak)

            # Sort by start date
            self._events = sorted(merged_events, key=lambda e: e.start_date)

            # Log critical peak date range for debugging
            critical_peaks = [e for e in self._events if e.is_critical]
            if critical_peaks:
                first_critical = min(critical_peaks, key=lambda e: e.start_date)
                last_critical = max(critical_peaks, key=lambda e: e.start_date)
                _LOGGER.debug(
                    "[OpenData] DCPC critical peaks: first=%s, last=%s",
                    first_critical.start_date.strftime("%Y-%m-%d %H:%M"),
                    last_critical.start_date.strftime("%Y-%m-%d %H:%M"),
                )

            _LOGGER.debug(
                "[OpenData] DCPC schedule: %d API events (critical) + %d generated (non-critical) = %d total",
                len(api_events),
                len(generated_peaks)
                - len(
                    [
                        p
                        for p in generated_peaks
                        if (p.start_date.date(), p.time_slot) in api_dates_slots
                    ]
                ),
                len(self._events),
            )
        else:
            # For DPC and other rates, only use API events
            self._events = api_events

            # Log critical peak date range for debugging
            if self._events:
                first_peak = min(self._events, key=lambda e: e.start_date)
                last_peak = max(self._events, key=lambda e: e.start_date)
                _LOGGER.debug(
                    "[OpenData] %s peaks: first=%s, last=%s, total=%d (all critical)",
                    self.rate_code,
                    first_peak.start_date.strftime("%Y-%m-%d %H:%M"),
                    last_peak.start_date.strftime("%Y-%m-%d %H:%M"),
                    len(self._events),
                )
            else:
                _LOGGER.debug(
                    "[OpenData] Loaded %d API peak events for rate %s (all critical)",
                    len(self._events),
                    self.rate_code,
                )

    def _generate_dcpc_schedule(self) -> list[PeakEvent]:
        """Generate DCPC (Winter Credits) peak schedule for today and tomorrow.

        Winter Credits has a fixed schedule during winter season (Dec 1 - Mar 31):
        - Morning Peak: 6:00-10:00 (4 hours)
        - Evening Peak: 16:00-20:00 (4 hours)

        Returns empty list if outside winter season.
        Returns list of PeakEvent objects with force_critical=False.
        """
        tz = zoneinfo.ZoneInfo("America/Toronto")
        now = datetime.datetime.now(tz)

        # Check if we're in winter season (Dec 1 - Mar 31)
        today = now.date()
        winter_start = datetime.date(today.year, 12, 1)
        winter_end = datetime.date(today.year + 1, 3, 31)

        # Handle year boundary - if today is before March 31, check previous year's Dec 1
        if today.month < 12:
            winter_start = datetime.date(today.year - 1, 12, 1)
            winter_end = datetime.date(today.year, 3, 31)

        if not (winter_start <= today <= winter_end):
            _LOGGER.debug(
                "[OpenData] Outside winter season (%s to %s), no DCPC schedule generated",
                winter_start,
                winter_end,
            )
            return []

        # Generate non-critical peaks for today and tomorrow only
        # Critical peaks beyond tomorrow come from API announcements
        generated_peaks: list[PeakEvent] = []

        for day_offset in [0, 1]:  # 0=today, 1=tomorrow
            target_date = today + datetime.timedelta(days=day_offset)

            # Morning peak: 6:00-10:00
            morning_start = datetime.datetime.combine(target_date, datetime.time(6, 0), tzinfo=tz)
            morning_end = datetime.datetime.combine(target_date, datetime.time(10, 0), tzinfo=tz)

            morning_data = {
                "offre": "CPC-D",
                "datedebut": morning_start.isoformat(),
                "datefin": morning_end.isoformat(),
                "plagehoraire": "AM",
                "duree": "PT04H00MS",
                "secteurclient": "Résidentiel",
            }
            generated_peaks.append(
                PeakEvent(morning_data, self.preheat_duration, force_critical=False)
            )

            # Evening peak: 16:00-20:00
            evening_start = datetime.datetime.combine(target_date, datetime.time(16, 0), tzinfo=tz)
            evening_end = datetime.datetime.combine(target_date, datetime.time(20, 0), tzinfo=tz)

            evening_data = {
                "offre": "CPC-D",
                "datedebut": evening_start.isoformat(),
                "datefin": evening_end.isoformat(),
                "plagehoraire": "PM",
                "duree": "PT04H00MS",
                "secteurclient": "Résidentiel",
            }
            generated_peaks.append(
                PeakEvent(evening_data, self.preheat_duration, force_critical=False)
            )

        _LOGGER.debug(
            "[OpenData] Generated %d DCPC schedule peaks for today and tomorrow",
            len(generated_peaks),
        )
        return generated_peaks

    def _get_hq_offers_for_rate(self) -> list[str]:
        """Get Hydro-Québec offer codes for current rate."""
        # Map internal rate code to HQ offer codes
        hq_offers = [
            hq_code
            for hq_code, internal_code in RATE_CODE_MAPPING.items()
            if internal_code == self.rate_code
        ]
        if hq_offers:
            _LOGGER.debug("Mapped rate '%s' to HQ offers: %s", self.rate_code, hq_offers)
            return hq_offers

        # Rates without peak programs (e.g., plain "D", "DT", "M" without options) have no peak data
        _LOGGER.info(
            "Rate '%s' does not have peak events in public API (no winter credit or dynamic pricing)",
            self.rate_code,
        )
        return []

    @property
    def next_peak(self) -> PeakEvent | None:
        """Get next upcoming peak event."""

        tz = zoneinfo.ZoneInfo("America/Toronto")
        now = datetime.datetime.now(tz)
        # Filter upcoming events - all event dates are already timezone-aware
        upcoming = [e for e in self._events if e.end_date > now]
        return min(upcoming, key=lambda e: e.start_date, default=None) if upcoming else None

    @property
    def next_critical_peak(self) -> PeakEvent | None:
        """Get next critical peak event."""

        tz = zoneinfo.ZoneInfo("America/Toronto")
        now = datetime.datetime.now(tz)
        # Filter upcoming critical events - all event dates are already timezone-aware
        upcoming = [e for e in self._events if e.end_date > now and e.is_critical]
        return min(upcoming, key=lambda e: e.start_date, default=None) if upcoming else None

    @property
    def current_peak(self) -> PeakEvent | None:
        """Get current active peak if any."""

        tz = zoneinfo.ZoneInfo("America/Toronto")
        now = datetime.datetime.now(tz)
        # Check if we're within any event's time window - all event dates are timezone-aware
        for event in self._events:
            if event.start_date <= now <= event.end_date:
                return event
        return None

    @property
    def current_state(self) -> str:
        """Get current state description.

        Returns hydroqc2mqtt-compatible values:
        - "off_season": No events loaded
        - "critical_peak": During a critical peak
        - "peak": During a non-critical peak
        - "critical_anchor": During an anchor period before a critical peak (DCPC only)
        - "anchor": During an anchor period before a non-critical peak (DCPC only)
        - "normal": Regular period (no peak/anchor/preheat active)
        """
        tz = zoneinfo.ZoneInfo("America/Toronto")
        now = datetime.datetime.now(tz)

        # If we're not in the dec 1st. to mar 31st. period, we're off-season
        if not ((now.month, now.day) >= (12, 1) or (now.month, now.day) <= (3, 31)):
            return "off_season"

        # Check if currently in a peak
        current = self.current_peak
        if current:
            return "critical_peak" if current.is_critical else "peak"

        # Check if currently in an anchor period (DCPC only)
        if self.rate_code == "DCPC":
            for event in self._events:
                if hasattr(event, "anchor") and event.anchor:
                    anchor = event.anchor
                    if anchor.start_date <= now < anchor.end_date:
                        return "critical_anchor" if anchor.is_critical else "anchor"

        # In season but no events, state is normal
        return "normal"

    @property
    def current_peak_is_critical(self) -> bool:
        """Check if current peak is critical."""
        current = self.current_peak
        return current.is_critical if current else False

    @property
    def preheat_in_progress(self) -> bool:
        """Check if pre-heat is in progress."""

        tz = zoneinfo.ZoneInfo("America/Toronto")
        now = datetime.datetime.now(tz)
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

    def _get_peak_for_period(self, period_start: datetime.datetime) -> PeakEvent | None:
        """Get peak event for a specific period."""

        # Ensure period_start is timezone-aware in America/Toronto
        if period_start.tzinfo is None:
            tz = zoneinfo.ZoneInfo("America/Toronto")
            period_start = period_start.replace(tzinfo=tz)
        elif period_start.tzinfo != zoneinfo.ZoneInfo("America/Toronto"):
            # Convert to America/Toronto if it's a different timezone
            period_start = period_start.astimezone(zoneinfo.ZoneInfo("America/Toronto"))

        for event in self._events:
            if event.start_date <= period_start < event.end_date:
                return event
        return None

    @property
    def today_morning_peak(self) -> PeakEvent | None:
        """Get today's morning peak (6AM-12PM)."""

        tz = zoneinfo.ZoneInfo("America/Toronto")
        now = datetime.datetime.now(tz)
        morning_start = now.replace(hour=6, minute=0, second=0, microsecond=0)
        return self._get_peak_for_period(morning_start)

    @property
    def today_evening_peak(self) -> PeakEvent | None:
        """Get today's evening peak (4PM-8PM)."""

        tz = zoneinfo.ZoneInfo("America/Toronto")
        now = datetime.datetime.now(tz)
        evening_start = now.replace(hour=16, minute=0, second=0, microsecond=0)
        return self._get_peak_for_period(evening_start)

    @property
    def tomorrow_morning_peak(self) -> PeakEvent | None:
        """Get tomorrow's morning peak (6AM-12PM)."""

        tz = zoneinfo.ZoneInfo("America/Toronto")
        now = datetime.datetime.now(tz)
        tomorrow = now + datetime.timedelta(days=1)
        morning_start = tomorrow.replace(hour=6, minute=0, second=0, microsecond=0)
        return self._get_peak_for_period(morning_start)

    @property
    def tomorrow_evening_peak(self) -> PeakEvent | None:
        """Get tomorrow's evening peak (4PM-8PM)."""

        tz = zoneinfo.ZoneInfo("America/Toronto")
        now = datetime.datetime.now(tz)
        tomorrow = now + datetime.timedelta(days=1)
        evening_start = tomorrow.replace(hour=16, minute=0, second=0, microsecond=0)
        return self._get_peak_for_period(evening_start)

    @property
    def next_anchor(self) -> AnchorPeriod | None:
        """Get next anchor period (for Winter Credits)."""
        # For Winter Credits, anchor is the notification period before peak
        next_event = self.next_peak
        if not next_event:
            return None

        return next_event.anchor
