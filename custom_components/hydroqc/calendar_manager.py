"""Calendar event management for Hydro-Québec peak periods."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from homeassistant.components.calendar import CalendarEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .public_data_client import PeakEvent

_LOGGER = logging.getLogger(__name__)

# French-only event templates (standardized for blueprint compatibility)
TITLE_CRITICAL = "🔴 Pointe critique"
TITLE_REGULAR = "⚪ Pointe régulière"

DESCRIPTION_TEMPLATE = (
    "Réduisez votre consommation d'électricité pendant cette période.\n\n"
    "Début: {start}\n"
    "Fin: {end}\n\n"
    "--- Métadonnées ---\n"
    "Ajouté le: {created_at}\n"
    "Tarif: {rate}\n"
    "Critique: {critical}\n"
    "ID: {uid}"
)

# Delay between calendar event creation calls (seconds)
EVENT_CREATION_DELAY = 0.1


def generate_event_uid(contract_id: str, peak_start: datetime) -> str:
    """Generate a stable UID for a peak event.

    Args:
        contract_id: Contract identifier
        peak_start: Peak event start datetime (timezone-aware)

    Returns:
        Stable UID string for the event
    """
    return f"hydroqc_{contract_id}_{peak_start.isoformat()}"


async def async_create_peak_event(
    hass: HomeAssistant,
    calendar_id: str,
    peak_event: PeakEvent,
    contract_id: str,
    contract_name: str,
    rate: str,
) -> str:
    """Create a calendar event for a peak period.

    Args:
        hass: Home Assistant instance
        calendar_id: Entity ID of the target calendar
        peak_event: Peak event data from PeakHandler
        contract_id: Contract identifier for UID generation
        contract_name: Human-readable contract name for event title
        rate: Rate code (DPC or DCPC)

    Returns:
        The UID of the created event

    Raises:
        Exception: If calendar service call fails
    """
    # Generate stable UID
    uid = generate_event_uid(contract_id, peak_event.start_date)

    # Choose title based on criticality
    title = (
        TITLE_CRITICAL.format(contract_name=contract_name)
        if peak_event.is_critical
        else TITLE_REGULAR.format(contract_name=contract_name)
    )

    # Format description with French datetime strings, metadata, and UID for duplicate detection
    start_str = peak_event.start_date.strftime("%H:%M")
    end_str = peak_event.end_date.strftime("%H:%M")
    # Use local timezone (America/Toronto) for creation timestamp
    local_tz = ZoneInfo("America/Toronto")
    created_at = datetime.now(local_tz).strftime("%Y-%m-%d %H:%M:%S %Z")
    critical_str = "Oui" if peak_event.is_critical else "Non"

    description = DESCRIPTION_TEMPLATE.format(
        start=start_str,
        end=end_str,
        created_at=created_at,
        rate=rate,
        critical=critical_str,
        uid=uid,
    )

    # Prepare service data (no uid field - not supported by HA calendar service)
    # Use location field to store rate for easy filtering in automations
    service_data = {
        "summary": title,
        "description": description,
        "start_date_time": peak_event.start_date.isoformat(),
        "end_date_time": peak_event.end_date.isoformat(),
        "location": f"Hydro-Québec {rate}",
    }

    _LOGGER.debug(
        "Creating calendar event: %s (%s to %s, critical=%s)",
        title,
        start_str,
        end_str,
        peak_event.is_critical,
    )

    try:
        # Call calendar.create_event service
        await hass.services.async_call(
            "calendar",
            "create_event",
            service_data=service_data,
            target={"entity_id": calendar_id},
            blocking=True,
        )

        _LOGGER.info("Created calendar event %s for %s", uid, contract_name)
        return uid

    except Exception as err:
        _LOGGER.error(
            "Failed to create calendar event %s: %s",
            uid,
            err,
        )
        raise


async def async_get_existing_event_uids(
    hass: HomeAssistant,
    calendar_id: str,
    start_date: datetime,
    end_date: datetime,
) -> set[str]:
    """Get UIDs of existing calendar events by checking their descriptions.

    Args:
        hass: Home Assistant instance
        calendar_id: Entity ID of the target calendar
        start_date: Start of date range to check
        end_date: End of date range to check

    Returns:
        Set of UIDs found in existing event descriptions
    """
    existing_uids: set[str] = set()

    try:
        # Try to get the calendar entity directly
        component = hass.data.get("calendar")
        if not component:
            _LOGGER.debug("Calendar component not loaded, skipping event check")
            return existing_uids

        # Get the entity from the component
        calendar_entity = None
        for entity in component.entities:
            if entity.entity_id == calendar_id:
                calendar_entity = entity
                break

        if not calendar_entity or not isinstance(calendar_entity, CalendarEntity):
            _LOGGER.debug("Calendar entity %s not found, assuming no existing events", calendar_id)
            return existing_uids

        # Use the entity's get_events method
        events = await calendar_entity.async_get_events(hass, start_date, end_date)

        # Parse events to extract UIDs from descriptions
        for event in events:
            description = event.description or ""
            # Extract UID from description (format: "ID: hydroqc_...")
            if "ID: hydroqc_" in description:
                # Find the UID in the description
                uid_start = description.find("ID: hydroqc_")
                if uid_start != -1:
                    uid_line = description[uid_start:].split("\n")[0]
                    uid = uid_line.replace("ID: ", "").strip()
                    if uid.startswith("hydroqc_"):
                        existing_uids.add(uid)
                        _LOGGER.debug("Found existing event with UID: %s", uid)

        _LOGGER.info("Found %d existing hydroqc events in calendar", len(existing_uids))

    except Exception as err:
        _LOGGER.warning("Failed to query existing calendar events: %s", err)

    return existing_uids


async def async_sync_events(
    hass: HomeAssistant,
    calendar_id: str,
    peaks: list[PeakEvent],
    stored_uids: set[str],
    contract_id: str,
    contract_name: str,
    rate: str,
    include_non_critical: bool,
) -> set[str]:
    """Sync peak events to a calendar entity.

    Args:
        hass: Home Assistant instance
        calendar_id: Entity ID of the target calendar
        peaks: List of peak events from PeakHandler
        stored_uids: Set of previously created event UIDs (for deduplication)
        contract_id: Contract identifier for UID generation
        contract_name: Human-readable contract name for event titles
        rate: Rate code (DPC or DCPC)
        include_non_critical: Whether to include non-critical peak events

    Returns:
        Updated set of event UIDs (including newly created ones)

    Raises:
        Exception: If calendar validation or event creation fails
    """
    # Filter peaks by criticality if needed
    filtered_peaks = peaks if include_non_critical else [p for p in peaks if p.is_critical]

    # Filter to future peaks only (skip past events)
    now = datetime.now(peaks[0].start_date.tzinfo if peaks else None)
    future_peaks = [p for p in filtered_peaks if p.end_date > now]

    if not future_peaks:
        _LOGGER.debug("No future peaks to sync for %s", contract_name)
        return stored_uids

    # Query calendar for existing events to verify they're actually there
    # This handles cases where calendar was cleared but storage still has UIDs
    if future_peaks:
        start_date = min(p.start_date for p in future_peaks)
        end_date = max(p.end_date for p in future_peaks)
        existing_uids = await async_get_existing_event_uids(hass, calendar_id, start_date, end_date)
        # Merge with stored UIDs to avoid recreating
        all_existing_uids = stored_uids | existing_uids
        _LOGGER.debug(
            "Total tracked UIDs: %d (stored: %d, found in calendar: %d)",
            len(all_existing_uids),
            len(stored_uids),
            len(existing_uids),
        )
    else:
        all_existing_uids = stored_uids

    _LOGGER.info(
        "Syncing %d peak events to calendar %s (include_non_critical=%s)",
        len(future_peaks),
        calendar_id,
        include_non_critical,
    )

    # Create events sequentially with delay
    new_uids = set(all_existing_uids)
    for peak in future_peaks:
        uid = generate_event_uid(contract_id, peak.start_date)

        # Skip if already created (check against all existing UIDs from storage + calendar)
        if uid in all_existing_uids:
            _LOGGER.debug("Skipping existing event %s", uid)
            continue

        try:
            # Create event
            created_uid = await async_create_peak_event(
                hass, calendar_id, peak, contract_id, contract_name, rate
            )
            new_uids.add(created_uid)

            # Delay before next creation
            if peak != future_peaks[-1]:  # Skip delay after last event
                await asyncio.sleep(EVENT_CREATION_DELAY)

        except Exception as err:
            _LOGGER.warning(
                "Failed to create event %s, continuing with others: %s",
                uid,
                err,
            )
            # Continue with other events even if one fails

    _LOGGER.info(
        "Calendar sync complete: %d events created, %d total",
        len(new_uids) - len(stored_uids),
        len(new_uids),
    )

    return new_uids
