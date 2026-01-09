"""Sensor platform for Hydro-Québec integration."""

from __future__ import annotations

import datetime
import logging
from collections.abc import Mapping
from typing import Any, cast

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.loader import async_get_integration

from .const import CONF_CONTRACT_ID, CONF_CONTRACT_NAME, DOMAIN, SENSORS
from .coordinator import HydroQcDataCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hydro-Québec sensors from a config entry."""
    coordinator: HydroQcDataCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Get integration version from manifest
    integration = await async_get_integration(hass, DOMAIN)
    version = str(integration.version) if integration.version else "unknown"

    entities: list[HydroQcSensor] = []

    for sensor_key, sensor_config_obj in SENSORS.items():
        sensor_config = cast(Mapping[str, Any], sensor_config_obj)
        # Check if sensor is applicable for this rate
        rates = sensor_config.get("rates", [])
        if "ALL" not in rates:
            if coordinator.rate_with_option not in rates:
                continue

        # In opendata mode, only create sensors that use public_client data
        if coordinator.is_opendata_mode:
            data_source = sensor_config.get("data_source", "")
            if isinstance(data_source, str) and not data_source.startswith("public_client."):
                _LOGGER.debug(
                    "Skipping sensor %s in opendata mode (requires portal login)",
                    sensor_key,
                )
                continue

        # Skip winter credit sensors (contract.peak_handler) if not DCPC
        # Note: public_client.peak_handler sensors should NOT be skipped
        data_source_str = str(sensor_config.get("data_source", ""))
        if "contract.peak_handler." in data_source_str and coordinator.rate_option != "CPC":
            continue

        entities.append(HydroQcSensor(coordinator, entry, sensor_key, sensor_config, version))

    async_add_entities(entities)
    _LOGGER.debug("Added %d sensor entities", len(entities))


class HydroQcSensor(CoordinatorEntity[HydroQcDataCoordinator], RestoreEntity, SensorEntity):
    """Representation of a Hydro-Québec sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HydroQcDataCoordinator,
        entry: ConfigEntry,
        sensor_key: str,
        sensor_config: Mapping[str, Any],
        version: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self._sensor_key = sensor_key
        self._sensor_config = sensor_config
        self._data_source = sensor_config["data_source"]
        self._attributes_sources = sensor_config.get("attributes", {})
        self._restored_value: Any = None

        # OpenData mode uses entry_id, Portal mode uses contract info
        contract_name = entry.data.get(CONF_CONTRACT_NAME, "OpenData")
        contract_id = entry.data.get(CONF_CONTRACT_ID, entry.entry_id)

        # Entity configuration
        self._attr_translation_key = self._sensor_key
        self._attr_unique_id = f"{contract_id}_{sensor_key}"
        self._attr_device_class = sensor_config.get("device_class")
        self._attr_state_class = sensor_config.get("state_class")
        self._attr_native_unit_of_measurement = sensor_config.get("unit")
        self._attr_icon = sensor_config.get("icon")

        # Set entity category for diagnostic sensors
        if sensor_config.get("diagnostic", False):
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

        # Set entity registry enabled default (for sensors disabled by default)
        if sensor_config.get("disabled_by_default", False):
            self._attr_entity_registry_enabled_default = False

        # Set attribution based on data source
        if isinstance(self._data_source, str) and self._data_source.startswith("public_client."):
            self._attr_attribution = "Données ouvertes Hydro-Québec"
        elif coordinator.is_portal_mode:
            self._attr_attribution = "Espace Client Hydro-Québec"
        else:
            self._attr_attribution = None

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

        # Restore previous state to avoid showing unknown during reload
        if (last_state := await self.async_get_last_state()) is not None:
            # Try to restore the numeric state
            try:
                if last_state.state not in ("unknown", "unavailable"):
                    self._restored_value = last_state.state
                    _LOGGER.debug(
                        "Restored sensor %s state: %s",
                        self.entity_id,
                        self._restored_value,
                    )
            except (ValueError, TypeError):
                _LOGGER.debug(
                    "Could not restore sensor %s state: %s",
                    self.entity_id,
                    last_state.state,
                )

    @property
    def native_value(self) -> Any:  # noqa: PLR0911
        """Return the state of the sensor."""
        # Check if sensor is seasonal and out of season
        if not self.coordinator.is_sensor_seasonal(self._data_source):
            return None

        value = self.coordinator.get_sensor_value(self._data_source)

        # If coordinator hasn't fetched data yet and we have a restored value, use it
        if value is None and self._restored_value is not None:
            _LOGGER.debug(
                "Sensor %s using restored value: %s (coordinator data not yet available)",
                self.entity_id,
                self._restored_value,
            )
            return self._restored_value

        if value is None:
            return None

        # We have fresh data from coordinator, clear the restored value
        if self._restored_value is not None:
            _LOGGER.debug(
                "Sensor %s got fresh data from coordinator, clearing restored value",
                self.entity_id,
            )
            self._restored_value = None

        # Format value based on type
        if isinstance(value, datetime.datetime):
            # For timestamp device class, return datetime object directly
            # Home Assistant will handle the formatting
            return value if self._attr_device_class == "timestamp" else value.isoformat()

        if isinstance(value, datetime.timedelta):
            return f"{value.seconds / 60} minutes"

        if isinstance(value, (int, float)) and self._attr_device_class == "monetary":
            return round(value, 2)

        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        attributes = {}

        # Add sensor-specific attributes
        for attr_key, attr_source in self._attributes_sources.items():
            attr_value = self.coordinator.get_sensor_value(attr_source)
            if attr_value is not None:
                # Format attribute values
                if isinstance(attr_value, datetime.datetime):
                    attributes[attr_key] = attr_value.isoformat()
                elif isinstance(attr_value, datetime.timedelta):
                    attributes[attr_key] = f"{attr_value.seconds / 60} minutes"
                else:
                    attributes[attr_key] = attr_value

        # Add common attributes
        if self.coordinator.last_update_success_time:
            attributes["last_update"] = self.coordinator.last_update_success_time.isoformat()

        # Determine data source
        if self._data_source.startswith("public_client."):
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
