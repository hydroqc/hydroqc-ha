"""Unit tests for the HydroQcDataCoordinator."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.core import HomeAssistant
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

        with patch("custom_components.hydroqc.coordinator.WebUser") as mock_webuser_class:
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

        with (
            patch("custom_components.hydroqc.coordinator.WebUser") as mock_webuser_class,
            patch("custom_components.hydroqc.coordinator.PublicDataClient"),
        ):
            mock_webuser = MagicMock()
            mock_webuser.session_expired = False
            mock_webuser.get_info = AsyncMock(side_effect=Exception("API failed"))
            mock_webuser.login = AsyncMock(return_value=True)
            mock_webuser_class.return_value = mock_webuser

            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)

            # async_refresh logs errors but doesn't raise
            await coordinator.async_refresh()
            # Data should be None after failure
            assert coordinator.data is None

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
        # Remove peak_handler from Rate D contract
        mock_contract.peak_handler = None

        with (
            patch(
                "custom_components.hydroqc.coordinator.WebUser",
                return_value=mock_webuser,
            ),
            patch("custom_components.hydroqc.coordinator.PublicDataClient"),
        ):
            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            await coordinator.async_refresh()

            # Rate D has no peak handler, so sensors are always available (returns True)
            assert coordinator.is_sensor_seasonal("contract.cp_current_bill")

    async def test_is_sensor_seasonal_rate_dpc_in_season(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_contract_dpc: MagicMock,
    ) -> None:
        """Test is_sensor_seasonal for Portal mode with peak handler (never seasonal)."""
        # Update config to use DPC rate
        mock_config_entry = MockConfigEntry(
            domain=DOMAIN,
            data={**mock_config_entry.data, "rate": "DPC"},
            entry_id=mock_config_entry.entry_id,
            unique_id=mock_config_entry.unique_id,
        )
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

            # DPC peak sensors without CPC option are always available (returns True)
            assert coordinator.is_sensor_seasonal("contract.peak_handler.current_state")

    async def test_rate_with_option_dcpc(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_contract_dcpc: MagicMock,
    ) -> None:
        """Test rate_with_option returns DCPC for D+CPC."""
        # Update config to have CPC rate option
        mock_config_entry = MockConfigEntry(
            domain=DOMAIN,
            data={**mock_config_entry.data, "rate": "D", "rate_option": "CPC"},
            entry_id=mock_config_entry.entry_id,
            unique_id=mock_config_entry.unique_id,
        )
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

    async def test_dcpc_preheat_only_triggers_for_critical_peaks(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
    ) -> None:
        """Test DCPC preheat only triggers when next peak is critical."""
        # Update config to DCPC rate
        mock_config_entry = MockConfigEntry(
            domain=DOMAIN,
            data={**mock_config_entry.data, "rate": "D", "rate_option": "CPC"},
            entry_id=mock_config_entry.entry_id,
            unique_id=mock_config_entry.unique_id,
        )
        mock_config_entry.add_to_hass(hass)

        with (
            patch(
                "custom_components.hydroqc.coordinator.WebUser",
                return_value=mock_webuser,
            ),
            patch("custom_components.hydroqc.coordinator.PublicDataClient") as mock_client_class,
        ):
            # Mock public client with preheat active
            mock_public_client = MagicMock()
            mock_peak_handler = MagicMock()

            # Setup: preheat is in progress
            mock_peak_handler.preheat_in_progress = True

            # Test 1: Next peak is NON-critical - preheat should return False
            mock_next_peak = MagicMock()
            mock_next_peak.is_critical = False
            mock_peak_handler.next_peak = mock_next_peak

            mock_public_client.peak_handler = mock_peak_handler
            mock_client_class.return_value = mock_public_client

            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            coordinator.data = {"public_client": mock_public_client}

            # Should return False (preheat active but next peak not critical)
            result = coordinator.get_sensor_value("public_client.peak_handler.preheat_in_progress")
            assert result is False

            # Test 2: Next peak IS critical - preheat should return True
            mock_next_peak.is_critical = True
            result = coordinator.get_sensor_value("public_client.peak_handler.preheat_in_progress")
            assert result is True

            # Test 3: Preheat not in progress, even with critical peak - should return False
            mock_peak_handler.preheat_in_progress = False
            mock_next_peak.is_critical = True
            result = coordinator.get_sensor_value("public_client.peak_handler.preheat_in_progress")
            assert result is False

    async def test_dcpc_preheat_timestamp_only_for_critical_peaks(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
    ) -> None:
        """Test DCPC preheat timestamp only shows when next peak is critical."""
        # Update config to DCPC rate
        mock_config_entry = MockConfigEntry(
            domain=DOMAIN,
            data={**mock_config_entry.data, "rate": "D", "rate_option": "CPC"},
            entry_id=mock_config_entry.entry_id,
            unique_id=mock_config_entry.unique_id,
        )
        mock_config_entry.add_to_hass(hass)

        with (
            patch(
                "custom_components.hydroqc.coordinator.WebUser",
                return_value=mock_webuser,
            ),
            patch("custom_components.hydroqc.coordinator.PublicDataClient") as mock_client_class,
        ):
            # Mock public client with preheat data
            mock_public_client = MagicMock()
            mock_peak_handler = MagicMock()

            # Mock preheat start date
            preheat_start = datetime(2025, 12, 3, 8, 0, tzinfo=ZoneInfo("America/Toronto"))

            # Setup next peak with preheat
            mock_next_peak = MagicMock()
            mock_preheat = MagicMock()
            mock_preheat.start_date = preheat_start
            mock_next_peak.preheat = mock_preheat

            mock_peak_handler.next_peak = mock_next_peak
            mock_public_client.peak_handler = mock_peak_handler
            mock_client_class.return_value = mock_public_client

            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            coordinator.data = {"public_client": mock_public_client}

            # Test 1: Next peak is NON-critical - should return None
            mock_next_peak.is_critical = False
            result = coordinator.get_sensor_value("public_client.peak_handler.next_peak.preheat.start_date")
            assert result is None

            # Test 2: Next peak IS critical - should return timestamp
            mock_next_peak.is_critical = True
            result = coordinator.get_sensor_value("public_client.peak_handler.next_peak.preheat.start_date")
            assert result == preheat_start
