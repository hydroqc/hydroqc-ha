"""Unit tests for the HydroQcDataCoordinator."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time
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

        with patch("custom_components.hydroqc.coordinator.base.WebUser") as mock_webuser_class:
            mock_webuser = MagicMock()
            mock_webuser.login = AsyncMock(return_value=True)
            mock_webuser_class.return_value = mock_webuser

            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)

            assert coordinator.name == DOMAIN
            assert coordinator.config_entry == mock_config_entry
            # Manual scheduling: update_interval is None (disabled automatic polling)
            assert coordinator.update_interval is None

    async def test_coordinator_login_success(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_public_client: MagicMock,
    ) -> None:
        """Test coordinator fetches data successfully."""
        mock_config_entry.add_to_hass(hass)

        # Mock successful data fetch
        mock_webuser.check_hq_portal_status = AsyncMock(return_value=True)

        with (
            patch(
                "custom_components.hydroqc.coordinator.base.WebUser",
                return_value=mock_webuser,
            ),
            patch("custom_components.hydroqc.coordinator.base.PublicDataClient", return_value=mock_public_client),
        ):
            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            
            # Mark as first refresh done to trigger data fetch
            coordinator._first_refresh_done = False
            
            await coordinator.async_refresh()

            # Should have fetched data successfully
            assert coordinator.last_update_success
            assert coordinator.data is not None
            assert "contract" in coordinator.data

    async def test_coordinator_login_failure(
        self, hass: HomeAssistant, mock_config_entry: MockConfigEntry
    ) -> None:
        """Test coordinator handles API failure."""
        mock_config_entry.add_to_hass(hass)

        with (
            patch("custom_components.hydroqc.coordinator.base.WebUser") as mock_webuser_class,
            patch("custom_components.hydroqc.coordinator.base.PublicDataClient"),
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
        mock_public_client: MagicMock,
    ) -> None:
        """Test coordinator updates data successfully."""
        mock_config_entry.add_to_hass(hass)

        # Set up contract on webuser
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

            data = coordinator.data
            assert data is not None
            assert "contract" in data
            assert data["contract"] == mock_contract
            assert "contract" in data
            assert data["contract"] == mock_contract
            assert data["account"] == mock_webuser.customers[0].accounts[0]

    async def test_coordinator_session_expiry_handling(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_public_client: MagicMock,
    ) -> None:
        """Test coordinator handles session expiry."""
        mock_config_entry.add_to_hass(hass)
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

            # Simulate session expiry
            mock_webuser.session_expired = True
            mock_webuser.login.reset_mock()

            # Update should trigger re-login
            coordinator._first_refresh_done = False
            await coordinator.async_refresh()

            # Should have called login again
            assert mock_webuser.login.call_count >= 1

    async def test_get_sensor_value_simple_path(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_contract: MagicMock,
        mock_public_client: MagicMock,
    ) -> None:
        """Test get_sensor_value with simple path."""
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

            value = coordinator.get_sensor_value("contract.cp_current_bill")
            assert value == 45.67

    async def test_get_sensor_value_nested_path(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_contract_dpc: MagicMock,
        mock_public_client: MagicMock,
    ) -> None:
        """Test get_sensor_value with nested path."""
        mock_config_entry.add_to_hass(hass)
        mock_webuser.customers[0].accounts[0].contracts[0] = mock_contract_dpc
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
            patch("custom_components.hydroqc.coordinator.base.PublicDataClient"),
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
            patch("custom_components.hydroqc.coordinator.base.PublicDataClient"),
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
            patch("custom_components.hydroqc.coordinator.base.PublicDataClient"),
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
            patch("custom_components.hydroqc.coordinator.base.PublicDataClient"),
        ):
            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            await coordinator.async_refresh()

            assert coordinator.rate == "D"
            assert coordinator.rate_with_option == "DCPC"

    @freeze_time("2025-12-09 10:00:00", tz_offset=-5)  # Freeze time before the test event
    async def test_calendar_sync_with_valid_entity(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
        mock_contract_dpc: MagicMock,
        mock_public_client: MagicMock,
    ) -> None:
        """Test calendar sync with valid calendar entity."""
        # Update config to include calendar
        mock_config_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                **mock_config_entry.data,
                "rate": "DPC",
                "rate_option": "",
                "calendar_entity_id": "calendar.test",
                "include_non_critical_peaks": False,
            },
            entry_id=mock_config_entry.entry_id,
            unique_id=mock_config_entry.unique_id,
        )
        mock_config_entry.add_to_hass(hass)

        # Mock calendar component being loaded
        hass.config.components.add("calendar")

        # Set up calendar state
        hass.states.async_set("calendar.test", "idle")

        # Setup peak handler with events for calendar sync
        mock_peak_handler = MagicMock()
        mock_event = MagicMock()
        # Use a specific future date for deterministic testing
        mock_event.start_date = datetime(2025, 12, 15, 18, 0, tzinfo=ZoneInfo("America/Toronto"))
        mock_event.end_date = datetime(2025, 12, 15, 20, 0, tzinfo=ZoneInfo("America/Toronto"))
        mock_event.is_critical = True
        mock_peak_handler._events = [mock_event]
        mock_public_client.peak_handler = mock_peak_handler
        
        with (
            patch(
                "custom_components.hydroqc.coordinator.base.WebUser",
                return_value=mock_webuser,
            ),
            patch("custom_components.hydroqc.coordinator.base.PublicDataClient", return_value=mock_public_client),
            patch("custom_components.hydroqc.coordinator.calendar_sync.calendar_manager") as mock_cal_mgr,
        ):
            mock_cal_mgr.async_sync_events = AsyncMock(return_value={"uid1"})

            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            await coordinator.async_refresh()

            # Wait for calendar sync task to complete
            if hasattr(coordinator, "_calendar_sync_task") and coordinator._calendar_sync_task:
                await coordinator._calendar_sync_task

            # Verify calendar sync was called
            mock_cal_mgr.async_sync_events.assert_called_once()

    async def test_calendar_sync_missing_entity_disables(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
    ) -> None:
        """Test calendar sync auto-disables after multiple validation failures."""
        # Register persistent_notification service
        mock_notification_service = AsyncMock()
        hass.services.async_register("persistent_notification", "create", mock_notification_service)

        # Update config to include calendar
        mock_config_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                **mock_config_entry.data,
                "rate": "DPC",
                "calendar_entity_id": "calendar.missing",
            },
            entry_id=mock_config_entry.entry_id,
            unique_id=mock_config_entry.unique_id,
        )
        mock_config_entry.add_to_hass(hass)

        # Mock calendar component being loaded
        hass.config.components.add("calendar")

        # Don't set up calendar state (entity missing)

        with (
            patch(
                "custom_components.hydroqc.coordinator.WebUser",
                return_value=mock_webuser,
            ),
            patch("custom_components.hydroqc.coordinator.base.PublicDataClient") as mock_client,
        ):
            mock_peak_handler = MagicMock()
            # Create mock events with proper date attributes for sorting
            def create_mock_event(idx: int) -> MagicMock:
                event = MagicMock()
                event.is_critical = True
                event.start_date = datetime(2026, 1, 28, 6 + idx, 0, 0, tzinfo=ZoneInfo("America/Toronto"))
                event.end_date = datetime(2026, 1, 28, 9 + idx, 0, 0, tzinfo=ZoneInfo("America/Toronto"))
                return event
            
            mock_peak_handler._events = [create_mock_event(0)]
            mock_client.return_value.peak_handler = mock_peak_handler

            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            
            # Retry 10 times (max_validation_attempts = 10)
            for i in range(10):
                # Change events each time to trigger calendar sync (different signature)
                mock_peak_handler._events = [create_mock_event(j) for j in range(i + 2)]
                
                await coordinator.async_refresh()
                if hasattr(coordinator, "_calendar_sync_task") and coordinator._calendar_sync_task:
                    await coordinator._calendar_sync_task
                
                # Should not disable until after 10th attempt
                if i < 9:
                    assert coordinator._calendar_entity_id == "calendar.missing"  # Still set
                    # Note: validation attempts may not increment on every refresh
                    # due to calendar sync optimization

            # After 10 attempts, calendar entity ID should be cleared (disabled)
            assert coordinator._calendar_entity_id is None
            assert coordinator._calendar_validation_attempts == 10
            # Notification service should have been called
            assert mock_notification_service.called

    async def test_calendar_sync_skipped_for_non_peak_rates(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
    ) -> None:
        """Test calendar sync is skipped for rates without peaks."""
        # Update config to include calendar but with rate D
        mock_config_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                **mock_config_entry.data,
                "rate": "D",
                "rate_option": "",
                "calendar_entity_id": "calendar.test",
            },
            entry_id=mock_config_entry.entry_id,
            unique_id=mock_config_entry.unique_id,
        )
        mock_config_entry.add_to_hass(hass)

        with (
            patch(
                "custom_components.hydroqc.coordinator.WebUser",
                return_value=mock_webuser,
            ),
            patch("custom_components.hydroqc.coordinator.base.PublicDataClient"),
            patch("custom_components.hydroqc.coordinator.calendar_manager") as mock_cal_mgr,
        ):
            mock_cal_mgr.async_sync_events = AsyncMock()

            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
            await coordinator.async_refresh()

            # Wait for any potential task
            if hasattr(coordinator, "_calendar_sync_task") and coordinator._calendar_sync_task:
                await coordinator._calendar_sync_task

            # Verify calendar sync was NOT called
            mock_cal_mgr.async_sync_events.assert_not_called()

    async def test_contract_name_property(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
    ) -> None:
        """Test contract_name property returns configured name."""
        with (
            patch(
                "custom_components.hydroqc.coordinator.WebUser",
                return_value=mock_webuser,
            ),
            patch("custom_components.hydroqc.coordinator.base.PublicDataClient"),
        ):
            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)

            assert coordinator.contract_name == "Home"

    async def test_contract_id_portal_mode(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_webuser: MagicMock,
    ) -> None:
        """Test contract_id returns actual ID in portal mode."""
        with (
            patch(
                "custom_components.hydroqc.coordinator.WebUser",
                return_value=mock_webuser,
            ),
            patch("custom_components.hydroqc.coordinator.base.PublicDataClient"),
        ):
            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)

            assert coordinator.contract_id == "contract123"

    async def test_contract_id_opendata_mode(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test contract_id generates stable ID in opendata mode."""
        mock_config_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                "auth_mode": "opendata",
                "contract_name": "Test Home",
                "rate": "DPC",
                "rate_option": "",
            },
            entry_id="test_entry_opendata",
            unique_id="opendata_test_home",
        )
        mock_config_entry.add_to_hass(hass)

        with patch("custom_components.hydroqc.coordinator.base.PublicDataClient"):
            coordinator = HydroQcDataCoordinator(hass, mock_config_entry)

            assert coordinator.contract_id == "opendata_test_home"
            assert coordinator.is_opendata_mode is True
