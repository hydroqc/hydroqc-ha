"""Helper functions for Hydro-Québec config flow."""

from __future__ import annotations

import logging

import aiohttp

_LOGGER = logging.getLogger(__name__)

# Hydro-Québec open data API endpoint (Opendatasoft v2.1)
WINTER_PEAKS_API_BASE = "https://donnees.hydroquebec.com/api/explore/v2.1"
WINTER_PEAKS_DATASET = "evenements-pointe"
WINTER_PEAKS_URL = f"{WINTER_PEAKS_API_BASE}/catalog/datasets/{WINTER_PEAKS_DATASET}/records"

# Rate mapping from HQ codes to display names (residential only)
RATE_CODE_MAPPING = {
    "CPC-D": ("D", "CPC", "Rate D + Winter Credits (CPC)"),
    "TPC-DPC": ("DPC", "", "Flex-D (Dynamic Pricing)"),
}


async def fetch_offers_for_residential() -> list[dict[str, str]]:
    """Fetch available residential rate offers from Hydro-Québec open data API."""
    try:
        async with aiohttp.ClientSession() as session:
            params: dict[str, str | int] = {
                "select": "offre",
                "refine": 'secteurclient:"Residentiel"',
                "limit": 100,
                "timezone": "America/Toronto",
            }
            async with session.get(
                WINTER_PEAKS_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                response.raise_for_status()
                data = await response.json()

                # Extract unique offers from results
                results = data.get("results", [])
                offers = {record.get("offre") for record in results if record.get("offre")}

                rate_options = []
                for offer in offers:
                    if offer in RATE_CODE_MAPPING:
                        rate, rate_option, label = RATE_CODE_MAPPING[offer]
                        rate_options.append(
                            {
                                "value": f"{rate}|{rate_option}",
                                "label": label,
                                "rate": rate,
                                "rate_option": rate_option,
                            }
                        )

                # Sort by label
                rate_options.sort(key=lambda x: x["label"])

                return rate_options

    except Exception as err:
        _LOGGER.warning("Failed to fetch residential offers from API: %s", err)
        # Return default residential rates fallback
        return [
            {
                "value": "D|CPC",
                "label": "Rate D + Winter Credits (CPC)",
                "rate": "D",
                "rate_option": "CPC",
            },
            {
                "value": "DPC|",
                "label": "Flex-D (Dynamic Pricing)",
                "rate": "DPC",
                "rate_option": "",
            },
        ]
