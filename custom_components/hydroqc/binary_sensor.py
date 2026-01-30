"""Binary sensor platform for Hydro-Québec integration."""

from __future__ import annotations

import logging
from typing import Any, cast

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.loader import async_get_integration

from .const import BINARY_SENSORS, CONF_CONTRACT_ID, CONF_CONTRACT_NAME, DOMAIN
from .coordinator import HydroQcDataCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hydro-Québec binary sensors from a config entry."""
    coordinator: HydroQcDataCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Get integration version from manifest
    integration = await async_get_integration(hass, DOMAIN)
    version = str(integration.version) if integration.version else "unknown"

    entities: list[HydroQcBinarySensor] = []

    for sensor_key, sensor_config in BINARY_SENSORS.items():
        # Check if sensor is applicable for this rate
        rates = cast(list[str], sensor_config["rates"])
        if "ALL" not in rates:
            if coordinator.rate_with_option not in rates:
                continue

        # In opendata mode, only create sensors that use public_client data
        if coordinator.is_opendata_mode:
            data_source = sensor_config["data_source"]
            if isinstance(data_source, str) and not data_source.startswith("public_client."):
                _LOGGER.debug(
                    "Skipping binary sensor %s in opendata mode (requires portal login)",
                    sensor_key,
                )
                continue

        # Skip winter credit sensors (contract.peak_handler) if not DCPC
        # Note: public_client.peak_handler sensors should NOT be skipped
        data_source_str = cast(str, sensor_config["data_source"])
        if "contract.peak_handler." in data_source_str and coordinator.rate_option != "CPC":
            continue

        # Skip calendar-based sensors if no calendar is configured
        if (
            data_source_str.startswith("calendar_peak_handler.")
            and not coordinator.calendar_peak_handler
        ):
            _LOGGER.debug(
                "Skipping binary sensor %s (no calendar configured)",
                sensor_key,
            )
            continue

        entities.append(HydroQcBinarySensor(coordinator, entry, sensor_key, sensor_config, version))

    async_add_entities(entities)
    _LOGGER.debug("Added %d binary sensor entities", len(entities))


class HydroQcBinarySensor(
    CoordinatorEntity[HydroQcDataCoordinator], RestoreEntity, BinarySensorEntity
):
    """Representation of a Hydro-Québec binary sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HydroQcDataCoordinator,
        entry: ConfigEntry,
        sensor_key: str,
        sensor_config: dict[str, Any],
        version: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)

        self._sensor_key = sensor_key
        self._sensor_config = sensor_config
        self._data_source = sensor_config["data_source"]
        self._restored_state: bool | None = None

        # OpenData mode uses entry_id, Portal mode uses contract info
        contract_name = entry.data.get(CONF_CONTRACT_NAME, "OpenData")
        contract_id = entry.data.get(CONF_CONTRACT_ID, entry.entry_id)

        # Entity configuration
        self._attr_translation_key = self._sensor_key
        self._attr_unique_id = f"{contract_id}_{sensor_key}"
        self._attr_device_class = sensor_config.get("device_class")
        self._attr_icon = sensor_config.get("icon")

        # Set entity category for diagnostic sensors
        if sensor_config.get("diagnostic", False):
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

        # Set entity registry enabled default (for sensors disabled by default)
        if sensor_config.get("disabled_by_default", False):
            self._attr_entity_registry_enabled_default = False

        # Set attribution based on data source
        # Calendar-based sensors show calendar name, others show data source
        if isinstance(self._data_source, str) and self._data_source.startswith(
            "calendar_peak_handler."
        ):
            # Attribution will be set dynamically in extra_state_attributes
            # since calendar name may not be available at init time
            self._attr_attribution = None
            self._uses_calendar_attribution = True
        elif isinstance(self._data_source, str) and self._data_source.startswith("public_client."):
            self._attr_attribution = "Données ouvertes Hydro-Québec"
            self._uses_calendar_attribution = False
        elif coordinator.is_portal_mode:
            self._attr_attribution = "Espace Client Hydro-Québec"
            self._uses_calendar_attribution = False
        else:
            self._attr_attribution = None
            self._uses_calendar_attribution = False

        # Device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, contract_id)},
            name=f"Hydro-Québec - {contract_name}",
            manufacturer="Hydro-Québec",
            model=f"{coordinator.rate}{coordinator.rate_option}",
            sw_version=version,
        )

    async def async_added_to_hass(self) -> None:
        """Restore last state when entity is added to hass."""
        await super().async_added_to_hass()

        # Restore previous state to avoid switching off during reload
        if (last_state := await self.async_get_last_state()) is not None:
            self._restored_state = last_state.state == "on"
            _LOGGER.debug(
                "Restored binary sensor %s state: %s",
                self.entity_id,
                self._restored_state,
            )

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        # Check if sensor is seasonal and out of season
        if not self.coordinator.is_sensor_seasonal(self._data_source):
            _LOGGER.debug(
                "Binary sensor %s is out of season, returning None",
                self.entity_id,
            )
            return None

        value = self.coordinator.get_sensor_value(self._data_source)

        # If coordinator hasn't fetched data yet and we have a restored state, use it
        if value is None and self._restored_state is not None:
            _LOGGER.debug(
                "Binary sensor %s using restored state: %s (coordinator data not yet available)",
                self.entity_id,
                self._restored_state,
            )
            return self._restored_state
        _LOGGER.debug(
            "Binary sensor %s got value: %r from data_source: %s",
            self.entity_id,
            value,
            self._data_source,
        )

        if value is None:
            # For public_client sensors (OpenData mode), None means off-season = False
            # For other sensors, None means data unavailable = Unknown
            if self._data_source.startswith("public_client."):
                _LOGGER.debug(
                    "Binary sensor %s returning False (OpenData mode, no peak data)",
                    self.entity_id,
                )
                return False
            _LOGGER.debug(
                "Binary sensor %s returning None (data unavailable)",
                self.entity_id,
            )
            return None

        # Convert to boolean and clear restored state (we now have real data)
        result = bool(value)
        if self._restored_state is not None:
            self._restored_state = None  # Clear restored state once we have real data
        _LOGGER.debug(
            "Binary sensor %s returning %s (converted from %r)",
            self.entity_id,
            result,
            value,
        )
        return result

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        attributes = {}

        # Add common attributes
        if self.coordinator.last_update_success_time:
            attributes["last_update"] = self.coordinator.last_update_success_time.isoformat()

        # Determine data source and attribution
        if self._data_source.startswith("calendar_peak_handler."):
            attributes["data_source"] = "calendar"
            # Set attribution dynamically based on calendar name
            if (
                hasattr(self.coordinator, "calendar_peak_handler")
                and self.coordinator.calendar_peak_handler
            ):
                calendar_name = self.coordinator.calendar_peak_handler.calendar_name
                if calendar_name:
                    attributes["attribution"] = f"Calendrier {calendar_name}"
        elif self._data_source.startswith("public_client."):
            attributes["data_source"] = "open_data"
        elif self.coordinator.is_portal_mode:
            attributes["data_source"] = "portal"
        else:
            attributes["data_source"] = "unknown"

        return attributes if attributes else None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # Sensors are always available to show last known value
        return True
