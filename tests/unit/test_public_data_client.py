"""Unit tests for the Hydro-Québec public data client."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from custom_components.hydroqc.public_data.client import PublicDataClient
from custom_components.hydroqc.public_data.models import PeakEvent
from tests.fake_http import FakeSession

ODS_PAYLOAD: dict[str, Any] = {
    "total_count": 2,
    "results": [
        {
            "offre": "CPC-D",
            "datedebut": "2026-12-15T06:00:00-05:00",
            "datefin": "2026-12-15T10:00:00-05:00",
            "plagehoraire": "AM",
            "duree": "PT04H00MS",
            "secteurclient": "Residentiel",
        },
        {
            "offre": "TPC-DPC",
            "datedebut": "2026-12-15T16:00:00-05:00",
            "datefin": "2026-12-15T20:00:00-05:00",
            "plagehoraire": "PM",
            "duree": "PT04H00MS",
            "secteurclient": "Residentiel",
        },
    ],
}

RENAMED_JSON_PAYLOAD: dict[str, Any] = {
    "offresDisponibles": ["Credit hivernal Residentiel (CPC-D)", "Flex Residentiel (TPC-DPC)"],
    "derniereExecution": ["2026-11-25 14:21:34"],
    "evenements": [
        {
            "offre": "Flex Residentiel (TPC-DPC)",
            "dateDebut": "2026-12-16T06:00:00-05:00",
            "dateFin": "2026-12-16T10:00:00-05:00",
            "plageHoraire": "AM",
            "duree": "PT04H00MS",
            "secteurClient": "Residentiel",
        },
        {
            "offre": "Credit hivernal Residentiel (CPC-D)",
            "dateDebut": "2026-12-16T06:00:00-05:00",
            "dateFin": "2026-12-16T10:00:00-05:00",
            "plageHoraire": "AM",
            "duree": "PT04H00MS",
            "secteurClient": "Residentiel",
        },
        {
            "offre": "LAT_40H_7J",
            "dateDebut": "2026-12-16T06:00:00-05:00",
            "dateFin": "2026-12-16T10:00:00-05:00",
            "plageHoraire": "AM",
            "duree": "PT04H00MS",
            "secteurClient": "Affaires",
        },
        {
            # No dates: skipped instead of failing the whole fetch
            "offre": "Flex Residentiel (TPC-DPC)",
        },
    ],
}


def _client(rate_code: str, payload: Any, status: int = 200) -> PublicDataClient:
    """Build a client wired to a fake HTTP session."""
    client = PublicDataClient(rate_code)
    client._session = FakeSession(payload, status)  # type: ignore[assignment]
    return client


@pytest.mark.asyncio
class TestFetchPeakData:
    """Peak events are matched on their normalized offer value."""

    async def test_ods_payload_lowercase_fields(self) -> None:
        """The Opendatasoft shape keeps working."""
        client = _client("DCPC", ODS_PAYLOAD)

        await client.fetch_peak_data()

        assert [event.offer for event in client.peak_handler._events] == ["CPC-D"]
        event = client.peak_handler._events[0]
        assert event.start_date.hour == 6
        assert event.time_slot == "AM"
        assert event.is_critical

    async def test_renamed_offer_labels_on_json_feed(self) -> None:
        """Labelled offers on the JSON feed still match the stored rate."""
        client = _client("DPC", RENAMED_JSON_PAYLOAD)

        await client.fetch_peak_data()

        assert [event.offer for event in client.peak_handler._events] == ["TPC-DPC"]
        event = client.peak_handler._events[0]
        assert event.start_date.day == 16
        assert event.is_residential

    async def test_dcpc_matches_labelled_offer(self) -> None:
        """Winter Credits matches its labelled offer too."""
        client = _client("DCPC", RENAMED_JSON_PAYLOAD)

        await client.fetch_peak_data()

        assert [event.offer for event in client.peak_handler._events] == ["CPC-D"]

    async def test_no_server_side_offer_filter(self) -> None:
        """The feed is not filtered by raw offer value, only by date."""
        client = _client("DPC", RENAMED_JSON_PAYLOAD)

        await client.fetch_peak_data()

        params = client._session.requests[0]["params"]  # type: ignore[attr-defined]
        assert "refine" not in params
        assert "datedebut>=" in params["where"]

    async def test_unknown_offer_is_logged_once(self, caplog: pytest.LogCaptureFixture) -> None:
        """An unrecognized offer value produces one warning, not one per poll."""
        caplog.set_level(logging.WARNING)
        client = _client("M-OEA", RENAMED_JSON_PAYLOAD)

        await client.fetch_peak_data()
        await client.fetch_peak_data()

        warnings = [record for record in caplog.records if "unknown offer value" in record.message]
        assert len(warnings) == 1
        assert "LAT_40H_7J" in warnings[0].getMessage()
        assert client.peak_handler._events == []

    async def test_http_error_is_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """A failed request is warned about and leaves the events untouched."""
        caplog.set_level(logging.WARNING)
        client = _client("DCPC", ODS_PAYLOAD, status=500)

        await client.fetch_peak_data()

        assert any("Failed to fetch peak data" in record.message for record in caplog.records)
        assert client.peak_handler._events == []


class TestPeakEventNormalization:
    """PeakEvent reads either feed spelling."""

    def test_accented_sector(self) -> None:
        """The old accented sector value still counts as residential."""
        event = PeakEvent(
            {
                "offre": "CPC-D",
                "datedebut": "2026-12-15 06:00",
                "datefin": "2026-12-15 10:00",
                "plagehoraire": "AM",
                "duree": "PT04H00MS",
                "secteurclient": "Résidentiel",
            }
        )

        assert event.is_residential
        assert not event.is_commercial
        assert event.sector == "Residentiel"

    def test_camel_case_fields(self) -> None:
        """CamelCase keys from the JSON feed are accepted."""
        event = PeakEvent(
            {
                "offre": "Flex Residentiel (TPC-DPC)",
                "dateDebut": "2026-12-15T16:00:00-05:00",
                "dateFin": "2026-12-15T20:00:00-05:00",
                "plageHoraire": "PM",
                "duree": "PT04H00MS",
                "secteurClient": "Affaires",
            }
        )

        assert event.offer == "TPC-DPC"
        assert event.time_slot == "PM"
        assert event.is_commercial

    def test_missing_dates_raise(self) -> None:
        """A record without dates is rejected with a clear error."""
        with pytest.raises(ValueError, match="Missing date fields"):
            PeakEvent({"offre": "CPC-D"})
