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

    def __init__(self, data: dict[str, Any], preheat_duration: int = 120) -> None:
        """Initialize peak event from API data."""

        self.offer = data["offre"]
        # Parse dates and make them timezone-aware (America/Toronto = EST/EDT)
        tz = zoneinfo.ZoneInfo("America/Toronto")

        # API uses lowercase field names: datedebut, datefin, plagehoraire, secteurclient
        start_str = data.get("datedebut") or data.get("dateDebut")
        end_str = data.get("datefin") or data.get("dateFin")

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
        """Determine if this is a critical peak based on offer type."""
        # TPC (Tarif de pointe critique) = Critical peak
        return self.offer.startswith("TPC") or self.offer.startswith("ENG")

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
        """Load peak events from API data.

        Note: Events are already filtered by rate at the API level,
        so no additional filtering is needed here.
        """
        self._events = [PeakEvent(event, self.preheat_duration) for event in events]
        _LOGGER.debug(
            "Loaded %d peak events for rate %s",
            len(self._events),
            self.rate_code,
        )

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
        """Get current state description."""
        # If no events, we're outside the season
        if not self._events:
            return "Off Season (Dec 1 - Mar 31)"

        tz = zoneinfo.ZoneInfo("America/Toronto")
        now = datetime.datetime.now(tz)
        current = self.current_peak

        if current:
            state_type = "Critical Peak" if current.is_critical else "Peak"
            return f"{state_type} in progress"

        # Check if in preheat
        next_event = self.next_peak
        if next_event:
            preheat_start = next_event.start_date - datetime.timedelta(
                minutes=self.preheat_duration
            )
            if preheat_start <= now < next_event.start_date:
                return "Pre-heat in progress"

        return "Regular period"

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
            params = {
                "limit": 100,
                "timezone": "America/Toronto",
                "refine": f'offre:"{hq_offers[0]}"',
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
