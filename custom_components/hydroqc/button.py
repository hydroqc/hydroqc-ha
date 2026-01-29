"""Button platform for Hydro-Québec integration."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.loader import async_get_integration

from .const import CONF_CONTRACT_ID, CONF_CONTRACT_NAME, DOMAIN
from .coordinator import HydroQcDataCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hydro-Québec button entities from a config entry."""
    coordinator: HydroQcDataCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Get integration version from manifest
    integration = await async_get_integration(hass, DOMAIN)
    version = str(integration.version) if integration.version else "unknown"

    entities: list[ButtonEntity] = []

    # Only add refresh button for DPC/DCPC rates with calendar configured
    if coordinator.rate_with_option in ["DPC", "DCPC"] and coordinator.calendar_peak_handler:
        entities.append(HydroQcRefreshPeakDataButton(coordinator, entry, version))

    if entities:
        async_add_entities(entities)
        _LOGGER.debug("Added %d button entities", len(entities))


class HydroQcRefreshPeakDataButton(CoordinatorEntity[HydroQcDataCoordinator], ButtonEntity):
    """Button to manually refresh peak data from OpenData and calendar."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:refresh"

    def __init__(
        self,
        coordinator: HydroQcDataCoordinator,
        entry: ConfigEntry,
        version: str,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._entry = entry
        self._version = version

        contract_id = entry.data.get(CONF_CONTRACT_ID, "unknown")
        contract_name = entry.data.get(CONF_CONTRACT_NAME, "Contract")

        self._attr_unique_id = f"{contract_id}_refresh_peak_data"
        self._attr_name = "Refresh Peak Data"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(contract_id))},
            name=f"Hydro-Québec - {contract_name}",
            manufacturer="Hydro-Québec",
            model=coordinator.rate_with_option,
            sw_version=version,
        )

    async def async_press(self) -> None:
        """Handle button press - refresh OpenData and Calendar data.

        This does NOT refresh Portal data (contract/billing).
        Only refreshes peak announcement data and calendar-based sensor data.
        """
        _LOGGER.info("[Button] Manual refresh triggered for %s", self.coordinator.contract_name)

        # Refresh OpenData (peak announcements)
        if self.coordinator.public_client:
            try:
                _LOGGER.debug("[Button] Fetching OpenData peak data")
                await self.coordinator.public_client.fetch_peak_data()
                _LOGGER.debug("[Button] OpenData peak data fetched successfully")

                # Sync to calendar if events changed (signature-based detection)
                if (
                    self.coordinator._calendar_entity_id
                    and self.coordinator.public_client.peak_handler
                ):
                    current_signature = self.coordinator._get_critical_events_signature()
                    if current_signature != self.coordinator._last_critical_events_signature:
                        if (
                            self.coordinator._calendar_sync_task is None
                            or self.coordinator._calendar_sync_task.done()
                        ):
                            self.coordinator._calendar_sync_task = asyncio.create_task(
                                self.coordinator._async_sync_calendar_events()
                            )
                            self.coordinator._last_critical_events_signature = current_signature
                            _LOGGER.debug(
                                "[Button] Calendar sync triggered (signature changed)",
                            )

            except Exception as err:
                _LOGGER.warning("[Button] Failed to fetch OpenData peak data: %s", err)

        # Wait for calendar sync to complete before reading calendar
        if self.coordinator._calendar_sync_task and not self.coordinator._calendar_sync_task.done():
            try:
                _LOGGER.debug("[Button] Waiting for calendar sync to complete")
                await asyncio.wait_for(self.coordinator._calendar_sync_task, timeout=30.0)
            except TimeoutError:
                _LOGGER.warning("[Button] Calendar sync timed out, proceeding anyway")
            except Exception as err:
                _LOGGER.warning("[Button] Calendar sync failed: %s, proceeding anyway", err)

        # Refresh calendar-based sensor data
        if self.coordinator.calendar_peak_handler:
            _LOGGER.debug("[Button] Refreshing calendar peak data")
            await self.coordinator.async_load_calendar_peak_events()

        # Notify listeners of updated data
        self.coordinator.async_set_updated_data(self.coordinator.data)
        _LOGGER.info("[Button] Peak data refresh complete for %s", self.coordinator.contract_name)
