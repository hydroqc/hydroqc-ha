"""Unit tests for the HydroQcDataCoordinator."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydroqc.const import DOMAIN
from custom_components.hydroqc.coordinator import HydroQcDataCoordinator

EST_TIMEZONE = ZoneInfo("America/Toronto")


@pytest.mark.asyncio
class TestHydroQcDataCoordinator:
    """Test the HydroQcDataCoordinator."""

    async def test_coordinator_initialization(
        self, hass: HomeAssistant, mock_config_entry: MockConfigEntry
    ) -> None:
        """Test coordinator initializes correctly."""
        mock_config_entry.add_to_hass(hass)

        with patch(
            "custom_components.hydroqc.coordinator.WebUser"
        ) as mock_webuser_class:
            mock_webuser = MagicMock()
            mock_webuser.login = AsyncMock(return_value=True)
            mock_webuser_class.return_value = mock_webuser

            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)

            assert coordinator.name == DOMAIN
            assert coordinator.config_entry == mock_config_entry
            assert coordinator.update_interval == timedelta(seconds=60)

    async def test_coordinator_login_success(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
    ) -> None:
        """Test coordinator fetches data successfully."""
        mock_config_entry.add_to_hass(hass)

        with (
            patch(
                "custom_components.hydroqc.coordinator.WebUser",
                return_value=mock_webuser,
            ),
            patch("custom_components.hydroqc.coordinator.PublicDataClient"),
        ):
            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            await coordinator.async_refresh()

            # Should have fetched data successfully
            assert coordinator.last_update_success
            assert coordinator.data is not None

    async def test_coordinator_login_failure(
        self, hass: HomeAssistant, mock_config_entry: MockConfigEntry
    ) -> None:
        """Test coordinator handles API failure."""
        mock_config_entry.add_to_hass(hass)

        with patch(
            "custom_components.hydroqc.coordinator.WebUser"
        ) as mock_webuser_class:
            mock_webuser = MagicMock()
            mock_webuser.session_expired = False
            mock_webuser.get_info = AsyncMock(side_effect=Exception("API failed"))
            mock_webuser_class.return_value = mock_webuser

            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)

            with pytest.raises(UpdateFailed):
                await coordinator.async_refresh()

    async def test_coordinator_update_data(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_contract: MagicMock,
    ) -> None:
        """Test coordinator updates data successfully."""
        mock_config_entry.add_to_hass(hass)

        # Set up contract on webuser
        mock_webuser.customers[0].accounts[0].contracts[0] = mock_contract

        with (
            patch(
                "custom_components.hydroqc.coordinator.WebUser",
                return_value=mock_webuser,
            ),
            patch("custom_components.hydroqc.coordinator.PublicDataClient"),
        ):
            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            # Set entry state to SETUP_IN_PROGRESS before refresh
            mock_config_entry.state = ConfigEntryState.SETUP_IN_PROGRESS
            await coordinator.async_refresh()

            data = coordinator.data
            assert data is not None
            assert "contract" in data
            assert data["contract"] == mock_contract
            assert data["account"] == mock_webuser.customers[0].accounts[0]

    async def test_coordinator_session_expiry_handling(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
    ) -> None:
        """Test coordinator handles session expiry."""
        mock_config_entry.add_to_hass(hass)

        with (
            patch(
                "custom_components.hydroqc.coordinator.WebUser",
                return_value=mock_webuser,
            ),
            patch("custom_components.hydroqc.coordinator.PublicDataClient"),
        ):
            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            # Set entry state to SETUP_IN_PROGRESS before refresh
            mock_config_entry.state = ConfigEntryState.SETUP_IN_PROGRESS
            await coordinator.async_refresh()

            # Simulate session expiry
            mock_webuser.session_expired = True
            mock_webuser.login.reset_mock()

            # Update should trigger re-login
            await coordinator.async_refresh()

            # Should have called login again
            assert mock_webuser.login.call_count >= 1

    async def test_get_sensor_value_simple_path(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_contract: MagicMock,
    ) -> None:
        """Test get_sensor_value with simple path."""
        mock_config_entry.add_to_hass(hass)
        mock_webuser.customers[0].accounts[0].contracts[0] = mock_contract

        with (
            patch(
                "custom_components.hydroqc.coordinator.WebUser",
                return_value=mock_webuser,
            ),
            patch("custom_components.hydroqc.coordinator.PublicDataClient"),
        ):
            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            await coordinator.async_refresh()

            value = coordinator.get_sensor_value("contract.cp_current_bill")
            assert value == 45.67

    async def test_get_sensor_value_nested_path(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_contract_dpc: MagicMock,
    ) -> None:
        """Test get_sensor_value with nested path."""
        mock_config_entry.add_to_hass(hass)
        mock_webuser.customers[0].accounts[0].contracts[0] = mock_contract_dpc

        with (
            patch(
                "custom_components.hydroqc.coordinator.WebUser",
                return_value=mock_webuser,
            ),
            patch("custom_components.hydroqc.coordinator.PublicDataClient"),
        ):
            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            await coordinator.async_refresh()

            value = coordinator.get_sensor_value("contract.peak_handler.current_state")
            assert value == "Regular"

    async def test_get_sensor_value_missing_path(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_contract: MagicMock,
    ) -> None:
        """Test get_sensor_value with missing root object returns None."""
        mock_config_entry.add_to_hass(hass)
        mock_webuser.customers[0].accounts[0].contracts[0] = mock_contract

        with (
            patch(
                "custom_components.hydroqc.coordinator.WebUser",
                return_value=mock_webuser,
            ),
            patch("custom_components.hydroqc.coordinator.PublicDataClient"),
        ):
            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            await coordinator.async_refresh()

            # Test missing root object
            value = coordinator.get_sensor_value("nonexistent_root.path")
            assert value is None

            # Note: Can't properly test missing nested attributes with MagicMock
            # as it auto-creates attributes. Real contract objects will return None correctly.

    async def test_is_sensor_seasonal_rate_d(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_contract: MagicMock,
    ) -> None:
        """Test is_sensor_seasonal returns False for Rate D (no peak handler)."""
        mock_config_entry.add_to_hass(hass)
        mock_webuser.customers[0].accounts[0].contracts[0] = mock_contract

        with (
            patch(
                "custom_components.hydroqc.coordinator.WebUser",
                return_value=mock_webuser,
            ),
            patch("custom_components.hydroqc.coordinator.PublicDataClient"),
        ):
            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            await coordinator.async_refresh()

            # Rate D has no peak handler, so all sensors are non-seasonal
            assert not coordinator.is_sensor_seasonal("contract.cp_current_bill")

    async def test_is_sensor_seasonal_rate_dpc_in_season(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_contract_dpc: MagicMock,
    ) -> None:
        """Test is_sensor_seasonal returns False during winter season."""
        mock_config_entry.add_to_hass(hass)
        mock_webuser.customers[0].accounts[0].contracts[0] = mock_contract_dpc

        with (
            patch(
                "custom_components.hydroqc.coordinator.WebUser",
                return_value=mock_webuser,
            ),
            patch("custom_components.hydroqc.coordinator.PublicDataClient"),
        ):
            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            await coordinator.async_refresh()

            # Mock current date to be in winter season (Dec 1 - Mar 31)
            with patch(
                "custom_components.hydroqc.coordinator.datetime"
            ) as mock_datetime:
                mock_datetime.now.return_value = datetime(
                    2024, 12, 15, tzinfo=EST_TIMEZONE
                )
                mock_datetime.side_effect = lambda *args, **kwargs: datetime(
                    *args, **kwargs
                )

                # Peak handler sensors should not be seasonal during winter
                assert not coordinator.is_sensor_seasonal(
                    "contract.peak_handler.current_state"
                )

    async def test_rate_with_option_dcpc(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_contract_dcpc: MagicMock,
    ) -> None:
        """Test rate_with_option returns DCPC for D+CPC."""
        mock_config_entry.add_to_hass(hass)
        mock_webuser.customers[0].accounts[0].contracts[0] = mock_contract_dcpc

        with (
            patch(
                "custom_components.hydroqc.coordinator.WebUser",
                return_value=mock_webuser,
            ),
            patch("custom_components.hydroqc.coordinator.PublicDataClient"),
        ):
            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            await coordinator.async_refresh()

            assert coordinator.rate == "D"
            assert coordinator.rate_with_option == "DCPC"
