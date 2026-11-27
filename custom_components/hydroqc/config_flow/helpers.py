"""Helper functions for Hydro-Québec config flow."""

from __future__ import annotations

import logging

import aiohttp

from ..public_data.normalize import extract_records, get_field, normalize_sector
from ..public_data.offers import PEAK_OFFERS, normalize_offer

_LOGGER = logging.getLogger(__name__)

# Hydro-Québec open data API endpoint (Opendatasoft v2.1)
WINTER_PEAKS_API_BASE = "https://donnees.hydroquebec.com/api/explore/v2.1"
WINTER_PEAKS_DATASET = "evenements-pointe"
WINTER_PEAKS_URL = f"{WINTER_PEAKS_API_BASE}/catalog/datasets/{WINTER_PEAKS_DATASET}/records"

# Sector mapping (canonical feed value -> display label)
SECTOR_MAPPING = {
    "Residentiel": "Residential",
    "Affaires": "Commercial",
}

DEFAULT_SECTORS = ["Residentiel", "Affaires"]

# Rates offered when the feed cannot be read
DEFAULT_OFFERS_BY_SECTOR = {
    "Residentiel": ["CPC-D", "TPC-DPC"],
    "Affaires": ["GDP-Affaires", "CPC-G"],
}

# One row per (offer, sector) pair, whatever their values are
_GROUP_PARAMS: dict[str, str | int] = {
    "select": "offre,secteurclient,count(*) as total",
    "group_by": "offre,secteurclient",
    "limit": 100,
}


def _rate_option(code: str) -> dict[str, str]:
    """Build a rate selection option for an offer code."""
    offer = PEAK_OFFERS[code]
    return {
        "value": f"{offer.rate}|{offer.rate_option}",
        "label": offer.label,
        "rate": offer.rate,
        "rate_option": offer.rate_option,
        "offer": code,
    }


def _default_rate_options(sector: str) -> list[dict[str, str]]:
    """Return the fallback rate selection options for a sector."""
    canonical_sector = normalize_sector(sector)
    codes = DEFAULT_OFFERS_BY_SECTOR.get(canonical_sector, DEFAULT_OFFERS_BY_SECTOR["Affaires"])
    return [_rate_option(code) for code in codes]


async def _fetch_dataset(
    params: dict[str, str | int], timeout: int = 10
) -> list[dict[str, object]]:
    """Query the peak events dataset and return its records."""
    async with (
        aiohttp.ClientSession() as session,
        session.get(
            WINTER_PEAKS_URL, params=params, timeout=aiohttp.ClientTimeout(total=timeout)
        ) as response,
    ):
        response.raise_for_status()
        return extract_records(await response.json())


async def _fetch_offer_rows() -> list[dict[str, object]]:
    """Return one row per (offer, sector) pair.

    Falls back to a plain page of events when the grouped query is refused,
    which keeps the flow working if Hydro-Québec renames a field.
    """
    try:
        rows = await _fetch_dataset(dict(_GROUP_PARAMS))
        if rows:
            return rows
    except Exception as err:
        _LOGGER.debug("Grouped offer query failed, falling back to events: %s", err)

    rows = await _fetch_dataset({"limit": 100, "timezone": "America/Toronto"})
    return [
        {
            "offre": get_field(row, "offre"),
            "secteurclient": get_field(row, "secteurclient"),
        }
        for row in rows
    ]


async def fetch_available_sectors() -> list[str]:
    """Fetch available sectors from Hydro-Québec open data API."""
    try:
        rows = await _fetch_offer_rows()
        sectors = {
            normalize_sector(get_field(row, "secteurclient"))
            for row in rows
            if get_field(row, "secteurclient")
        }
        return sorted(sector for sector in sectors if sector) or list(DEFAULT_SECTORS)
    except Exception as err:
        _LOGGER.warning("Failed to fetch sectors from API: %s", err)
        return list(DEFAULT_SECTORS)


async def fetch_offers_for_sector(sector: str) -> list[dict[str, str]]:
    """Fetch available offers for a specific sector from Hydro-Québec open data API."""
    try:
        rows = await _fetch_offer_rows()
        wanted_sector = normalize_sector(sector)

        in_sector = [
            row
            for row in rows
            if normalize_sector(get_field(row, "secteurclient")) == wanted_sector
        ]
        # Never return nothing only because the sector value changed shape
        candidates = in_sector or rows

        codes: list[str] = []
        for row in candidates:
            code = normalize_offer(get_field(row, "offre"))
            if code in PEAK_OFFERS and code not in codes:
                codes.append(code)

        if not codes:
            _LOGGER.warning(
                "No known peak offer for sector %s in the public feed, using defaults", sector
            )
            return _default_rate_options(sector)

        rate_options = [_rate_option(code) for code in codes]
        rate_options.sort(key=lambda option: option["label"])
        return rate_options

    except Exception as err:
        _LOGGER.warning("Failed to fetch offers for sector %s from API: %s", sector, err)
        return _default_rate_options(sector)
