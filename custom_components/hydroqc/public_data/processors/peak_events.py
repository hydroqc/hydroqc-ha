"""Peak events processor for evenements-pointe dataset (residential only)."""

from __future__ import annotations

import datetime
import logging
import zoneinfo
from typing import Any

from ..peak_handler import PeakHandler
from .base import DatasetProcessor

_LOGGER = logging.getLogger(__name__)


class PeakEventsProcessor(DatasetProcessor):
    """Processor for winter peak events dataset (residential customers only).
    
    Fetches critical peak announcements from Hydro-Québec's open data API
    and filters for residential sector only. Commercial events are ignored.
    """

    def __init__(self, peak_handler: PeakHandler) -> None:
        """Initialize peak events processor.
        
        Args:
            peak_handler: PeakHandler instance to load events into
        """
        self.peak_handler = peak_handler

    def get_dataset_name(self) -> str:
        """Get the dataset name for peak events."""
        return "evenements-pointe"

    def build_fetch_params(self) -> dict[str, Any]:
        """Build query parameters for fetching peak events.
        
        Returns residential-only peak events from today onwards.
        """
        # Get HQ offer codes for current rate
        hq_offers = self.peak_handler._get_hq_offers_for_rate()
        if not hq_offers:
            _LOGGER.debug(
                "[OpenData] No peak events available for rate %s, skipping fetch",
                self.peak_handler.rate_code,
            )
            return {}

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
                "[OpenData] Multiple offers detected for rate %s, only filtering by first: %s",
                self.peak_handler.rate_code,
                hq_offers[0],
            )

        _LOGGER.debug(
            "[OpenData] Fetching peak events for rate %s with refine: offre=%s",
            self.peak_handler.rate_code,
            hq_offers[0],
        )

        return params

    async def process_response(self, data: dict[str, Any]) -> None:
        """Process peak events API response and load into peak handler.
        
        Filters for residential sector only - commercial events are ignored.
        
        Args:
            data: Raw JSON response from the OpenData API
        """
        results = data.get("results", [])
        _LOGGER.debug(
            "[OpenData] Received %d results from API for rate %s",
            len(results),
            self.peak_handler.rate_code,
        )

        # Field names are lowercase in the API
        events = []
        for record in results:
            sector = record.get("secteurclient", "")
            
            # Filter for residential sector only
            if sector != "Résidentiel":
                _LOGGER.debug(
                    "[OpenData] Ignoring non-residential event: sector=%s, offer=%s",
                    sector,
                    record.get("offre", ""),
                )
                continue
            
            events.append({
                "offre": record.get("offre", ""),
                "dateDebut": record.get("datedebut", ""),
                "dateFin": record.get("datefin", ""),
                "plageHoraire": record.get("plagehoraire", ""),
                "duree": record.get("duree", ""),
                "secteurClient": sector,
            })

        _LOGGER.info(
            "[OpenData] Filtered %d residential peak events (ignored %d non-residential)",
            len(events),
            len(results) - len(events),
        )

        # Load events into peak handler
        self.peak_handler.load_events(events)
