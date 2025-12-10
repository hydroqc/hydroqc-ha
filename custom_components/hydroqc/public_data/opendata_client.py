"""Base client for Hydro-Québec Open Data API (Opendatasoft v2.1)."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

# Hydro-Québec open data API base URL (Opendatasoft v2.1)
OPENDATA_API_BASE = "https://donnees.hydroquebec.com/api/explore/v2.1"


class OpenDataClient:
    """Base client for accessing Hydro-Québec Open Data API.

    This client provides generic access to any dataset on the Opendatasoft v2.1 API.
    Dataset-specific logic is handled by processor classes.
    """

    def __init__(self) -> None:
        """Initialize OpenData client."""
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close_session(self) -> None:
        """Close aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    def build_dataset_url(self, dataset_name: str) -> str:
        """Build dataset URL for a given dataset name.

        Args:
            dataset_name: Name of the dataset (e.g., "evenements-pointe", "demande-electricite-quebec")

        Returns:
            Full URL to the dataset records endpoint
        """
        return f"{OPENDATA_API_BASE}/catalog/datasets/{dataset_name}/records"

    async def fetch_dataset(
        self, dataset_name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Fetch data from a specific dataset.

        Args:
            dataset_name: Name of the dataset to fetch from
            params: Query parameters for the API request

        Returns:
            JSON response from the API

        Raises:
            aiohttp.ClientError: If the HTTP request fails
        """
        session = await self._get_session()
        url = self.build_dataset_url(dataset_name)

        _LOGGER.debug(
            "[OpenData] Fetching from dataset '%s' with params: %s", dataset_name, params
        )

        async with session.get(
            url, params=params, timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            response.raise_for_status()
            data: dict[str, Any] = await response.json()

            results_count = len(data.get("results", []))
            _LOGGER.debug(
                "[OpenData] Received %d results from dataset '%s'",
                results_count,
                dataset_name,
            )

            return data
