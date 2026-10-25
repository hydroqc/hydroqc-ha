"""Unit tests for reauthentication when Hydro-Québec refuses the stored credentials."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import hydroqc
import pytest
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ConfigEntryAuthFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydroqc.const import DOMAIN
from custom_components.hydroqc.coordinator import HydroQcDataCoordinator


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let the flow manager load the hydroqc custom integration."""


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Keep the reload triggered by the reauth flow away from the portal."""
    with (
        patch("custom_components.hydroqc.async_setup_entry", return_value=True) as setup,
        patch("custom_components.hydroqc.async_unload_entry", return_value=True),
    ):
        yield setup


async def _start_reauth(hass: HomeAssistant, entry: MockConfigEntry) -> dict:
    return await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )


async def test_reauth_stores_new_password(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_webuser: MagicMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """A password accepted by the portal replaces the stored one."""
    mock_config_entry.add_to_hass(hass)

    result = await _start_reauth(hass, mock_config_entry)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch("custom_components.hydroqc.config_flow.base.WebUser", return_value=mock_webuser):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "new_password"}
        )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_PASSWORD] == "new_password"


async def test_reauth_refused_password_shows_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_webuser: MagicMock,
) -> None:
    """A refused login keeps the form open and the stored password unchanged."""
    mock_config_entry.add_to_hass(hass)
    mock_webuser.login = AsyncMock(return_value=False)

    result = await _start_reauth(hass, mock_config_entry)
    with patch("custom_components.hydroqc.config_flow.base.WebUser", return_value=mock_webuser):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "wrong_password"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert mock_config_entry.data[CONF_PASSWORD] == "test_password"


@pytest.mark.parametrize(
    "login",
    [
        AsyncMock(return_value=False),
        AsyncMock(side_effect=hydroqc.error.HydroQcHTTPError("Error Fetching", 200)),
    ],
    ids=["login_returns_false", "login_redirect_broken"],
)
async def test_coordinator_refused_login_raises_auth_failed(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_webuser: MagicMock,
    mock_public_client: MagicMock,
    login: AsyncMock,
) -> None:
    """A refused portal login is reported as an authentication failure."""
    mock_config_entry.add_to_hass(hass)
    mock_webuser.session_expired = True
    mock_webuser.login = login

    with (
        patch("custom_components.hydroqc.coordinator.base.WebUser", return_value=mock_webuser),
        patch(
            "custom_components.hydroqc.coordinator.base.PublicDataClient",
            return_value=mock_public_client,
        ),
    ):
        coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator._async_update_data()


async def test_coordinator_portal_error_during_login_is_not_auth_failure(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_webuser: MagicMock,
    mock_public_client: MagicMock,
) -> None:
    """A 5xx during login stays a regular update failure."""
    mock_config_entry.add_to_hass(hass)
    mock_webuser.session_expired = True
    mock_webuser.login = AsyncMock(side_effect=hydroqc.error.HydroQcHTTPError("Down", 503))

    with (
        patch("custom_components.hydroqc.coordinator.base.WebUser", return_value=mock_webuser),
        patch(
            "custom_components.hydroqc.coordinator.base.PublicDataClient",
            return_value=mock_public_client,
        ),
    ):
        coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
        with pytest.raises(Exception) as exc_info:
            await coordinator._async_update_data()
    assert not isinstance(exc_info.value, ConfigEntryAuthFailed)
