"""Unit tests for sensor entities."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydroqc.const import DOMAIN
from custom_components.hydroqc.coordinator import HydroQcDataCoordinator
from custom_components.hydroqc.sensor import async_setup_entry

EST_TIMEZONE = ZoneInfo("America/Toronto")


@pytest.mark.asyncio
class TestHydroQcSensor:
    """Test the HydroQcSensor entities."""

    async def test_sensor_setup_rate_d(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_contract: MagicMock,
        mock_integration_version: MagicMock,
    ) -> None:
        """Test sensor setup for Rate D contract."""
        mock_config_entry.add_to_hass(hass)
        mock_webuser.customers[0].accounts[0].contracts[0] = mock_contract

        with (
            patch(
                "custom_components.hydroqc.coordinator.WebUser",
                return_value=mock_webuser,
            ),
            patch("custom_components.hydroqc.coordinator.base.PublicDataClient"),
        ):
            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            await coordinator.async_refresh()

            # Register coordinator in hass.data like real integration does
            hass.data.setdefault(DOMAIN, {})
            hass.data[DOMAIN][mock_config_entry.entry_id] = coordinator

            async_add_entities = MagicMock()
            await async_setup_entry(hass, mock_config_entry, async_add_entities)

            # Verify sensors were created
            assert async_add_entities.called
            entities = async_add_entities.call_args[0][0]

            # Rate D should have basic sensors (balance, billing period, etc.)
            # Should NOT have winter credit sensors or peak sensors
            sensor_keys = [entity._sensor_key for entity in entities]
            assert "balance" in sensor_keys
            assert "current_billing_period_projected_bill" in sensor_keys
            assert "current_billing_period_total_consumption" in sensor_keys

            # Winter credit sensors should not be present for Rate D
            assert "wc_cumulated_credit" not in sensor_keys
            assert "dpc_current_state" not in sensor_keys

    async def test_sensor_setup_rate_dcpc(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_contract_dcpc: MagicMock,
        mock_integration_version: MagicMock,
    ) -> None:
        """Test sensor setup for Rate D+CPC contract (winter credits)."""
        # Update config to use CPC rate option
        dcpc_config = MockConfigEntry(
            domain=DOMAIN,
            data={**mock_config_entry.data, "rate": "D", "rate_option": "CPC"},
            entry_id=mock_config_entry.entry_id,
            unique_id=mock_config_entry.unique_id,
        )
        dcpc_config.add_to_hass(hass)
        mock_webuser.customers[0].accounts[0].contracts[0] = mock_contract_dcpc

        with (
            patch(
                "custom_components.hydroqc.coordinator.WebUser",
                return_value=mock_webuser,
            ),
            patch("custom_components.hydroqc.coordinator.base.PublicDataClient"),
        ):
            coordinator = HydroQcDataCoordinator(hass, dcpc_config)
            await coordinator.async_refresh()

            # Register coordinator in hass.data like real integration does
            hass.data.setdefault(DOMAIN, {})
            hass.data[DOMAIN][dcpc_config.entry_id] = coordinator

            async_add_entities = MagicMock()
            await async_setup_entry(hass, dcpc_config, async_add_entities)

            entities = async_add_entities.call_args[0][0]
            sensor_keys = [entity._sensor_key for entity in entities]

            # Should have winter credit sensors
            assert "wc_cumulated_credit" in sensor_keys
            assert "wc_yesterday_morning_peak_credit" in sensor_keys
            assert "wc_yesterday_evening_peak_credit" in sensor_keys

    async def test_sensor_setup_rate_dpc(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_contract_dpc: MagicMock,
        mock_integration_version: MagicMock,
    ) -> None:
        """Test sensor setup for Flex-D (DPC) contract without calendar.

        Without a calendar configured, calendar-based sensors should NOT be created.
        """
        # Update config to use DPC rate (no calendar)
        dpc_config = MockConfigEntry(
            domain=DOMAIN,
            data={**mock_config_entry.data, "rate": "DPC"},
            entry_id=mock_config_entry.entry_id,
            unique_id=mock_config_entry.unique_id,
        )
        dpc_config.add_to_hass(hass)
        mock_webuser.customers[0].accounts[0].contracts[0] = mock_contract_dpc

        with (
            patch(
                "custom_components.hydroqc.coordinator.WebUser",
                return_value=mock_webuser,
            ),
            patch("custom_components.hydroqc.coordinator.base.PublicDataClient"),
        ):
            coordinator = HydroQcDataCoordinator(hass, dpc_config)
            await coordinator.async_refresh()

            # Register coordinator in hass.data like real integration does
            hass.data.setdefault(DOMAIN, {})
            hass.data[DOMAIN][dpc_config.entry_id] = coordinator

            async_add_entities = MagicMock()
            await async_setup_entry(hass, dpc_config, async_add_entities)

            entities = async_add_entities.call_args[0][0]
            sensor_keys = [entity._sensor_key for entity in entities]

            # Calendar-based Flex-D sensors should NOT be created without calendar
            assert "dpc_state" not in sensor_keys
            assert "dpc_next_peak_start" not in sensor_keys
            # Portal-based sensors should still be created
            assert "dpc_critical_hours_count" in sensor_keys

    async def test_sensor_state_value(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_contract: MagicMock,
        mock_integration_version: MagicMock,
        mock_public_client: MagicMock,
    ) -> None:
        """Test sensor returns correct state value."""
        mock_config_entry.add_to_hass(hass)
        mock_webuser.customers[0].accounts[0].contracts[0] = mock_contract
        mock_webuser.check_hq_portal_status = AsyncMock(return_value=True)
        # Set the projected bill value on mock contract
        mock_contract.cp_projected_bill = 75.00

        with (
            patch(
                "custom_components.hydroqc.coordinator.base.WebUser",
                return_value=mock_webuser,
            ),
            patch("custom_components.hydroqc.coordinator.base.PublicDataClient", return_value=mock_public_client),
        ):
            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            coordinator._first_refresh_done = False
            await coordinator.async_refresh()

            # Register coordinator in hass.data like real integration does
            hass.data.setdefault(DOMAIN, {})
            hass.data[DOMAIN][mock_config_entry.entry_id] = coordinator

            async_add_entities = MagicMock()
            await async_setup_entry(hass, mock_config_entry, async_add_entities)

            entities = async_add_entities.call_args[0][0]

            # Find the projected bill sensor
            projected_bill_sensor = next(
                (e for e in entities if e._sensor_key == "current_billing_period_projected_bill"),
                None,
            )
            assert projected_bill_sensor is not None

            # Verify it returns the correct value from coordinator
            assert projected_bill_sensor.native_value == 75.00

    async def test_sensor_attributes(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_contract: MagicMock,
        mock_integration_version: MagicMock,
        mock_public_client: MagicMock,
    ) -> None:
        """Test sensor includes correct attributes."""
        mock_config_entry.add_to_hass(hass)
        mock_webuser.customers[0].accounts[0].contracts[0] = mock_contract
        mock_webuser.check_hq_portal_status = AsyncMock(return_value=True)

        with (
            patch(
                "custom_components.hydroqc.coordinator.base.WebUser",
                return_value=mock_webuser,
            ),
            patch("custom_components.hydroqc.coordinator.base.PublicDataClient", return_value=mock_public_client),
        ):
            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            coordinator._first_refresh_done = False
            await coordinator.async_refresh()

            # Register coordinator in hass.data like real integration does
            hass.data.setdefault(DOMAIN, {})
            hass.data[DOMAIN][mock_config_entry.entry_id] = coordinator

            async_add_entities = MagicMock()
            await async_setup_entry(hass, mock_config_entry, async_add_entities)

            entities = async_add_entities.call_args[0][0]

            # Check that sensors have required attributes
            for entity in entities:
                extra_state_attributes = entity.extra_state_attributes
                assert "last_update" in extra_state_attributes
                assert "data_source" in extra_state_attributes

                # Verify last_update is an ISO timestamp
                last_update = extra_state_attributes["last_update"]
                assert isinstance(last_update, str)
                # Should be parseable as datetime
                datetime.fromisoformat(last_update.replace("Z", "+00:00"))

    async def test_sensor_availability(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_contract: MagicMock,
        mock_integration_version: MagicMock,
    ) -> None:
        """Test sensor availability based on data presence."""
        mock_config_entry.add_to_hass(hass)
        mock_webuser.customers[0].accounts[0].contracts[0] = mock_contract

        with (
            patch(
                "custom_components.hydroqc.coordinator.WebUser",
                return_value=mock_webuser,
            ),
            patch("custom_components.hydroqc.coordinator.base.PublicDataClient"),
        ):
            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            await coordinator.async_refresh()

            # Register coordinator in hass.data like real integration does
            hass.data.setdefault(DOMAIN, {})
            hass.data[DOMAIN][mock_config_entry.entry_id] = coordinator

            async_add_entities = MagicMock()
            await async_setup_entry(hass, mock_config_entry, async_add_entities)

            entities = async_add_entities.call_args[0][0]

            # All sensors should be available with valid data
            for entity in entities:
                assert entity.available

    async def test_sensor_device_info(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_contract: MagicMock,
        mock_integration_version: MagicMock,
    ) -> None:
        """Test sensor device info is correctly set."""
        mock_config_entry.add_to_hass(hass)
        mock_webuser.customers[0].accounts[0].contracts[0] = mock_contract

        with (
            patch(
                "custom_components.hydroqc.coordinator.WebUser",
                return_value=mock_webuser,
            ),
            patch("custom_components.hydroqc.coordinator.base.PublicDataClient"),
        ):
            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            await coordinator.async_refresh()

            # Register coordinator in hass.data like real integration does
            hass.data.setdefault(DOMAIN, {})
            hass.data[DOMAIN][mock_config_entry.entry_id] = coordinator

            async_add_entities = MagicMock()
            await async_setup_entry(hass, mock_config_entry, async_add_entities)

            entities = async_add_entities.call_args[0][0]

            # Check device info
            for entity in entities:
                device_info = entity.device_info
                assert device_info is not None
                assert "identifiers" in device_info
                assert "name" in device_info
                assert "manufacturer" in device_info

    async def test_sensor_unique_id(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_contract: MagicMock,
        mock_integration_version: MagicMock,
    ) -> None:
        """Test sensor unique IDs are correctly formatted."""
        mock_config_entry.add_to_hass(hass)
        mock_webuser.customers[0].accounts[0].contracts[0] = mock_contract

        with (
            patch(
                "custom_components.hydroqc.coordinator.WebUser",
                return_value=mock_webuser,
            ),
            patch("custom_components.hydroqc.coordinator.base.PublicDataClient"),
        ):
            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            await coordinator.async_refresh()

            # Register coordinator in hass.data like real integration does
            hass.data.setdefault(DOMAIN, {})
            hass.data[DOMAIN][mock_config_entry.entry_id] = coordinator

            async_add_entities = MagicMock()
            await async_setup_entry(hass, mock_config_entry, async_add_entities)

            entities = async_add_entities.call_args[0][0]

        # Verify unique IDs are set and contain contract ID
        unique_ids = [entity.unique_id for entity in entities]
        assert len(unique_ids) == len(set(unique_ids))  # All unique
        for uid in unique_ids:
            assert "contract123" in uid