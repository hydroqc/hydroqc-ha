"""Client for Hydro-Québec public open data API (residential rates only)."""

from __future__ import annotations

import datetime
import logging

from .opendata_client import OpenDataClient
from .peak_handler import PeakHandler
from .processors import PeakEventsProcessor
from .processors.base import DatasetProcessor

_LOGGER = logging.getLogger(__name__)


class PublicDataClient:
    """Client for Hydro-Québec public open data API (residential rates only).

    This client uses a processor pattern to handle different datasets.
    By default, it uses PeakEventsProcessor for winter peak events.
    """

    def __init__(
        self,
        rate_code: str,
        preheat_duration: int = 120,
        processor: DatasetProcessor | None = None,
    ) -> None:
        """Initialize public data client.

        Args:
            rate_code: Residential rate code (DCPC, DPC only)
            preheat_duration: Pre-heat duration in minutes (default 120)
            processor: Optional dataset processor (defaults to PeakEventsProcessor)
        """
        self.rate_code = rate_code
        self.peak_handler = PeakHandler(rate_code, preheat_duration)
        self._opendata_client = OpenDataClient()
        self._last_fetch: datetime.datetime | None = None

        # Use provided processor or default to peak events
        self._processor = processor or PeakEventsProcessor(self.peak_handler)

    async def fetch_peak_data(self) -> None:
        """Fetch winter peak data from public API using processor pattern."""
        try:
            # Build fetch parameters using processor
            params = self._processor.build_fetch_params()
            if not params:
                _LOGGER.debug(
                    "[OpenData] No params returned by processor, skipping fetch for rate %s",
                    self.rate_code,
                )
                return

            # Fetch data from OpenData API
            dataset_name = self._processor.get_dataset_name()
            data = await self._opendata_client.fetch_dataset(dataset_name, params)

            # Process the response using processor
            await self._processor.process_response(data)

            self._last_fetch = datetime.datetime.now(datetime.UTC)
            _LOGGER.info(
                "[OpenData] Successfully fetched data from dataset '%s' for rate %s",
                dataset_name,
                self.rate_code,
            )

        except Exception as err:
            _LOGGER.warning(
                "[OpenData] Failed to fetch data for rate %s: %s",
                self.rate_code,
                err,
            )

    async def close_session(self) -> None:
        """Close aiohttp session."""
        await self._opendata_client.close_session()

    def set_preheat_duration(self, duration: int) -> None:
        """Set pre-heat duration in minutes."""
        self.peak_handler.preheat_duration = duration
