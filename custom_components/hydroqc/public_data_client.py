"""Public data client for Hydro-Québec winter peaks (open data API)."""

from __future__ import annotations

import datetime
import logging
import zoneinfo
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

# Hydro-Québec open data API endpoint (Opendatasoft v2.1)
WINTER_PEAKS_API_BASE = "https://donnees.hydroquebec.com/api/explore/v2.1"
WINTER_PEAKS_DATASET = "evenements-pointe"
WINTER_PEAKS_URL = f"{WINTER_PEAKS_API_BASE}/catalog/datasets/{WINTER_PEAKS_DATASET}/records"

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


class PreHeatPeriod:
    """Represents a pre-heat period before a peak."""

    def __init__(self, peak_start: datetime.datetime, duration_minutes: int) -> None:
        """Initialize pre-heat period."""
        self.start_date = peak_start - datetime.timedelta(minutes=duration_minutes)
        self.end_date = peak_start


class AnchorPeriod:
    """Represents an anchor period (notification) before a peak."""

    def __init__(self, peak_start: datetime.datetime, is_morning: bool, is_critical: bool) -> None:
        """Initialize anchor period.

        Morning peaks (6:00-10:00): Anchor starts 5 hours before, lasts 3 hours
        Evening peaks (16:00-20:00): Anchor starts 4 hours before, lasts 2 hours
        """
        if is_morning:
            # Morning: 5 hours before peak, duration 3 hours
            anchor_start_offset = 5
            anchor_duration = 3
        else:
            # Evening: 4 hours before peak, duration 2 hours
            anchor_start_offset = 4
            anchor_duration = 2

        self.start_date = peak_start - datetime.timedelta(hours=anchor_start_offset)
        self.end_date = self.start_date + datetime.timedelta(hours=anchor_duration)
        self.is_critical = is_critical


class PeakEvent:
    """Represents a winter peak event."""

    def __init__(
        self,
        data: dict[str, Any],
        preheat_duration: int = 120,
        force_critical: bool | None = None,
    ) -> None:
        """Initialize peak event from API data.

        Args:
            data: Peak event data from API
            preheat_duration: Pre-heat duration in minutes
            force_critical: Explicitly set critical status (True=critical from API,
                          False=generated non-critical, None=auto-detect from offer)
        """
        self.offer = data["offre"]
        self._force_critical = force_critical
        # Parse dates and make them timezone-aware (America/Toronto = EST/EDT)
        tz = zoneinfo.ZoneInfo("America/Toronto")

        # API uses lowercase field names: datedebut, datefin, plagehoraire, secteurclient
        start_str = data.get("datedebut") or data.get("dateDebut")
        end_str = data.get("datefin") or data.get("dateFin")

        if not start_str or not end_str:
            raise ValueError(f"Missing date fields in data: {data}")

        # Handle both date formats:
        # - Simple: "YYYY-MM-DD HH:MM" (most common from API)
        # - ISO: "YYYY-MM-DDTHH:MM:SS-05:00" or similar
        try:
            # Try ISO format first
            start_dt = datetime.datetime.fromisoformat(start_str)
            end_dt = datetime.datetime.fromisoformat(end_str)
            # Ensure timezone-aware - if naive, add America/Toronto
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=tz)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=tz)
            self.start_date = start_dt
            self.end_date = end_dt
        except (ValueError, TypeError) as err:
            # Fall back to simple format
            try:
                self.start_date = datetime.datetime.strptime(start_str, "%Y-%m-%d %H:%M").replace(
                    tzinfo=tz
                )
                self.end_date = datetime.datetime.strptime(end_str, "%Y-%m-%d %H:%M").replace(
                    tzinfo=tz
                )
            except (ValueError, TypeError) as err2:
                _LOGGER.error(
                    "Failed to parse dates: start=%r end=%r (ISO error: %s, Simple error: %s)",
                    start_str,
                    end_str,
                    err,
                    err2,
                )
                raise

        self.time_slot = data.get("plagehoraire") or data.get("plageHoraire")  # AM or PM
        self.duration = data.get("duree")
        self.sector = data.get("secteurclient") or data.get(
            "secteurClient"
        )  # Résidentiel or Affaires
        self._preheat_duration = preheat_duration

    @property
    def is_critical(self) -> bool:
        """Determine if this is a critical peak.

        Returns True if:
        - force_critical=True (event from OpenData API announcement)
        - force_critical=None and offer starts with TPC/ENG (backward compatibility)

        Returns False if:
        - force_critical=False (generated non-critical schedule peak)
        - force_critical=None and offer doesn't start with TPC/ENG
        """
        if self._force_critical is not None:
            return self._force_critical
        # Fallback for backward compatibility (should not be used with new code)
        return bool(self.offer.startswith("TPC") or self.offer.startswith("ENG"))

    @property
    def preheat(self) -> PreHeatPeriod:
        """Get pre-heat period for this peak."""
        return PreHeatPeriod(self.start_date, self._preheat_duration)

    @property
    def anchor(self) -> AnchorPeriod:
        """Get anchor period for this peak (Winter Credits)."""
        # Determine if this is a morning peak (6:00-10:00) or evening peak (16:00-20:00)
        is_morning = self.time_slot == "AM"
        return AnchorPeriod(self.start_date, is_morning, self.is_critical)

    @property
    def is_residential(self) -> bool:
        """Check if this peak is for residential sector."""
        return self.sector == "Résidentiel"

    @property
    def is_commercial(self) -> bool:
        """Check if this peak is for commercial sector."""
        return self.sector == "Affaires"


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
        # If no events, we're off season
        if not self._events:
            return "off_season"

        tz = zoneinfo.ZoneInfo("America/Toronto")
        now = datetime.datetime.now(tz)

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


class PublicDataClient:
    """Client for Hydro-Québec public open data API."""

    def __init__(self, rate_code: str, preheat_duration: int = 120) -> None:
        """Initialize public data client.

        Args:
            rate_code: Rate code (DCPC, DPC, M-GDP, etc.)
            preheat_duration: Pre-heat duration in minutes (default 120)
        """
        self.rate_code = rate_code
        self.peak_handler = PeakHandler(rate_code, preheat_duration)
        self._session: aiohttp.ClientSession | None = None
        self._last_fetch: datetime.datetime | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def fetch_peak_data(self) -> None:
        """Fetch winter peak data from public API."""
        try:
            session = await self._get_session()

            # Get HQ offer codes for current rate
            hq_offers = self.peak_handler._get_hq_offers_for_rate()
            if not hq_offers:
                _LOGGER.debug(
                    "[OpenData] No peak events available for rate %s, skipping API fetch",
                    self.rate_code,
                )
                return

            # Build refine filter to filter by rate (Opendatasoft API syntax)
            # Use refine parameter: refine=offre:"TPC-DPC"
            # Filter for events from today onwards (next 7 days)
            tz = zoneinfo.ZoneInfo("America/Toronto")
            today = datetime.datetime.now(tz).date()
            today_str = today.isoformat()

            params: dict[str, str | int] = {
                "limit": 100,
                "timezone": "America/Toronto",
                "refine": f'offre:"{hq_offers[0]}"',
                "where": f"datedebut>='{today_str}'",
            }

            if len(hq_offers) > 1:
                _LOGGER.warning(
                    "Multiple offers detected for rate %s, only filtering by first: %s",
                    self.rate_code,
                    hq_offers[0],
                )

            _LOGGER.debug(
                "[OpenData] Fetching peak events for rate %s with refine: offre=%s",
                self.rate_code,
                hq_offers[0],
            )

            async with session.get(
                WINTER_PEAKS_URL, params=params, timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                response.raise_for_status()
                data = await response.json()

                # Extract records from Opendatasoft API response
                results = data.get("results", [])
                _LOGGER.debug(
                    "[OpenData] Received %d results from API for rate %s",
                    len(results),
                    self.rate_code,
                )

                # Field names are lowercase in the API, map to our expected camelCase format
                events = [
                    {
                        "offre": record.get("offre", ""),
                        "dateDebut": record.get("datedebut", ""),
                        "dateFin": record.get("datefin", ""),
                        "plageHoraire": record.get("plagehoraire", ""),
                        "duree": record.get("duree", ""),
                        "secteurClient": record.get("secteurclient", ""),
                    }
                    for record in results
                ]

                # Load events into peak handler (no filtering needed, already filtered by API)
                self.peak_handler.load_events(events)

                self._last_fetch = datetime.datetime.now(datetime.UTC)
                _LOGGER.info(
                    "[OpenData] Successfully fetched %d peak events from public API for rate %s",
                    len(events),
                    self.rate_code,
                )

        except aiohttp.ClientError as err:
            _LOGGER.warning("[OpenData] Failed to fetch peak data from public API: %s", err)
        except Exception:
            _LOGGER.exception("[OpenData] Unexpected error fetching peak data")

    async def close_session(self) -> None:
        """Close aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    def set_preheat_duration(self, duration: int) -> None:
        """Set pre-heat duration in minutes."""
        self.peak_handler.preheat_duration = duration
