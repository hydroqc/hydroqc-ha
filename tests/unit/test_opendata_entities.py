"""Unit tests for the entities created in OpenData mode."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydroqc.binary_sensor import async_setup_entry as setup_binary_sensors
from custom_components.hydroqc.button import async_setup_entry as setup_buttons
from custom_components.hydroqc.const import DOMAIN
from custom_components.hydroqc.sensor import async_setup_entry as setup_sensors


def _opendata_coordinator(rate_with_option: str) -> MagicMock:
    """Return a coordinator stub in OpenData mode with a calendar handler."""
    coordinator = MagicMock()
    coordinator.rate_with_option = rate_with_option
    coordinator.rate = rate_with_option
    coordinator.rate_option = ""
    coordinator.is_opendata_mode = True
    coordinator.is_portal_mode = False
    coordinator.get_sensor_value.return_value = None
    coordinator.last_update_success_time = None
    coordinator.calendar_peak_handler = MagicMock(calendar_name="Peaks")
    return coordinator


@pytest.mark.asyncio
class TestOpenDataEntities:
    """OpenData mode exposes the same calendar-based peak entities as portal mode."""

    async def test_dpc_sensors_are_created(
        self,
        hass: HomeAssistant,
        mock_config_entry_opendata: MockConfigEntry,
        mock_integration_version: MagicMock,
    ) -> None:
        """Flex-D gets its calendar-based peak sensors without a login."""
        entry = mock_config_entry_opendata
        entry.add_to_hass(hass)
        coordinator = _opendata_coordinator("DPC")
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

        async_add_entities = MagicMock()
        await setup_sensors(hass, entry, async_add_entities)

        sensor_keys = [entity._sensor_key for entity in async_add_entities.call_args[0][0]]
        assert "dpc_state" in sensor_keys
        assert "dpc_next_peak_start" in sensor_keys
        assert "dpc_next_peak_end" in sensor_keys
        # Portal-only sensors still need a login
        assert "balance" not in sensor_keys
        assert "dpc_critical_hours_count" not in sensor_keys

    async def test_dpc_binary_sensors_are_created(
        self,
        hass: HomeAssistant,
        mock_config_entry_opendata: MockConfigEntry,
        mock_integration_version: MagicMock,
    ) -> None:
        """Flex-D peak flags come from the calendar in OpenData mode."""
        entry = mock_config_entry_opendata
        entry.add_to_hass(hass)
        coordinator = _opendata_coordinator("DPC")
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

        async_add_entities = MagicMock()
        await setup_binary_sensors(hass, entry, async_add_entities)

        sensor_keys = [entity._sensor_key for entity in async_add_entities.call_args[0][0]]
        assert sensor_keys
        assert any(key.startswith("dpc_") for key in sensor_keys)

    async def test_dcpc_sensors_are_created(
        self,
        hass: HomeAssistant,
        mock_config_entry_opendata_dcpc: MockConfigEntry,
        mock_integration_version: MagicMock,
    ) -> None:
        """Winter Credits gets its calendar-based sensors without a login."""
        entry = mock_config_entry_opendata_dcpc
        entry.add_to_hass(hass)
        coordinator = _opendata_coordinator("DCPC")
        coordinator.rate_option = "CPC"
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

        async_add_entities = MagicMock()
        await setup_sensors(hass, entry, async_add_entities)

        sensor_keys = [entity._sensor_key for entity in async_add_entities.call_args[0][0]]
        assert "wc_state" in sensor_keys
        assert "wc_next_peak_start" in sensor_keys
        assert "balance" not in sensor_keys

    async def test_all_platforms_share_one_device(
        self,
        hass: HomeAssistant,
        mock_config_entry_opendata: MockConfigEntry,
        mock_integration_version: MagicMock,
    ) -> None:
        """Sensors, binary sensors and the button land on the same device."""
        entry = mock_config_entry_opendata
        entry.add_to_hass(hass)
        coordinator = _opendata_coordinator("DPC")
        coordinator.rate_option = ""
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

        identifiers: set[frozenset[tuple[str, str]]] = set()
        unique_ids: list[str] = []

        for setup in (setup_sensors, setup_binary_sensors, setup_buttons):
            async_add_entities = MagicMock()
            with patch(
                "custom_components.hydroqc.button.async_get_integration",
                new=AsyncMock(return_value=mock_integration_version),
            ):
                await setup(hass, entry, async_add_entities)
            for entity in async_add_entities.call_args[0][0]:
                identifiers.add(frozenset(entity._attr_device_info["identifiers"]))
                unique_ids.append(entity._attr_unique_id)

        assert identifiers == {frozenset({(DOMAIN, entry.entry_id)})}
        assert len(unique_ids) == len(set(unique_ids))
