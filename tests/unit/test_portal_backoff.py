"""Short, offline regressions for the shared portal outage cooldown."""

import datetime
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import hydroqc
import pytest
from aiohttp import ClientResponseError
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydroqc.coordinator import HydroQcDataCoordinator


@pytest.fixture
def coordinator(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_webuser: MagicMock,
    mock_public_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> Generator[HydroQcDataCoordinator]:
    """Use existing portal fixtures, with deterministic jitter and no real requests."""
    freezer.move_to("2026-01-15 12:00:00+00:00")
    mock_config_entry.add_to_hass(hass)
    with (
        patch("custom_components.hydroqc.coordinator.base.WebUser", return_value=mock_webuser),
        patch(
            "custom_components.hydroqc.coordinator.base.PublicDataClient",
            return_value=mock_public_client,
        ),
        patch("custom_components.hydroqc.coordinator.base.async_track_time_change"),
        patch(
            "custom_components.hydroqc.coordinator.base.random.uniform",
            side_effect=lambda low, high: low,
        ),
    ):
        yield HydroQcDataCoordinator(hass, mock_config_entry)


async def test_progressive_backoff_shared_with_opendata_and_consumption(
    coordinator: HydroQcDataCoordinator,
    mock_webuser: MagicMock,
    mock_public_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Offline status is checked once per cooldown, regardless of automatic caller."""
    mock_webuser.check_hq_portal_status.return_value = False
    for attempts, minutes in enumerate((15, 30, 60, 60), start=1):
        await coordinator._async_update_data()
        assert coordinator._last_portal_update is None
        assert not coordinator._should_update_portal()
        deadline = coordinator._portal_retry_after
        assert deadline == datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=minutes)

        with patch.object(
            coordinator, "async_request_refresh", side_effect=coordinator._async_update_data
        ):
            await coordinator._async_scheduled_opendata_update(datetime.datetime.now(datetime.UTC))
        await coordinator._async_update_data()
        await coordinator._async_regular_consumption_sync()
        assert mock_webuser.check_hq_portal_status.await_count == attempts
        mock_webuser.login.assert_not_awaited()
        assert mock_public_client.fetch_peak_data.await_count >= attempts * 2
        freezer.move_to(deadline)


@pytest.mark.parametrize("error", [hydroqc.error.HydroQcHTTPError("Down", 503), TimeoutError()])
async def test_consumption_failure_stops_date_loop_and_requires_refresh_first(
    coordinator: HydroQcDataCoordinator,
    mock_webuser: MagicMock,
    freezer: FrozenDateTimeFactory,
    error: Exception,
) -> None:
    """The first failed day stops network traffic; success resets and staggers recovery."""
    await coordinator._async_update_data()
    contract = coordinator._contract
    contract.get_hourly_consumption.side_effect = error
    today = datetime.date.today()
    with pytest.raises(UpdateFailed):
        await coordinator.async_fetch_hourly_consumption(today - datetime.timedelta(days=30), today)
    contract.get_hourly_consumption.assert_awaited_once()
    last_success = coordinator._last_portal_update
    await coordinator._async_update_data()
    assert coordinator._last_portal_update == last_success

    freezer.move_to(coordinator._portal_retry_after)
    with pytest.raises(UpdateFailed):
        await coordinator.async_fetch_hourly_consumption(today, today)
    contract.get_hourly_consumption.assert_awaited_once()
    await coordinator._async_update_data()
    assert coordinator._portal_failures == 0
    assert coordinator._portal_retry_after is None
    assert coordinator._consumption_resume_at == datetime.datetime.now(
        datetime.UTC
    ) + datetime.timedelta(seconds=30)
    with patch(
        "custom_components.hydroqc.coordinator.base.asyncio.sleep", new_callable=AsyncMock
    ) as sleep:
        async with coordinator._async_portal_request(consumption=True):
            pass
    sleep.assert_awaited_once_with(30)
    assert mock_webuser.get_info.await_count == 2


@pytest.mark.parametrize("retry_after", ["7200", "Thu, 15 Jan 2026 14:00:00 GMT"])
async def test_retry_after_is_a_lower_bound(
    coordinator: HydroQcDataCoordinator,
    mock_webuser: MagicMock,
    retry_after: str,
) -> None:
    """Honor both standard Retry-After formats when headers are accessible."""
    mock_webuser.get_info.side_effect = ClientResponseError(
        MagicMock(), (), status=429, headers={"Retry-After": retry_after}
    )
    with (
        patch("custom_components.hydroqc.coordinator.base.random.uniform", return_value=17),
        pytest.raises(UpdateFailed),
    ):
        await coordinator._async_update_data()
    assert coordinator._portal_retry_after == datetime.datetime.now(
        datetime.UTC
    ) + datetime.timedelta(seconds=7217)


async def test_auth_failure_is_not_retried_or_masked(
    coordinator: HydroQcDataCoordinator,
    mock_webuser: MagicMock,
) -> None:
    """Refused credentials stay an auth failure, including later automatic calls."""
    mock_webuser.session_expired = True
    mock_webuser.login.return_value = False
    for _ in range(2):
        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator._async_update_data()
    await coordinator._async_regular_consumption_sync()
    mock_webuser.login.assert_awaited_once()
    assert coordinator._portal_retry_after is None


async def test_csv_requests_share_cooldown(
    coordinator: HydroQcDataCoordinator,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Even a historical import cannot bypass a failed hourly-consumption request."""
    await coordinator._async_update_data()
    coordinator._ensure_helper_modules()
    coordinator._portal_backoff(TimeoutError())
    freezer.move_to(coordinator._portal_retry_after)
    await coordinator._history_importer.import_csv_history(60)
    coordinator._contract.get_hourly_energy.assert_not_called()


async def test_unpublished_consumption_is_not_an_outage(
    coordinator: HydroQcDataCoordinator,
) -> None:
    """Keep the wrapper's expected no-data handling, without penalizing the portal."""
    await coordinator._async_update_data()
    coordinator._contract.get_hourly_consumption.side_effect = [
        hydroqc.error.HydroQcHTTPError("No data available for date 2026-01-14"),
        {"results": {"listeDonneesConsoEnergieHoraire": []}},
    ]
    today = datetime.date.today()
    await coordinator.async_fetch_hourly_consumption(today - datetime.timedelta(days=1), today)
    assert coordinator._contract.get_hourly_consumption.await_count == 2
    assert coordinator._portal_retry_after is None


async def test_consumption_auth_failure_reaches_reauth(
    coordinator: HydroQcDataCoordinator,
) -> None:
    """A 401 stops the consumption loop and requests reauth instead of retries."""
    await coordinator._async_update_data()
    coordinator._contract.get_hourly_consumption.side_effect = hydroqc.error.HydroQcHTTPError(
        "Unauthorized", 401
    )
    today = datetime.date.today()
    with (
        patch.object(coordinator.entry, "async_start_reauth") as reauth,
        pytest.raises(ConfigEntryAuthFailed),
    ):
        await coordinator.async_fetch_hourly_consumption(today - datetime.timedelta(days=30), today)
    reauth.assert_called_once()
    coordinator._contract.get_hourly_consumption.assert_awaited_once()
    assert coordinator._portal_retry_after is None
