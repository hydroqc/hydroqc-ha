"""Unit tests for calendar_manager module."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from custom_components.hydroqc import calendar_manager
from custom_components.hydroqc.public_data_client import PeakEvent

# Timezone constant
EST = ZoneInfo("America/Toronto")


@pytest.fixture
def mock_hass() -> MagicMock:
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()
    return hass


@pytest.fixture
def sample_critical_peak() -> PeakEvent:
    """Create a sample critical peak event (tomorrow)."""
    start = datetime.now(EST) + timedelta(days=1)
    start = start.replace(hour=6, minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=4)
    data = {
        "offre": "CPC-D",
        "datedebut": start.isoformat(),
        "datefin": end.isoformat(),
        "plagehoraire": "AM",
        "duree": "PT04H00MS",
        "secteurclient": "Résidentiel",
    }
    return PeakEvent(data, preheat_duration=120, force_critical=True)


@pytest.fixture
def sample_regular_peak() -> PeakEvent:
    """Create a sample regular (non-critical) peak event (day after tomorrow)."""
    start = datetime.now(EST) + timedelta(days=2)
    start = start.replace(hour=16, minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=4)
    data = {
        "offre": "CPC-D",
        "datedebut": start.isoformat(),
        "datefin": end.isoformat(),
        "plagehoraire": "PM",
        "duree": "PT04H00MS",
        "secteurclient": "Résidentiel",
    }
    return PeakEvent(data, preheat_duration=120, force_critical=False)


def test_generate_event_uid_stability() -> None:
    """Test that event UID generation is stable."""
    contract_id = "test_contract_123"
    peak_start = datetime(2025, 1, 15, 6, 0, tzinfo=EST)

    uid1 = calendar_manager.generate_event_uid(contract_id, peak_start)
    uid2 = calendar_manager.generate_event_uid(contract_id, peak_start)

    assert uid1 == uid2
    assert uid1 == "hydroqc_test_contract_123_2025-01-15T06:00:00-05:00"


def test_generate_event_uid_uniqueness() -> None:
    """Test that different peaks generate different UIDs."""
    contract_id = "test_contract_123"
    peak1_start = datetime(2025, 1, 15, 6, 0, tzinfo=EST)
    peak2_start = datetime(2025, 1, 15, 16, 0, tzinfo=EST)

    uid1 = calendar_manager.generate_event_uid(contract_id, peak1_start)
    uid2 = calendar_manager.generate_event_uid(contract_id, peak2_start)

    assert uid1 != uid2


def test_generate_event_uid_preserves_timezone() -> None:
    """Test that event UID preserves timezone information."""
    contract_id = "test_contract_123"
    peak_start = datetime(2025, 1, 15, 6, 0, tzinfo=EST)

    uid = calendar_manager.generate_event_uid(contract_id, peak_start)

    # Check that timezone offset is included
    assert "-05:00" in uid or "-04:00" in uid  # EST or EDT


@pytest.mark.asyncio
async def test_create_peak_event_critical(
    mock_hass: MagicMock, sample_critical_peak: PeakEvent
) -> None:
    """Test creating a critical peak event."""
    calendar_id = "calendar.test_calendar"
    contract_id = "contract_123"
    contract_name = "Home"

    uid = await calendar_manager.async_create_peak_event(
        mock_hass, calendar_id, sample_critical_peak, contract_id, contract_name, "DCPC"
    )

    # Verify service call
    mock_hass.services.async_call.assert_called_once()
    call_args = mock_hass.services.async_call.call_args

    assert call_args.args[0] == "calendar"
    assert call_args.args[1] == "create_event"

    service_data = call_args.kwargs["service_data"]
    assert service_data["summary"] == "🔴 Pointe critique"
    assert "Réduisez votre consommation" in service_data["description"]
    assert "06:00" in service_data["description"]
    assert "10:00" in service_data["description"]
    assert uid in service_data["description"]  # UID is in description for duplicate detection
    assert service_data["start_date_time"] == sample_critical_peak.start_date.isoformat()
    assert service_data["end_date_time"] == sample_critical_peak.end_date.isoformat()
    assert "uid" not in service_data  # UID field not supported by HA calendar service

    # Verify target
    assert call_args.kwargs["target"] == {"entity_id": calendar_id}
    assert call_args.kwargs["blocking"] is True


@pytest.mark.asyncio
async def test_create_peak_event_regular(
    mock_hass: MagicMock, sample_regular_peak: PeakEvent
) -> None:
    """Test creating a regular (non-critical) peak event."""
    calendar_id = "calendar.test_calendar"
    contract_id = "contract_123"
    contract_name = "Cottage"

    uid = await calendar_manager.async_create_peak_event(
        mock_hass, calendar_id, sample_regular_peak, contract_id, contract_name, "DCPC"
    )

    call_args = mock_hass.services.async_call.call_args
    service_data = call_args.kwargs["service_data"]

    assert service_data["summary"] == "⚪ Pointe régulière"
    assert "16:00" in service_data["description"]
    assert "20:00" in service_data["description"]
    assert uid in service_data["description"]  # UID is in description
    assert "uid" not in service_data  # UID field not supported by HA calendar service


@pytest.mark.asyncio
async def test_create_peak_event_service_failure(
    mock_hass: MagicMock, sample_critical_peak: PeakEvent
) -> None:
    """Test handling of service call failure."""
    mock_hass.services.async_call.side_effect = Exception("Service call failed")

    with pytest.raises(Exception, match="Service call failed"):
        await calendar_manager.async_create_peak_event(
            mock_hass,
            "calendar.test",
            sample_critical_peak,
            "contract_123",
            "Home",
            "DPC",
        )


@pytest.mark.asyncio
async def test_sync_events_creates_future_events_only(
    mock_hass: MagicMock, sample_critical_peak: PeakEvent, sample_regular_peak: PeakEvent
) -> None:
    """Test that sync only creates future events."""
    # Create a past event
    past_start = datetime.now(EST) - timedelta(days=1)
    past_end = past_start + timedelta(hours=4)
    past_data = {
        "offre": "CPC-D",
        "datedebut": past_start.isoformat(),
        "datefin": past_end.isoformat(),
        "plagehoraire": "AM",
        "duree": "PT04H00MS",
        "secteurclient": "Résidentiel",
    }
    past_peak = PeakEvent(past_data, preheat_duration=120, force_critical=True)

    peaks = [past_peak, sample_critical_peak, sample_regular_peak]

    new_uids = await calendar_manager.async_sync_events(
        mock_hass,
        "calendar.test",
        peaks,
        set(),
        "contract_123",
        "Home",
        "DCPC",
        include_non_critical=True,
    )

    # Should create 2 events (future ones)
    assert mock_hass.services.async_call.call_count == 2
    assert len(new_uids) == 2


@pytest.mark.asyncio
async def test_sync_events_filters_by_criticality(
    mock_hass: MagicMock, sample_critical_peak: PeakEvent, sample_regular_peak: PeakEvent
) -> None:
    """Test that sync filters by criticality when include_non_critical=False."""
    peaks = [sample_critical_peak, sample_regular_peak]

    # Only critical peaks
    new_uids = await calendar_manager.async_sync_events(
        mock_hass,
        "calendar.test",
        peaks,
        set(),
        "contract_123",
        "Home",
        "DCPC",
        include_non_critical=False,
    )

    # Should create 1 event (critical one)
    assert mock_hass.services.async_call.call_count == 1
    assert len(new_uids) == 1


@pytest.mark.asyncio
async def test_sync_events_skips_existing(
    mock_hass: MagicMock, sample_critical_peak: PeakEvent
) -> None:
    """Test that sync skips events that are already created."""
    existing_uid = calendar_manager.generate_event_uid(
        "contract_123", sample_critical_peak.start_date
    )
    stored_uids = {existing_uid}

    new_uids = await calendar_manager.async_sync_events(
        mock_hass,
        "calendar.test",
        [sample_critical_peak],
        stored_uids,
        "contract_123",
        "Home",
        "DCPC",
        include_non_critical=True,
    )

    # Should not create any events (already exists)
    assert mock_hass.services.async_call.call_count == 0
    assert new_uids == stored_uids


@pytest.mark.asyncio
async def test_sync_events_sequential_with_delay(
    mock_hass: MagicMock, sample_critical_peak: PeakEvent, sample_regular_peak: PeakEvent
) -> None:
    """Test that events are created sequentially with delay."""
    peaks = [sample_critical_peak, sample_regular_peak]

    with patch("custom_components.hydroqc.calendar_manager.asyncio.sleep") as mock_sleep:
        await calendar_manager.async_sync_events(
            mock_hass,
            "calendar.test",
            peaks,
            set(),
            "contract_123",
            "Home",
            "DCPC",
            include_non_critical=True,
        )

        # Should sleep once (between two events, not after the last)
        mock_sleep.assert_called_once_with(0.1)


@pytest.mark.asyncio
async def test_sync_events_continues_on_individual_failure(
    mock_hass: MagicMock, sample_critical_peak: PeakEvent, sample_regular_peak: PeakEvent
) -> None:
    """Test that sync continues creating events even if one fails."""
    # Make first create fail, second create succeed
    mock_hass.services.async_call.side_effect = [
        Exception("First event failed"),
        None,  # second create succeeds
    ]

    peaks = [sample_critical_peak, sample_regular_peak]

    new_uids = await calendar_manager.async_sync_events(
        mock_hass,
        "calendar.test",
        peaks,
        set(),
        "contract_123",
        "Home",
        "DCPC",
        include_non_critical=True,
    )

    # Should attempt to create both events
    assert mock_hass.services.async_call.call_count == 2
    # Should only track the successful one
    assert len(new_uids) == 1


@pytest.mark.asyncio
async def test_sync_events_empty_list(mock_hass: MagicMock) -> None:
    """Test syncing with empty peak list."""
    new_uids = await calendar_manager.async_sync_events(
        mock_hass,
        "calendar.test",
        [],
        set(),
        "contract_123",
        "Home",
        "DCPC",
        include_non_critical=True,
    )

    mock_hass.services.async_call.assert_not_called()
    assert len(new_uids) == 0


@pytest.mark.asyncio
async def test_sync_events_includes_all_when_flag_true(
    mock_hass: MagicMock, sample_critical_peak: PeakEvent, sample_regular_peak: PeakEvent
) -> None:
    """Test that all events are included when include_non_critical=True."""
    peaks = [sample_critical_peak, sample_regular_peak]

    new_uids = await calendar_manager.async_sync_events(
        mock_hass,
        "calendar.test",
        peaks,
        set(),
        "contract_123",
        "Home",
        "DCPC",
        include_non_critical=True,
    )

    # Should create both events
    assert mock_hass.services.async_call.call_count == 2
    assert len(new_uids) == 2


def test_event_title_templates() -> None:
    """Test French-only event title templates."""
    critical_title = calendar_manager.TITLE_CRITICAL
    regular_title = calendar_manager.TITLE_REGULAR

    assert critical_title == "🔴 Pointe critique"
    assert regular_title == "⚪ Pointe régulière"


def test_event_description_template() -> None:
    """Test French-only event description template."""
    uid = "test_uid_123"
    description = calendar_manager.DESCRIPTION_TEMPLATE.format(
        start="06:00",
        end="10:00",
        created_at="2025-12-04 12:00:00 EST",
        rate="DCPC",
        critical="Oui",
        uid=uid,
    )

    assert "Réduisez votre consommation" in description
    assert "Début: 06:00" in description
    assert "Fin: 10:00" in description
    assert "Ajouté le: 2025-12-04 12:00:00 EST" in description
    assert "Tarif: DCPC" in description
    assert "Critique: Oui" in description
    assert f"ID: {uid}" in description


@pytest.mark.asyncio
async def test_get_existing_event_uids_no_calendar_component(mock_hass: MagicMock) -> None:
    """Test getting existing UIDs when calendar component is not loaded."""
    mock_hass.data = {}  # No calendar component

    start_date = datetime.now(EST)
    end_date = start_date + timedelta(days=7)

    uids = await calendar_manager.async_get_existing_event_uids(
        mock_hass, "calendar.test", start_date, end_date
    )

    assert len(uids) == 0


@pytest.mark.asyncio
async def test_get_existing_event_uids_no_matching_entity(mock_hass: MagicMock) -> None:
    """Test getting existing UIDs when calendar entity doesn't exist."""
    # Mock calendar component but no matching entity
    mock_calendar_component = MagicMock()
    mock_calendar_component.entities = []
    mock_hass.data = {"calendar": mock_calendar_component}

    start_date = datetime.now(EST)
    end_date = start_date + timedelta(days=7)

    uids = await calendar_manager.async_get_existing_event_uids(
        mock_hass, "calendar.test", start_date, end_date
    )

    assert len(uids) == 0


@pytest.mark.asyncio
async def test_get_existing_event_uids_finds_hydroqc_events(mock_hass: MagicMock) -> None:
    """Test extracting UIDs from calendar event descriptions."""
    from homeassistant.components.calendar import CalendarEntity

    # Mock calendar entity with events
    mock_event1 = MagicMock()
    mock_event1.description = (
        "Test event\nID: hydroqc_contract_123_2025-01-15T06:00:00-05:00\nOther data"
    )

    mock_event2 = MagicMock()
    mock_event2.description = "Another event\nID: hydroqc_contract_123_2025-01-15T16:00:00-05:00"

    mock_event3 = MagicMock()
    mock_event3.description = "Event without UID"  # Should be ignored

    mock_calendar_entity = MagicMock(spec=CalendarEntity)
    mock_calendar_entity.entity_id = "calendar.test"
    mock_calendar_entity.async_get_events = AsyncMock(
        return_value=[mock_event1, mock_event2, mock_event3]
    )

    mock_calendar_component = MagicMock()
    mock_calendar_component.entities = [mock_calendar_entity]
    mock_hass.data = {"calendar": mock_calendar_component}

    start_date = datetime.now(EST)
    end_date = start_date + timedelta(days=7)

    uids = await calendar_manager.async_get_existing_event_uids(
        mock_hass, "calendar.test", start_date, end_date
    )

    assert len(uids) == 2
    assert "hydroqc_contract_123_2025-01-15T06:00:00-05:00" in uids
    assert "hydroqc_contract_123_2025-01-15T16:00:00-05:00" in uids


@pytest.mark.asyncio
async def test_get_existing_event_uids_handles_errors(mock_hass: MagicMock) -> None:
    """Test that errors querying calendar are handled gracefully."""
    from homeassistant.components.calendar import CalendarEntity

    mock_calendar_entity = MagicMock(spec=CalendarEntity)
    mock_calendar_entity.entity_id = "calendar.test"
    mock_calendar_entity.async_get_events = AsyncMock(side_effect=Exception("Calendar error"))

    mock_calendar_component = MagicMock()
    mock_calendar_component.entities = [mock_calendar_entity]
    mock_hass.data = {"calendar": mock_calendar_component}

    start_date = datetime.now(EST)
    end_date = start_date + timedelta(days=7)

    # Should not raise, just return empty set
    uids = await calendar_manager.async_get_existing_event_uids(
        mock_hass, "calendar.test", start_date, end_date
    )

    assert len(uids) == 0


@pytest.mark.asyncio
async def test_sync_events_dpc_only_critical(
    mock_hass: MagicMock,
) -> None:
    """Test DPC rate only creates events for critical peaks."""
    # Create DPC peaks (all from API, all critical)
    dpc_peak1 = PeakEvent(
        {
            "offre": "TPC-DPC",
            "datedebut": (datetime.now(EST) + timedelta(days=1))
            .replace(hour=14, minute=0)
            .isoformat(),
            "datefin": (datetime.now(EST) + timedelta(days=1))
            .replace(hour=18, minute=0)
            .isoformat(),
            "plagehoraire": "PM",
            "duree": "PT04H00MS",
            "secteurclient": "Résidentiel",
        },
        preheat_duration=120,
        force_critical=True,  # All DPC API events are critical
    )

    peaks = [dpc_peak1]

    new_uids = await calendar_manager.async_sync_events(
        mock_hass,
        "calendar.test",
        peaks,
        set(),
        "contract_dpc",
        "Home",
        "DPC",
        include_non_critical=False,  # Default setting
    )

    # Should create 1 event (critical DPC peak)
    assert mock_hass.services.async_call.call_count == 1
    assert len(new_uids) == 1


@pytest.mark.asyncio
async def test_sync_events_merges_stored_and_calendar_uids(
    mock_hass: MagicMock, sample_critical_peak: PeakEvent
) -> None:
    """Test that sync merges UIDs from storage and calendar to avoid duplicates."""
    from homeassistant.components.calendar import CalendarEntity

    # Create a second peak
    peak2_start = datetime.now(EST) + timedelta(days=3)
    peak2_start = peak2_start.replace(hour=16, minute=0, second=0, microsecond=0)
    peak2_end = peak2_start + timedelta(hours=4)
    peak2_data = {
        "offre": "CPC-D",
        "datedebut": peak2_start.isoformat(),
        "datefin": peak2_end.isoformat(),
        "plagehoraire": "PM",
        "duree": "PT04H00MS",
        "secteurclient": "Résidentiel",
    }
    peak2 = PeakEvent(peak2_data, preheat_duration=120, force_critical=True)

    # UID for first peak is in storage
    uid1 = calendar_manager.generate_event_uid("contract_123", sample_critical_peak.start_date)
    stored_uids = {uid1}

    # UID for second peak is in calendar (but not storage)
    uid2 = calendar_manager.generate_event_uid("contract_123", peak2.start_date)

    # Mock calendar entity with second event
    mock_event = MagicMock()
    mock_event.description = f"Test event\nID: {uid2}\nOther data"

    mock_calendar_entity = MagicMock(spec=CalendarEntity)
    mock_calendar_entity.entity_id = "calendar.test"
    mock_calendar_entity.async_get_events = AsyncMock(return_value=[mock_event])

    mock_calendar_component = MagicMock()
    mock_calendar_component.entities = [mock_calendar_entity]
    mock_hass.data = {"calendar": mock_calendar_component}

    peaks = [sample_critical_peak, peak2]

    new_uids = await calendar_manager.async_sync_events(
        mock_hass,
        "calendar.test",
        peaks,
        stored_uids,
        "contract_123",
        "Home",
        "DCPC",
        include_non_critical=True,
    )

    # Should not create any events (both already exist - one in storage, one in calendar)
    assert mock_hass.services.async_call.call_count == 0
    # Both UIDs should be tracked
    assert len(new_uids) == 2
    assert uid1 in new_uids
    assert uid2 in new_uids


@pytest.mark.asyncio
async def test_sync_events_different_contracts_same_calendar(
    mock_hass: MagicMock,
) -> None:
    """Test multiple contracts can share the same calendar with unique UIDs."""
    # Create peaks for two different contracts at same time
    start = datetime.now(EST) + timedelta(days=1)
    start = start.replace(hour=6, minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=4)

    peak_data = {
        "offre": "CPC-D",
        "datedebut": start.isoformat(),
        "datefin": end.isoformat(),
        "plagehoraire": "AM",
        "duree": "PT04H00MS",
        "secteurclient": "Résidentiel",
    }

    peak1 = PeakEvent(peak_data, preheat_duration=120, force_critical=True)
    peak2 = PeakEvent(peak_data, preheat_duration=120, force_critical=True)

    # First contract syncs
    uids1 = await calendar_manager.async_sync_events(
        mock_hass,
        "calendar.shared",
        [peak1],
        set(),
        "contract_home",
        "Home",
        "DCPC",
        include_non_critical=True,
    )

    # Second contract syncs (same calendar, different contract ID)
    uids2 = await calendar_manager.async_sync_events(
        mock_hass,
        "calendar.shared",
        [peak2],
        set(),
        "contract_cottage",
        "Cottage",
        "DCPC",
        include_non_critical=True,
    )

    # Each contract should create its own event (different UIDs due to different contract IDs)
    assert mock_hass.services.async_call.call_count == 2
    assert len(uids1) == 1
    assert len(uids2) == 1
    # UIDs should be different even though peaks are at same time
    assert list(uids1)[0] != list(uids2)[0]
