"""Helper functions for Hydro-Québec config flow."""

from __future__ import annotations

import logging

import aiohttp

_LOGGER = logging.getLogger(__name__)

# Hydro-Québec open data API endpoint (Opendatasoft v2.1)
WINTER_PEAKS_API_BASE = "https://donnees.hydroquebec.com/api/explore/v2.1"
WINTER_PEAKS_DATASET = "evenements-pointe"
WINTER_PEAKS_URL = f"{WINTER_PEAKS_API_BASE}/catalog/datasets/{WINTER_PEAKS_DATASET}/records"

# Sector mapping
SECTOR_MAPPING = {
    "Residentiel": "Residential",
    "Affaires": "Commercial",
}

# Rate mapping from HQ codes to display names
RATE_CODE_MAPPING = {
    "CPC-D": ("D", "CPC", "Rate D + Winter Credits (CPC)"),
    "TPC-DPC": ("DPC", "", "Flex-D (Dynamic Pricing)"),
    "GDP-Affaires": ("M", "GDP", "Commercial Rate M + GDP"),
    "CPC-G": ("M", "CPC", "Commercial Rate M + Winter Credits (CPC)"),
    "TPC-GPC": ("M", "GPC", "Commercial Rate M + GPC"),
    "ENG01": ("M", "ENG", "Commercial Rate M + ENG01"),
    "OEA": ("M", "OEA", "Commercial Rate M + OEA"),
}


async def fetch_available_sectors() -> list[str]:
    """Fetch available sectors from Hydro-Québec open data API."""
    try:
        async with aiohttp.ClientSession() as session:
            params: dict[str, str | int] = {
                "select": "secteurclient",
                "limit": 100,
                "timezone": "America/Toronto",
            }
            async with session.get(
                WINTER_PEAKS_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                response.raise_for_status()
                data = await response.json()

                # Extract unique sectors from results
                results = data.get("results", [])
                sectors = {
                    record.get("secteurclient") for record in results if record.get("secteurclient")
                }

                return sorted(sectors)

    except Exception as err:
        _LOGGER.warning("Failed to fetch sectors from API: %s", err)
        return ["Residentiel", "Affaires"]


async def fetch_offers_for_sector(sector: str) -> list[dict[str, str]]:
    """Fetch available offers for a specific sector from Hydro-Québec open data API."""
    try:
        async with aiohttp.ClientSession() as session:
            params: dict[str, str | int] = {
                "select": "offre",
                "refine": f'secteurclient:"{sector}"',
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
        _LOGGER.warning("Failed to fetch offers for sector %s from API: %s", sector, err)
        # Return default fallback based on sector
        if sector == "Residentiel":
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
        return [
            {
                "value": "M|GDP",
                "label": "Commercial Rate M + GDP",
                "rate": "M",
                "rate_option": "GDP",
            },
            {
                "value": "M|CPC",
                "label": "Commercial Rate M + Winter Credits (CPC)",
                "rate": "M",
                "rate_option": "CPC",
            },
        ]
