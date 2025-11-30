"""The Hydro-Québec integration."""

from __future__ import annotations

import datetime
import logging
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import CONF_MIGRATE_HAUT, CONF_MIGRATE_REG, CONF_MIGRATE_TOTAL, DOMAIN
from .coordinator import HydroQcDataCoordinator
from .statistics_manager import migrate_statistics_streams

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]

# Service constants
SERVICE_REFRESH_DATA = "refresh_data"
SERVICE_SYNC_HISTORY = "sync_consumption_history"
SERVICE_MIGRATE_STATISTICS = "migrate_statistics"

ATTR_DAYS_BACK = "days_back"
ATTR_SOURCE_TOTAL = "source_total"
ATTR_SOURCE_REG = "source_reg"
ATTR_SOURCE_HAUT = "source_haut"

SERVICE_REFRESH_SCHEMA = cv.make_entity_service_schema({})

SERVICE_SYNC_HISTORY_SCHEMA = cv.make_entity_service_schema(
    {
        vol.Optional(ATTR_DAYS_BACK, default=731): cv.positive_int,
    }
)

SERVICE_MIGRATE_STATISTICS_SCHEMA = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_SOURCE_TOTAL): cv.string,
        vol.Optional(ATTR_SOURCE_REG): cv.string,
        vol.Optional(ATTR_SOURCE_HAUT): cv.string,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Hydro-Québec from a config entry."""
    _LOGGER.debug("Setting up Hydro-Québec integration for %s", entry.title)

    coordinator = HydroQcDataCoordinator(hass, entry)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady(f"Error connecting to Hydro-Québec: {err}") from err

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services (only once, first entry sets them up)
    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH_DATA):
        await _async_register_services(hass)

    # Mark first refresh as done and schedule initial consumption sync in background
    # This runs after HA setup completes to avoid blocking startup
    coordinator._first_refresh_done = True
    if coordinator.is_portal_mode and coordinator._contract:
        # Check for migration first
        migrate_total = entry.data.get(CONF_MIGRATE_TOTAL)
        if migrate_total:
            _LOGGER.info("Starting statistics migration from hydroqc2mqtt")
            # Build source mapping
            source_mapping = {
                "total": migrate_total,
                "reg": entry.data.get(CONF_MIGRATE_REG, "none"),
                "haut": entry.data.get(CONF_MIGRATE_HAUT, "none"),
            }

            # Execute migration
            hass.async_create_task(
                _async_execute_migration(hass, entry, coordinator, source_mapping)
            )
        else:
            # No migration - proceed with regular history import
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

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading Hydro-Québec integration for %s", entry.title)

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: HydroQcDataCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

    return unload_ok


async def _async_register_services(hass: HomeAssistant) -> None:  # noqa: PLR0915
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

    async def handle_migrate_statistics(call: ServiceCall) -> None:
        """Handle migrate_statistics service call."""
        source_total = call.data.get(ATTR_SOURCE_TOTAL)
        source_reg = call.data.get(ATTR_SOURCE_REG, "none")
        source_haut = call.data.get(ATTR_SOURCE_HAUT, "none")

        # Get entity registry
        ent_reg = er.async_get(hass)

        # Find entities from service call
        entity_ids = call.data.get("entity_id", [])
        if not entity_ids:
            _LOGGER.warning("No entity_id provided for migrate_statistics service")
            return

        for entity_id in entity_ids:
            entity_entry = ent_reg.async_get(entity_id)
            if not entity_entry or not entity_entry.config_entry_id:
                _LOGGER.warning("Entity %s not found or has no config entry", entity_id)
                continue

            coordinator: HydroQcDataCoordinator = hass.data[DOMAIN].get(
                entity_entry.config_entry_id
            )
            if not coordinator:
                _LOGGER.warning("No coordinator found for entity %s", entity_id)
                continue

            if not coordinator.is_portal_mode:
                _LOGGER.warning("Entity %s is in OpenData mode, migration not available", entity_id)
                continue

            try:
                # Build source mapping (ensure all values are str, not None)
                source_mapping: dict[str, str] = {
                    "total": source_total,
                    "reg": source_reg if source_reg else "none",
                    "haut": source_haut if source_haut else "none",
                }

                # Get entry
                entry = hass.config_entries.async_get_entry(entity_entry.config_entry_id)
                if not entry:
                    raise HomeAssistantError(f"Config entry not found for entity {entity_id}")
                contract_name = entry.data.get("contract_name", "unknown")

                # Execute migration
                _LOGGER.info("Starting migration for entity %s", entity_id)
                await migrate_statistics_streams(
                    hass,
                    source_mapping,
                    coordinator._get_statistic_id,
                    contract_name,
                )

            except Exception as err:
                _LOGGER.error("Error migrating statistics for entity %s: %s", entity_id, err)
                raise HomeAssistantError(f"Failed to migrate statistics: {err}") from err

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
        SERVICE_MIGRATE_STATISTICS,
        handle_migrate_statistics,
        schema=SERVICE_MIGRATE_STATISTICS_SCHEMA,
    )


async def _async_execute_migration(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: HydroQcDataCoordinator,
    source_mapping: dict[str, str],
) -> None:
    """Execute statistics migration and clean up entry data.

    Args:
        hass: Home Assistant instance
        entry: Config entry
        coordinator: Coordinator instance
        source_mapping: Dict mapping stream type to source statistic_id
    """
    try:
        # Execute migration
        contract_name = entry.data.get("contract_name", "unknown")
        results = await migrate_statistics_streams(
            hass,
            source_mapping,
            coordinator._get_statistic_id,
            contract_name,
        )

        _LOGGER.info("Migration completed with results: %s", results)

        # Remove migration keys from entry data (one-time operation)
        new_data = dict(entry.data)
        new_data.pop(CONF_MIGRATE_TOTAL, None)
        new_data.pop(CONF_MIGRATE_REG, None)
        new_data.pop(CONF_MIGRATE_HAUT, None)
        hass.config_entries.async_update_entry(entry, data=new_data)

        # Continue with regular history sync to fill any gaps
        history_days = entry.data.get("history_days", 0)
        if history_days > 30:
            _LOGGER.info("Starting CSV import after migration to fill gaps")
            coordinator.async_sync_consumption_history(days_back=history_days)
            # Remove history_days flag
            new_data = dict(entry.data)
            new_data.pop("history_days", None)
            hass.config_entries.async_update_entry(entry, data=new_data)
        else:
            hass.async_create_task(coordinator._async_regular_consumption_sync())

    except Exception as err:
        _LOGGER.error("Migration failed: %s", err)
        # Continue with regular sync even if migration fails
        hass.async_create_task(coordinator._async_regular_consumption_sync())


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
