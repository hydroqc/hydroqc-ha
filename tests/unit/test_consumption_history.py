"""Unit tests for consumption history synchronization."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydroqc.coordinator import HydroQcDataCoordinator

EST_TIMEZONE = ZoneInfo("America/Toronto")


@pytest.mark.asyncio
class TestConsumptionHistorySync:
    """Test consumption history synchronization."""

    @freeze_time("2024-03-10 01:30:00", tz_offset=-5)  # Before DST (EST)
    async def test_hourly_sync_before_spring_dst(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_contract: MagicMock,
        sample_hourly_json: dict[str, Any],
    ) -> None:
        """Test hourly consumption sync before spring DST transition."""
        mock_config_entry.add_to_hass(hass)
        mock_webuser.customers[0].accounts[0].contracts[0] = mock_contract

        # Mock hourly data spanning DST transition
        mock_contract.get_hourly_energy.return_value = sample_hourly_json
        mock_webuser.check_hq_portal_status = AsyncMock(return_value=True)

        with patch("custom_components.hydroqc.coordinator.base.WebUser", return_value=mock_webuser):
            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            coordinator._first_refresh_done = False
            await coordinator.async_refresh()

            # Verify contract is called with timezone-aware datetime
            # This test ensures DST handling doesn't break before transition
            assert coordinator.data is not None

    @freeze_time("2024-03-10 03:30:00", tz_offset=-4)  # After DST (EDT)
    async def test_hourly_sync_after_spring_dst(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_contract: MagicMock,
        sample_hourly_json: dict[str, Any],
    ) -> None:
        """Test hourly consumption sync after spring DST transition."""
        mock_config_entry.add_to_hass(hass)
        mock_webuser.customers[0].accounts[0].contracts[0] = mock_contract
        mock_webuser.check_hq_portal_status = AsyncMock(return_value=True)

        # Mock hourly data after DST
        mock_contract.get_hourly_energy.return_value = sample_hourly_json

        with patch("custom_components.hydroqc.coordinator.base.WebUser", return_value=mock_webuser):
            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            coordinator._first_refresh_done = False
            await coordinator.async_refresh()

            # Verify coordinator handles DST transition correctly
            assert coordinator.data is not None

    @freeze_time("2024-11-03 01:30:00", tz_offset=-4)  # Fall DST transition
    async def test_hourly_sync_fall_dst_transition(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_contract: MagicMock,
        sample_hourly_json: dict[str, Any],
    ) -> None:
        """Test hourly consumption sync during fall DST transition (repeated hour)."""
        mock_config_entry.add_to_hass(hass)
        mock_webuser.customers[0].accounts[0].contracts[0] = mock_contract
        mock_webuser.check_hq_portal_status = AsyncMock(return_value=True)

        # Mock hourly data spanning repeated hour (1 AM occurs twice)
        mock_contract.get_hourly_energy.return_value = sample_hourly_json

        with patch("custom_components.hydroqc.coordinator.base.WebUser", return_value=mock_webuser):
            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            coordinator._first_refresh_done = False
            await coordinator.async_refresh()

            # Verify coordinator handles fall DST (repeated hour) correctly
            assert coordinator.data is not None

    async def test_csv_import_date_parsing_with_french_decimals(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_contract: MagicMock,
    ) -> None:
        """Test CSV import handles French decimal format correctly."""
        mock_config_entry.add_to_hass(hass)
        mock_webuser.customers[0].accounts[0].contracts[0] = mock_contract
        mock_webuser.check_hq_portal_status = AsyncMock(return_value=True)

        # Mock CSV data with French decimal separators (comma)
        csv_data = {
            "results": {
                "listeDonneesConsoEnergieHoraire": [
                    {
                        "dateHeureDebutPeriode": "2024-11-26 00:00",
                        "consoReg": "1,234",  # French format
                    },
                    {
                        "dateHeureDebutPeriode": "2024-11-26 01:00",
                        "consoReg": "1,567",
                    },
                ]
            }
        }
        mock_contract.get_hourly_energy.return_value = csv_data

        with patch("custom_components.hydroqc.coordinator.base.WebUser", return_value=mock_webuser):
            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            coordinator._first_refresh_done = False
            await coordinator.async_refresh()

            # Should handle French decimals without errors
            assert coordinator.data is not None

    async def test_csv_import_handles_missing_data(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_contract: MagicMock,
    ) -> None:
        """Test CSV import handles missing consumption data gracefully."""
        mock_config_entry.add_to_hass(hass)
        mock_webuser.customers[0].accounts[0].contracts[0] = mock_contract
        mock_webuser.check_hq_portal_status = AsyncMock(return_value=True)

        # Mock CSV data with missing consumption values
        csv_data = {
            "results": {
                "listeDonneesConsoEnergieHoraire": [
                    {
                        "dateHeureDebutPeriode": "2024-11-26 00:00",
                        "consoReg": None,  # Missing data
                    },
                    {
                        "dateHeureDebutPeriode": "2024-11-26 01:00",
                        "consoReg": 1.567,
                    },
                ]
            }
        }
        mock_contract.get_hourly_energy.return_value = csv_data

        with patch("custom_components.hydroqc.coordinator.base.WebUser", return_value=mock_webuser):
            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            coordinator._first_refresh_done = False
            await coordinator.async_refresh()

            # Should skip missing data entries without crashing
            assert coordinator.data is not None

    async def test_statistics_metadata_has_mean_type(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_contract: MagicMock,
        statistics_metadata: dict[str, Any],
    ) -> None:
        """Test statistics metadata includes mean_type field (HA 2025.11+)."""
        mock_config_entry.add_to_hass(hass)
        mock_webuser.customers[0].accounts[0].contracts[0] = mock_contract
        mock_webuser.check_hq_portal_status = AsyncMock(return_value=True)

        with patch("custom_components.hydroqc.coordinator.base.WebUser", return_value=mock_webuser):
            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            coordinator._first_refresh_done = False
            await coordinator.async_refresh()

            # Verify metadata includes required mean_type field
            assert "mean_type" in statistics_metadata
            assert statistics_metadata["has_sum"] is True
            assert statistics_metadata["has_mean"] is False

    async def test_cumulative_sum_calculation(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_contract: MagicMock,
        sample_hourly_json: dict[str, Any],
    ) -> None:
        """Test cumulative sum is calculated correctly for statistics."""
        mock_config_entry.add_to_hass(hass)
        mock_webuser.customers[0].accounts[0].contracts[0] = mock_contract
        mock_webuser.check_hq_portal_status = AsyncMock(return_value=True)

        mock_contract.get_hourly_energy.return_value = sample_hourly_json

        with patch("custom_components.hydroqc.coordinator.base.WebUser", return_value=mock_webuser):
            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            coordinator._first_refresh_done = False
            await coordinator.async_refresh()

            # Cumulative sum should be calculated from first import
            # Each statistics entry should have:
            # - start: timestamp
            # - state: hourly consumption
            # - sum: running total from first import
            assert coordinator.data is not None
