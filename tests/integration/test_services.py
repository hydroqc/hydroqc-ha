"""Integration tests for services."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydroqc.const import DOMAIN


@pytest.mark.skip(
    reason="Integration tests require full HA integration loader setup - see issue #5"
)
@pytest.mark.asyncio
class TestServices:
    """Test the services."""

    # TODO: Implement this test when SERVICE_CLEAR_CONSUMPTION_HISTORY is added
    # async def test_clear_consumption_history_service(
    #     self,
    #     hass: HomeAssistant,
    #     mock_config_entry: MockConfigEntry,
    #     mock_webuser: MagicMock,
    #     mock_contract: MagicMock,
    #     mock_statistics_api: MagicMock,
    # ) -> None:
    #     """Test the clear_consumption_history service."""
    #     mock_config_entry.add_to_hass(hass)
    #     mock_webuser.customers[0].accounts[0].contracts[0] = mock_contract
    #
    #     with patch(
    #         "custom_components.hydroqc.coordinator.WebUser", return_value=mock_webuser
    #     ):
    #         # Set up the integration
    #         await hass.config_entries.async_setup(mock_config_entry.entry_id)
    #         await hass.async_block_till_done()
    #
    #         # Call the service
    #         await hass.services.async_call(
    #             DOMAIN,
    #             "clear_consumption_history",
    #             {},
    #             blocking=True,
    #         )
    #
    #         # Verify statistics were cleared
    #         mock_statistics_api.clear_statistics.assert_called()

    async def test_refresh_data_service(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_contract: MagicMock,
    ) -> None:
        """Test the refresh_data service."""
        mock_config_entry.add_to_hass(hass)
        mock_webuser.customers[0].accounts[0].contracts[0] = mock_contract

        with patch("custom_components.hydroqc.coordinator.WebUser", return_value=mock_webuser):
            # Set up the integration
            await hass.config_entries.async_setup(mock_config_entry.entry_id)
            await hass.async_block_till_done()

            # Reset mock to track new calls
            mock_contract.get_info.reset_mock()

            # Call the service
            await hass.services.async_call(
                DOMAIN,
                "refresh_data",
                {},
                blocking=True,
            )

            # Verify data was refreshed
            mock_contract.get_info.assert_called()

    async def test_fetch_hourly_consumption_service(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_contract: MagicMock,
        sample_hourly_json: dict,
    ) -> None:
        """Test the fetch_hourly_consumption service."""
        mock_config_entry.add_to_hass(hass)
        mock_webuser.customers[0].accounts[0].contracts[0] = mock_contract
        mock_contract.get_hourly_energy.return_value = sample_hourly_json

        with patch("custom_components.hydroqc.coordinator.WebUser", return_value=mock_webuser):
            # Set up the integration
            await hass.config_entries.async_setup(mock_config_entry.entry_id)
            await hass.async_block_till_done()

            # Call the service
            await hass.services.async_call(
                DOMAIN,
                "fetch_hourly_consumption",
                {},
                blocking=True,
            )

            # Verify hourly data was fetched
            mock_contract.get_hourly_energy.assert_called()
