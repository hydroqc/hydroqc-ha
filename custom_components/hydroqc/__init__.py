"""The Hydro-Québec integration."""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from . import calendar_manager
from .const import DOMAIN
from .coordinator import HydroQcDataCoordinator

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
]

# Service constants
SERVICE_REFRESH_DATA = "refresh_data"
SERVICE_SYNC_HISTORY = "sync_consumption_history"
SERVICE_CREATE_PEAK_EVENT = "create_peak_event"

ATTR_DAYS_BACK = "days_back"
ATTR_DATE = "date"
ATTR_TIME_SLOT = "time_slot"

SERVICE_REFRESH_SCHEMA = cv.make_entity_service_schema({})

SERVICE_SYNC_HISTORY_SCHEMA = cv.make_entity_service_schema(
    {
        vol.Optional(ATTR_DAYS_BACK, default=731): cv.positive_int,
    }
)

SERVICE_CREATE_PEAK_EVENT_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): vol.Any(cv.string, vol.All(cv.ensure_list, [cv.string])),
        vol.Required(ATTR_DATE): cv.date,
        vol.Required(ATTR_TIME_SLOT): vol.In(["AM", "PM"]),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Hydro-Québec from a config entry."""
    _LOGGER.debug("Setting up Hydro-Québec integration for %s", entry.title)

    # Migration: Remove deprecated update_interval from options
    if "update_interval" in entry.options:
        new_options = {k: v for k, v in entry.options.items() if k != "update_interval"}
        hass.config_entries.async_update_entry(entry, options=new_options)
        _LOGGER.info("Migrated config: removed deprecated 'update_interval' option")

    coordinator = HydroQcDataCoordinator(hass, entry)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady(f"Error connecting to Hydro-Québec: {err}") from err

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Load persisted calendar event UIDs from storage
    await coordinator.async_load_calendar_uids()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services (only once, first entry sets them up)
    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH_DATA):
        await _async_register_services(hass)

    # Mark first refresh as done
    coordinator._first_refresh_done = True

    # Register options update listener for immediate calendar sync
    async def _async_options_updated(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Handle options update - trigger immediate calendar sync if configured."""
        coord: HydroQcDataCoordinator = hass.data[DOMAIN][config_entry.entry_id]

        # Update coordinator with new calendar settings
        coord._calendar_entity_id = config_entry.options.get(
            "calendar_entity_id", config_entry.data.get("calendar_entity_id")
        )

        # Reset validation state to re-validate new calendar entity
        coord._calendar_validation_attempts = 0
        coord._calendar_validation_passed = False

        # Trigger immediate calendar sync if calendar is configured
        if coord._calendar_entity_id:
            _LOGGER.info(
                "Calendar configuration updated for %s, triggering immediate sync",
                coord.contract_name,
            )
            await coord._async_sync_calendar_events()
        else:
            _LOGGER.info("Calendar configuration removed for %s", coord.contract_name)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    if coordinator.is_portal_mode and coordinator._contract:
        # Check if consumption sync is enabled
        enable_consumption_sync = entry.data.get("enable_consumption_sync", True)

        if enable_consumption_sync:
            # Check if this is the first setup (history_days present) or a restart (flag removed)
            # We only import history once after initial setup, not on every restart
            history_days = entry.data.get("history_days", 0)

            if history_days > 0:
                # First setup - remove the flag so it doesn't run again on restart
                new_data = dict(entry.data)
                del new_data["history_days"]
                hass.config_entries.async_update_entry(entry, data=new_data)

                if history_days > 30:
                    _LOGGER.info(
                        "User requested %d-day history import, starting CSV import "
                        "(regular sync will run after CSV import completes)",
                        history_days,
                    )
                    coordinator.async_sync_consumption_history(days_back=history_days)
                else:
                    # 30 days or less: regular initial sync already covers this
                    hass.async_create_task(coordinator._async_regular_consumption_sync())
            else:
                # Restart - just run regular sync to catch up on recent data
                hass.async_create_task(coordinator._async_regular_consumption_sync())
        else:
            _LOGGER.info(
                "Consumption sync disabled for %s, skipping consumption history import",
                coordinator.contract_name,
            )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading Hydro-Québec integration for %s", entry.title)

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: HydroQcDataCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

    return unload_ok


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration services."""

    async def handle_refresh_data(call: ServiceCall) -> None:
        """Handle refresh_data service call."""
        # Get entity_id from service call
        entity_ids = call.data.get("entity_id")
        if not entity_ids:
            _LOGGER.warning("No entity_id provided for refresh_data service")
            return

        # Get entity registry
        ent_reg = er.async_get(hass)

        # Find coordinators for the entities
        coordinators_to_refresh = set()
        for entity_id in entity_ids:
            entity = ent_reg.async_get(entity_id)
            if entity and entity.config_entry_id:
                coordinator = hass.data[DOMAIN].get(entity.config_entry_id)
                if coordinator:
                    coordinators_to_refresh.add(coordinator)

        # Refresh all found coordinators
        for coordinator in coordinators_to_refresh:
            await coordinator.async_request_refresh()

        _LOGGER.info("Refreshed %d coordinator(s)", len(coordinators_to_refresh))

    async def handle_fetch_hourly_consumption(call: ServiceCall) -> None:
        """Handle fetch_hourly_consumption service call."""

    async def handle_sync_consumption_history(call: ServiceCall) -> None:
        """Handle sync_consumption_history service call (force CSV import)."""
        days_back: int = call.data.get(ATTR_DAYS_BACK, 731)
        device_ids = call.data.get("device_id")

        if not device_ids:
            _LOGGER.warning("No device_id provided for sync_consumption_history service")
            return

        # Get device registry
        dev_reg = dr.async_get(hass)

        # Find coordinators for the devices
        for device_id in device_ids:
            device = dev_reg.async_get(device_id)
            if not device:
                _LOGGER.warning("Device %s not found", device_id)
                continue

            # Find config entry for this device
            for config_entry_id in device.config_entries:
                coordinator: HydroQcDataCoordinator = hass.data[DOMAIN].get(config_entry_id)
                if coordinator and coordinator.is_portal_mode:
                    # Check if consumption sync is enabled (check options first, then data)
                    enable_consumption_sync = coordinator.entry.options.get(
                        "enable_consumption_sync",
                        coordinator.entry.data.get("enable_consumption_sync", True),
                    )
                    if not enable_consumption_sync:
                        _LOGGER.warning(
                            "Device %s has consumption sync disabled, skipping history sync",
                            device.name or device_id,
                        )
                        continue

                    try:
                        # Start CSV import for historical consumption (non-blocking)
                        coordinator.async_sync_consumption_history(days_back)
                        _LOGGER.info(
                            "Started consumption history sync for device %s (last %d days)",
                            device.name or device_id,
                            days_back,
                        )
                    except Exception as err:
                        _LOGGER.error(
                            "Error starting consumption history sync for device %s: %s",
                            device.name or device_id,
                            err,
                        )
                        raise HomeAssistantError(
                            f"Failed to start consumption history sync: {err}"
                        ) from err
                elif coordinator and not coordinator.is_portal_mode:
                    _LOGGER.warning(
                        "Device %s is in OpenData mode, consumption history not available",
                        device.name or device_id,
                    )

    async def handle_create_peak_event(call: ServiceCall) -> None:
        """Handle create_peak_event service call.

        Creates a manual critical peak event in the calendar for the specified
        date and time slot. Uses the same UID format as OpenData events.
        """
        device_id_input = call.data.get("device_id")
        event_date: datetime.date = call.data.get(ATTR_DATE)
        time_slot: str = call.data.get(ATTR_TIME_SLOT)

        # Normalize device_id to a list
        if isinstance(device_id_input, str):
            device_ids = [device_id_input]
        else:
            device_ids = device_id_input or []

        if not device_ids:
            raise HomeAssistantError("No device_id provided for create_peak_event service")

        if not event_date:
            raise HomeAssistantError("No date provided for create_peak_event service")

        if not time_slot:
            raise HomeAssistantError("No time_slot provided for create_peak_event service")

        # Get device registry
        dev_reg = dr.async_get(hass)

        events_created = 0
        errors = []

        for device_id in device_ids:
            device = dev_reg.async_get(device_id)
            if not device:
                errors.append(f"Device {device_id} not found")
                continue

            # Find config entry for this device
            for config_entry_id in device.config_entries:
                coordinator: HydroQcDataCoordinator = hass.data[DOMAIN].get(config_entry_id)
                if not coordinator:
                    continue

                # Check if calendar is configured
                calendar_entity_id = coordinator._calendar_entity_id
                if not calendar_entity_id:
                    errors.append(
                        f"No calendar configured for {coordinator.contract_name}. "
                        "Configure a calendar in the integration options."
                    )
                    continue

                # Check rate supports peaks
                if coordinator.rate_with_option not in ("DPC", "DCPC"):
                    errors.append(
                        f"{coordinator.contract_name} has rate {coordinator.rate_with_option}, "
                        "peak events only apply to DPC/DCPC rates."
                    )
                    continue

                try:
                    # Build start/end times based on time slot
                    tz = ZoneInfo("America/Toronto")
                    if time_slot == "AM":
                        start_time = datetime.time(6, 0)
                        end_time = datetime.time(10, 0)
                    else:
                        start_time = datetime.time(16, 0)
                        end_time = datetime.time(20, 0)

                    start_dt = datetime.datetime.combine(event_date, start_time, tzinfo=tz)
                    end_dt = datetime.datetime.combine(event_date, end_time, tzinfo=tz)

                    # Check if event already exists
                    existing_events = await calendar_manager.async_get_existing_event_uids(
                        hass, calendar_entity_id, start_dt, end_dt
                    )
                    uid = calendar_manager.generate_event_uid(coordinator.contract_id, start_dt)
                    if uid in existing_events:
                        errors.append(
                            f"{coordinator.contract_name}: Event already exists for "
                            f"{event_date} {time_slot}"
                        )
                        continue

                    # Create a simple object with required attributes for async_create_peak_event
                    # Use default args to capture current values and avoid B023 loop variable issue
                    class ManualPeakEvent:
                        def __init__(
                            self,
                            _start: datetime.datetime = start_dt,
                            _end: datetime.datetime = end_dt,
                        ) -> None:
                            self.start_date = _start
                            self.end_date = _end
                            self.is_critical = True

                    # Create the event using existing function
                    uid = await calendar_manager.async_create_peak_event(
                        hass=hass,
                        calendar_id=calendar_entity_id,
                        peak_event=ManualPeakEvent(),
                        contract_id=coordinator.contract_id,
                        contract_name=coordinator.contract_name,
                        rate=coordinator.rate_with_option,
                    )

                    # Add UID to coordinator's tracked events
                    coordinator._created_event_uids.add(uid)
                    await coordinator.async_save_calendar_uids()

                    # Refresh calendar sensors immediately
                    await coordinator.async_load_calendar_peak_events()
                    coordinator.async_set_updated_data(coordinator.data)

                    events_created += 1
                    _LOGGER.info(
                        "Created manual peak event for %s on %s %s (UID: %s)",
                        coordinator.contract_name,
                        event_date,
                        time_slot,
                        uid,
                    )

                except ValueError as err:
                    # Event already exists or invalid time_slot
                    errors.append(f"{coordinator.contract_name}: {err}")
                except Exception as err:
                    errors.append(f"{coordinator.contract_name}: Failed to create event - {err}")

        if errors and events_created == 0:
            raise HomeAssistantError("; ".join(errors))
        if errors:
            _LOGGER.warning("Some events could not be created: %s", "; ".join(errors))

    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH_DATA,
        handle_refresh_data,
        schema=SERVICE_REFRESH_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SYNC_HISTORY,
        handle_sync_consumption_history,
        schema=SERVICE_SYNC_HISTORY_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_PEAK_EVENT,
        handle_create_peak_event,
        schema=SERVICE_CREATE_PEAK_EVENT_SCHEMA,
    )


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
