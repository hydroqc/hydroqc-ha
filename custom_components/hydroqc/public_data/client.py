"""Client for Hydro-Québec public open data API."""

from __future__ import annotations

import datetime
import logging
import zoneinfo

import aiohttp

from .peak_handler import PeakHandler

_LOGGER = logging.getLogger(__name__)

# Hydro-Québec open data API endpoint (Opendatasoft v2.1)
WINTER_PEAKS_API_BASE = "https://donnees.hydroquebec.com/api/explore/v2.1"
WINTER_PEAKS_DATASET = "evenements-pointe"
WINTER_PEAKS_URL = f"{WINTER_PEAKS_API_BASE}/catalog/datasets/{WINTER_PEAKS_DATASET}/records"


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
