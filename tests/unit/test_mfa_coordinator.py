"""Unit tests for the e-mail verification (MFA) handling in the coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.hydroqc.coordinator.base as coordinator_module
from custom_components.hydroqc.coordinator import HydroQcDataCoordinator
from custom_components.hydroqc.session import async_load_session


class HydroQcMFAResult:
    """Stand-in for the wrapper ``LoginStatus`` enum value."""

    def __init__(self, name: str, value: str) -> None:
        self.name = name
        self.value = value


MFA_REQUIRED = HydroQcMFAResult("MFA_REQUIRED", "mfa_required")
SUCCESS = HydroQcMFAResult("SUCCESS", "success")


class HydroQcMFARequiredError(Exception):
    """Same class name as the wrapper error, without importing it."""


def _build_coordinator(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    webuser: MagicMock,
    public_client: MagicMock,
) -> HydroQcDataCoordinator:
    """Create a coordinator wired to the mocked clients."""
    with (
        patch("custom_components.hydroqc.coordinator.base.WebUser", return_value=webuser),
        patch(
            "custom_components.hydroqc.coordinator.base.PublicDataClient",
            return_value=public_client,
        ),
    ):
        return HydroQcDataCoordinator(hass, entry)


async def test_login_requiring_a_code_raises_auth_failed(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_webuser: MagicMock,
    mock_public_client: MagicMock,
) -> None:
    """A background login landing on the code step asks for a reauthentication."""
    mock_config_entry.add_to_hass(hass)
    mock_webuser.login = AsyncMock(return_value=MFA_REQUIRED)
    coordinator = _build_coordinator(hass, mock_config_entry, mock_webuser, mock_public_client)

    with pytest.raises(ConfigEntryAuthFailed, match="verification code"):
        await coordinator._async_login()


async def test_mfa_error_during_update_raises_auth_failed(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_webuser: MagicMock,
    mock_public_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wrapper exception is mapped to an authentication failure."""
    mock_config_entry.add_to_hass(hass)
    mock_webuser.session_expired = True
    mock_webuser.login = AsyncMock(side_effect=HydroQcMFARequiredError("code needed"))
    # The installed wrapper predates the MFA support: inject the exception class
    # the same way a newer release exposes it.
    monkeypatch.setattr(coordinator_module, "MFA_ERRORS", (HydroQcMFARequiredError,))
    coordinator = _build_coordinator(hass, mock_config_entry, mock_webuser, mock_public_client)

    with pytest.raises(ConfigEntryAuthFailed, match="verification code"):
        await coordinator._async_update_data()


async def test_stored_session_is_reused_on_restart(
    hass: HomeAssistant,
    hass_storage: dict,
    mock_config_entry: MockConfigEntry,
    mock_webuser: MagicMock,
    mock_public_client: MagicMock,
) -> None:
    """A restored session is tried before asking for the password again."""
    mock_config_entry.add_to_hass(hass)
    mock_webuser.try_silent_login = AsyncMock(return_value=SUCCESS)
    hass_storage[f"hydroqc.{mock_config_entry.entry_id}.session"] = {
        "version": 1,
        "key": f"hydroqc.{mock_config_entry.entry_id}.session",
        "data": {"refresh_token": "stored", "cookies": []},
    }
    coordinator = _build_coordinator(hass, mock_config_entry, mock_webuser, mock_public_client)

    await coordinator.async_restore_session()

    assert coordinator._session_restored is True
    assert mock_webuser.import_session_state.call_args[0][0]["refresh_token"] == "stored"

    await coordinator._async_login()

    mock_webuser.try_silent_login.assert_awaited_once()
    mock_webuser.login.assert_not_awaited()


async def test_session_is_persisted_after_a_refresh(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_webuser: MagicMock,
    mock_public_client: MagicMock,
) -> None:
    """The refresh token and cookies are stored for the next start."""
    mock_config_entry.add_to_hass(hass)
    mock_webuser.export_session_state = MagicMock(
        return_value={"refresh_token": "fresh", "cookies": [{"key": "x-ms-cpim-sso"}]}
    )
    coordinator = _build_coordinator(hass, mock_config_entry, mock_webuser, mock_public_client)

    await coordinator._async_persist_session()

    state = await async_load_session(hass, mock_config_entry)
    assert state is not None
    assert state["refresh_token"] == "fresh"
    assert state["cookies"] == [{"key": "x-ms-cpim-sso"}]


async def test_empty_session_is_not_persisted(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_webuser: MagicMock,
    mock_public_client: MagicMock,
) -> None:
    """A login that produced no token must not erase a stored session."""
    mock_config_entry.add_to_hass(hass)
    mock_webuser.export_session_state = MagicMock(
        return_value={"refresh_token": None, "cookies": []}
    )
    coordinator = _build_coordinator(hass, mock_config_entry, mock_webuser, mock_public_client)

    await coordinator._async_persist_session()

    assert await async_load_session(hass, mock_config_entry) is None
