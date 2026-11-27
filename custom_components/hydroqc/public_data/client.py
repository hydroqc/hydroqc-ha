"""Client for Hydro-Québec public open data API."""

from __future__ import annotations

import datetime
import logging
import zoneinfo

import aiohttp

from .normalize import extract_records, normalize_event
from .offers import is_known_offer, normalize_offer
from .peak_handler import PeakHandler

_LOGGER = logging.getLogger(__name__)

# Hydro-Québec open data API endpoint (Opendatasoft v2.1)
WINTER_PEAKS_API_BASE = "https://donnees.hydroquebec.com/api/explore/v2.1"
WINTER_PEAKS_DATASET = "evenements-pointe"
WINTER_PEAKS_URL = f"{WINTER_PEAKS_API_BASE}/catalog/datasets/{WINTER_PEAKS_DATASET}/records"

# Date field of the dataset, used in the server-side date filter.
WINTER_PEAKS_DATE_FIELD = "datedebut"

# Records requested per fetch. Hydro-Québec publishes a few dozen events per
# season across every offer, so a full page covers every announced peak.
WINTER_PEAKS_FETCH_LIMIT = 100


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
        self._warned_unknown_offers = False

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

            # Filter for events from today onwards. Offers are matched locally
            # after normalization: Hydro-Québec renamed the offer values on its
            # feeds, so a server-side filter on the raw value would miss events.
            tz = zoneinfo.ZoneInfo("America/Toronto")
            today = datetime.datetime.now(tz).date()
            today_str = today.isoformat()

            params: dict[str, str | int] = {
                "limit": WINTER_PEAKS_FETCH_LIMIT,
                "timezone": "America/Toronto",
                "where": f"{WINTER_PEAKS_DATE_FIELD}>='{today_str}'",
                "order_by": f"{WINTER_PEAKS_DATE_FIELD} asc",
            }

            _LOGGER.debug(
                "[OpenData] Fetching peak events for rate %s (offers: %s)",
                self.rate_code,
                ", ".join(hq_offers),
            )

            async with session.get(
                WINTER_PEAKS_URL, params=params, timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                response.raise_for_status()
                data = await response.json()

                records = extract_records(data)
                _LOGGER.debug(
                    "[OpenData] Received %d records from API for rate %s",
                    len(records),
                    self.rate_code,
                )

                if len(records) >= WINTER_PEAKS_FETCH_LIMIT:
                    _LOGGER.warning(
                        "[OpenData] API returned %d records, the page limit; some peak events may be missing",
                        len(records),
                    )

                wanted = set(hq_offers)
                events: list[dict[str, str]] = []
                unknown_offers: set[str] = set()

                for record in records:
                    event = normalize_event(record)
                    if event is None:
                        _LOGGER.debug("[OpenData] Skipping record without dates: %s", record)
                        continue

                    offer_code = normalize_offer(event["offre"])
                    if offer_code in wanted:
                        event["offre"] = offer_code
                        events.append(event)
                    elif not is_known_offer(event["offre"]):
                        unknown_offers.add(event["offre"])

                if unknown_offers and not self._warned_unknown_offers:
                    self._warned_unknown_offers = True
                    _LOGGER.warning(
                        "[OpenData] Public feed returned unknown offer value(s) %s; "
                        "add them to public_data/offers.py if Hydro-Québec renamed an offer",
                        sorted(unknown_offers),
                    )

                # Load events into peak handler (already filtered by offer)
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
