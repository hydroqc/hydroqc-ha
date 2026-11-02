"""Unit tests for the missing consumption periods of a new contract."""

import datetime
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import hydroqc
import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydroqc.coordinator import HydroQcDataCoordinator

NOW = "2026-09-25 12:00:00-04:00"


def _periods_error(status_code: int) -> hydroqc.error.HydroQcHTTPError:
    return hydroqc.error.HydroQcHTTPError(
        f"Error Fetching resourceObtenirDonneesPeriodesConsommation - {status_code}",
        status_code,
    )


@pytest.fixture
def contract(mock_webuser: MagicMock) -> MagicMock:
    """Contract of the mocked portal account, started two days before NOW."""
    contract = mock_webuser.customers[0].accounts[0].contracts[0]
    contract.start_date = datetime.date(2026, 9, 23)
    contract.get_periods_info = AsyncMock(side_effect=_periods_error(400))
    return contract


@pytest.fixture
def coordinator(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_webuser: MagicMock,
    mock_public_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> HydroQcDataCoordinator:
    """Coordinator wired to the mocked portal account."""
    freezer.move_to(NOW)
    mock_config_entry.add_to_hass(hass)
    with (
        patch("custom_components.hydroqc.coordinator.base.WebUser", return_value=mock_webuser),
        patch(
            "custom_components.hydroqc.coordinator.base.PublicDataClient",
            return_value=mock_public_client,
        ),
    ):
        return HydroQcDataCoordinator(hass, mock_config_entry)


async def test_new_contract_without_periods_keeps_updating(
    coordinator: HydroQcDataCoordinator,
    contract: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A 400 on a recent contract warns once and the rest of the data still updates."""
    caplog.set_level(logging.WARNING)

    await coordinator.async_refresh()

    assert coordinator.last_update_success
    assert coordinator.periods_unavailable
    assert coordinator.get_sensor_value("account.balance") == 123.45
    assert coordinator.get_sensor_value("contract.cp_current_bill") is None
    contract.refresh_outages.assert_awaited()
    warnings = [r for r in caplog.records if "not available yet" in r.getMessage()]
    assert len(warnings) == 1
    assert "2026-09-23" in warnings[0].getMessage()


async def test_new_contract_periods_retried_hourly_until_available(
    coordinator: HydroQcDataCoordinator,
    contract: MagicMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Refreshes within the hour skip the call, the next one retries and clears the state."""
    caplog.set_level(logging.WARNING)

    await coordinator.async_refresh()
    freezer.tick(datetime.timedelta(minutes=30))
    await coordinator.async_refresh()

    assert contract.get_periods_info.await_count == 1
    assert len([r for r in caplog.records if "not available yet" in r.getMessage()]) == 1

    contract.get_periods_info = AsyncMock(return_value=[{}])
    freezer.tick(datetime.timedelta(minutes=31))
    await coordinator.async_refresh()

    contract.get_periods_info.assert_awaited_once()
    assert coordinator.last_update_success
    assert not coordinator.periods_unavailable
    assert coordinator.get_sensor_value("contract.cp_current_bill") == 45.67


async def test_new_contract_skips_consumption_sync(
    coordinator: HydroQcDataCoordinator,
    contract: MagicMock,
) -> None:
    """Hourly consumption is refused too, the sync waits and keeps its initial run."""
    await coordinator.async_refresh()

    with patch.object(coordinator, "async_fetch_hourly_consumption") as fetch:
        await coordinator._async_regular_consumption_sync()

    fetch.assert_not_called()
    assert not coordinator._initial_sync_done


async def test_old_contract_periods_error_still_fails(
    coordinator: HydroQcDataCoordinator,
    contract: MagicMock,
) -> None:
    """Past the grace period a 400 is a real error."""
    contract.start_date = datetime.date(2026, 6, 1)

    await coordinator.async_refresh()

    assert not coordinator.last_update_success
    assert not coordinator.periods_unavailable


async def test_new_contract_other_http_error_still_fails(
    coordinator: HydroQcDataCoordinator,
    contract: MagicMock,
) -> None:
    """Only the 400 answer is tolerated for a recent contract."""
    contract.get_periods_info = AsyncMock(side_effect=_periods_error(500))

    await coordinator.async_refresh()

    assert not coordinator.last_update_success
    assert not coordinator.periods_unavailable
