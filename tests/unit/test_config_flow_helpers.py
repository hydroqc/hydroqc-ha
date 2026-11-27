"""Unit tests for the config flow helpers reading the public feed."""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.hydroqc.config_flow import helpers
from tests.fake_http import FakeSession

GROUPED_RENAMED_PAYLOAD: dict[str, Any] = {
    "total_count": 4,
    "results": [
        {
            "offre": "Credit hivernal Residentiel (CPC-D)",
            "secteurclient": "Residentiel",
            "total": 47,
        },
        {"offre": "Flex Residentiel (TPC-DPC)", "secteurclient": "Residentiel", "total": 45},
        {"offre": "LAT_40H_7J", "secteurclient": "Affaires", "total": 8},
        {"offre": "GDP-Affaires", "secteurclient": "Affaires", "total": 33},
    ],
}

ACCENTED_SECTOR_PAYLOAD: dict[str, Any] = {
    "evenements": [
        {"offre": "CPC-D", "secteurClient": "Résidentiel"},
        {"offre": "OEA", "secteurClient": "Affaires"},
    ]
}


@pytest.mark.asyncio
class TestFetchOffersForSector:
    """Rate options stay available whatever the feed calls the offers."""

    async def test_labelled_offers_are_offered(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Renamed offer values still produce selectable rates."""
        monkeypatch.setattr(
            helpers.aiohttp, "ClientSession", lambda: FakeSession(GROUPED_RENAMED_PAYLOAD)
        )

        options = await helpers.fetch_offers_for_sector("Residentiel")

        assert [option["value"] for option in options] == ["DPC|", "D|CPC"]
        assert [option["label"] for option in options] == [
            "Flex-D (Dynamic Pricing)",
            "Rate D + Winter Credits (CPC)",
        ]

    async def test_options_are_deduplicated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A code seen under both its old and new name is listed once."""
        payload = {
            "results": [
                {"offre": "TPC-DPC", "secteurclient": "Residentiel"},
                {"offre": "Flex Residentiel (TPC-DPC)", "secteurclient": "Residentiel"},
            ]
        }
        monkeypatch.setattr(helpers.aiohttp, "ClientSession", lambda: FakeSession(payload))

        options = await helpers.fetch_offers_for_sector("Residentiel")

        assert [option["value"] for option in options] == ["DPC|"]

    async def test_empty_feed_falls_back_to_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An empty or unknown feed never leaves the dropdown unusable."""
        monkeypatch.setattr(helpers.aiohttp, "ClientSession", lambda: FakeSession({"results": []}))

        options = await helpers.fetch_offers_for_sector("Residentiel")

        assert [option["value"] for option in options] == ["D|CPC", "DPC|"]

    async def test_error_falls_back_to_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A failed request still offers the default rates."""
        monkeypatch.setattr(helpers.aiohttp, "ClientSession", lambda: FakeSession({}, status=500))

        options = await helpers.fetch_offers_for_sector("Affaires")

        assert [option["value"] for option in options] == ["M|GDP", "M|CPC"]


@pytest.mark.asyncio
class TestFetchAvailableSectors:
    """Sector values are canonicalized."""

    async def test_accented_sector_is_canonical(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The old accented value maps to the canonical sector."""
        monkeypatch.setattr(
            helpers.aiohttp, "ClientSession", lambda: FakeSession(ACCENTED_SECTOR_PAYLOAD)
        )

        assert await helpers.fetch_available_sectors() == ["Affaires", "Residentiel"]

    async def test_error_falls_back_to_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A feed failure keeps both sectors selectable."""
        monkeypatch.setattr(helpers.aiohttp, "ClientSession", lambda: FakeSession({}, status=500))

        assert await helpers.fetch_available_sectors() == ["Residentiel", "Affaires"]
