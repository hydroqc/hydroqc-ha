"""The IPv4-only session created for Force IPv4 is closed by its owner.

The wrapper never closes a session it did not create, so the config flow and
the coordinator have to close the one they hand it, or Home Assistant logs
"Unclosed client session" / "Unclosed connector" after each login and reload.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import hydroqc
import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydroqc.const import (
    AUTH_MODE_PORTAL,
    CONF_AUTH_MODE,
    CONF_CONTRACT_NAME,
    CONF_FORCE_IPV4,
)
from custom_components.hydroqc.coordinator import HydroQcDataCoordinator


class _MFARequired:
    """Stand-in for the wrapper ``LoginStatus.MFA_REQUIRED`` value."""

    name = "MFA_REQUIRED"
    value = "mfa_required"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let the flow manager load the hydroqc custom integration."""


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Keep the entry setup away from the portal."""
    with (
        patch("custom_components.hydroqc.async_setup_entry", return_value=True) as setup,
        patch("custom_components.hydroqc.async_unload_entry", return_value=True),
    ):
        yield setup


async def _login(
    hass: HomeAssistant, mock_webuser: MagicMock, force_ipv4: bool
) -> tuple[dict[str, Any], list[Any]]:
    """Run the setup flow up to the login, return the result and the sessions handed out."""
    sessions: list[Any] = []

    def make_webuser(*_args: Any, **kwargs: Any) -> MagicMock:
        sessions.append(kwargs.get("session"))
        return mock_webuser

    result = await hass.config_entries.flow.async_init("hydroqc", context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_AUTH_MODE: AUTH_MODE_PORTAL, CONF_FORCE_IPV4: force_ipv4}
    )
    with patch("custom_components.hydroqc.config_flow.base.WebUser", side_effect=make_webuser):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "test@example.com",
                CONF_PASSWORD: "test_password",
                CONF_CONTRACT_NAME: "Home",
            },
        )
    return result, sessions


async def test_failed_login_closes_the_ipv4_session(
    hass: HomeAssistant,
    mock_webuser: MagicMock,
    mock_setup_entry: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Regression: a login rejected with an HTTP error left the session open."""
    mock_webuser.login = AsyncMock(
        side_effect=hydroqc.error.HydroQcHTTPError(
            "Error Fetching https://example.test/authorize - 403", 403
        )
    )
    caplog.set_level("DEBUG", logger="custom_components.hydroqc.config_flow.base")

    result, sessions = await _login(hass, mock_webuser, force_ipv4=True)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert len(sessions) == 1
    assert isinstance(sessions[0], aiohttp.ClientSession)
    assert sessions[0].closed
    # The URL and status the wrapper does not log are now in the debug log
    assert "https://example.test/authorize - 403" in caplog.text


async def test_portal_offline_closes_the_ipv4_session(
    hass: HomeAssistant, mock_webuser: MagicMock, mock_setup_entry: AsyncMock
) -> None:
    mock_webuser.check_hq_portal_status = AsyncMock(return_value=False)

    result, sessions = await _login(hass, mock_webuser, force_ipv4=True)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]
    assert sessions[0].closed


async def test_successful_login_closes_the_ipv4_session(
    hass: HomeAssistant, mock_webuser: MagicMock, mock_setup_entry: AsyncMock
) -> None:
    result, sessions = await _login(hass, mock_webuser, force_ipv4=True)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "select_contract"
    assert sessions[0].closed


async def test_session_stays_open_for_the_code_then_closes_when_abandoned(
    hass: HomeAssistant, mock_webuser: MagicMock, mock_setup_entry: AsyncMock
) -> None:
    """The verification step needs the live session; closing the dialog releases it."""
    mock_webuser.login = AsyncMock(return_value=_MFARequired())

    result, sessions = await _login(hass, mock_webuser, force_ipv4=True)

    assert result["step_id"] == "mfa"
    assert not sessions[0].closed

    hass.config_entries.flow.async_abort(result["flow_id"])
    await hass.async_block_till_done()

    assert sessions[0].closed
    mock_webuser.close_session.assert_awaited()


async def test_retry_closes_the_previous_session(
    hass: HomeAssistant, mock_webuser: MagicMock, mock_setup_entry: AsyncMock
) -> None:
    """Each attempt gets a fresh session; the previous one is not left behind."""
    mock_webuser.login = AsyncMock(return_value=_MFARequired())
    result, sessions = await _login(hass, mock_webuser, force_ipv4=True)
    assert result["step_id"] == "mfa"

    flow = hass.config_entries.flow._progress[result["flow_id"]]
    with patch(
        "custom_components.hydroqc.config_flow.base.WebUser",
        side_effect=lambda *_a, **kw: sessions.append(kw.get("session")) or mock_webuser,
    ):
        await flow._async_start_portal_login()

    assert len(sessions) == 2
    assert sessions[0].closed
    assert not sessions[1].closed
    await flow._async_close_webuser()
    assert sessions[1].closed


async def test_without_force_ipv4_no_session_is_created(
    hass: HomeAssistant, mock_webuser: MagicMock, mock_setup_entry: AsyncMock
) -> None:
    result, sessions = await _login(hass, mock_webuser, force_ipv4=False)

    assert result["step_id"] == "select_contract"
    assert sessions == [None]


async def test_coordinator_shutdown_closes_the_ipv4_session(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_webuser: MagicMock
) -> None:
    """Regression: every reload (an options change, for one) leaked a session."""
    entry = MockConfigEntry(
        domain=mock_config_entry.domain,
        title=mock_config_entry.title,
        data={**mock_config_entry.data, CONF_FORCE_IPV4: True},
        unique_id=mock_config_entry.unique_id,
    )
    entry.add_to_hass(hass)
    sessions: list[Any] = []

    def make_webuser(*_args: Any, **kwargs: Any) -> MagicMock:
        sessions.append(kwargs.get("session"))
        return mock_webuser

    public_client = MagicMock()
    public_client.close_session = AsyncMock()
    with (
        patch("custom_components.hydroqc.coordinator.base.WebUser", side_effect=make_webuser),
        patch(
            "custom_components.hydroqc.coordinator.base.PublicDataClient",
            return_value=public_client,
        ),
    ):
        coordinator = HydroQcDataCoordinator(hass, entry)

    assert isinstance(sessions[0], aiohttp.ClientSession)
    assert not sessions[0].closed

    await coordinator.async_shutdown()

    assert sessions[0].closed
    mock_webuser.close_session.assert_awaited()
    public_client.close_session.assert_awaited()
