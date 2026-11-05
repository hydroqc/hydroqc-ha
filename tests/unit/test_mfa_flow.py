"""Unit tests for the e-mail verification (MFA) step of the config flow."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydroqc.const import (
    AUTH_MODE_PORTAL,
    CONF_AUTH_MODE,
    CONF_CONTRACT_NAME,
    CONF_MFA_CODE,
    DOMAIN,
)
from custom_components.hydroqc.session import async_load_session, take_pending_session


class HydroQcMFAResult:
    """Stand-in for the wrapper ``LoginStatus`` enum value."""

    def __init__(self, name: str, value: str) -> None:
        self.name = name
        self.value = value


MFA_REQUIRED = HydroQcMFAResult("MFA_REQUIRED", "mfa_required")
SUCCESS = HydroQcMFAResult("SUCCESS", "success")


class HydroQcMFAInvalidCodeError(Exception):
    """Same class name as the wrapper error, without importing it."""


class HydroQcMFAExpiredError(Exception):
    """Same class name as the wrapper error, without importing it."""


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


async def _start_account_flow(hass: HomeAssistant, mock_webuser: MagicMock) -> dict:
    """Go through the first two steps of the setup flow."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_AUTH_MODE: AUTH_MODE_PORTAL}
    )
    assert result["step_id"] == "account"

    with patch("custom_components.hydroqc.config_flow.base.WebUser", return_value=mock_webuser):
        return await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "test@example.com",
                CONF_PASSWORD: "test_password",
                CONF_CONTRACT_NAME: "Home",
            },
        )


async def test_setup_asks_for_the_verification_code(
    hass: HomeAssistant,
    mock_webuser: MagicMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """A login asking for a code shows the verification step, not an error."""
    mock_webuser.login = AsyncMock(return_value=MFA_REQUIRED)

    result = await _start_account_flow(hass, mock_webuser)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "mfa"
    assert result["errors"] in (None, {})
    assert result["description_placeholders"] == {"email": "test@example.com"}

    mock_webuser.submit_mfa_code = AsyncMock(return_value=SUCCESS)
    with patch("custom_components.hydroqc.config_flow.base.WebUser", return_value=mock_webuser):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_MFA_CODE: "123456"}
        )

    mock_webuser.submit_mfa_code.assert_awaited_once_with("123456")
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "select_contract"
    # The temporary client is closed once the login is complete.
    mock_webuser.close_session.assert_awaited()


async def test_initial_setup_persists_the_session(
    hass: HomeAssistant,
    mock_webuser: MagicMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """The session obtained during setup is reused by the new entry."""
    mock_webuser.login = AsyncMock(return_value=MFA_REQUIRED)
    mock_webuser.submit_mfa_code = AsyncMock(return_value=SUCCESS)
    mock_webuser.export_session_state = MagicMock(
        return_value={"refresh_token": "setup-token", "cookies": []}
    )

    result = await _start_account_flow(hass, mock_webuser)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MFA_CODE: "123456"}
    )
    assert result["step_id"] == "select_contract"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"contract": "test_contract_id"}
    )
    assert result["step_id"] == "import_history"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    # The entry does not exist while the code is entered: the flow stages the
    # session under the contract id for the coordinator to adopt.
    state = take_pending_session(hass, "test_contract_id")
    assert state is not None
    assert state["refresh_token"] == "setup-token"


async def test_empty_code_requests_a_new_one(
    hass: HomeAssistant,
    mock_webuser: MagicMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """An empty field asks the portal to send another code."""
    mock_webuser.login = AsyncMock(return_value=MFA_REQUIRED)

    result = await _start_account_flow(hass, mock_webuser)
    assert result["step_id"] == "mfa"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MFA_CODE: "   "}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "mfa"
    assert result["errors"] == {"base": "mfa_code_resent"}
    mock_webuser.request_mfa_code.assert_awaited_once()
    mock_webuser.submit_mfa_code.assert_not_awaited()


async def test_refused_code_keeps_the_step_open(
    hass: HomeAssistant,
    mock_webuser: MagicMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """A refused code is reported without restarting the login."""
    mock_webuser.login = AsyncMock(return_value=MFA_REQUIRED)
    result = await _start_account_flow(hass, mock_webuser)

    mock_webuser.submit_mfa_code = AsyncMock(side_effect=HydroQcMFAInvalidCodeError())
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MFA_CODE: "000000"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "mfa"
    assert result["errors"] == {"base": "invalid_mfa_code"}


async def test_account_error_after_code_returns_to_the_login_step(
    hass: HomeAssistant,
    mock_webuser: MagicMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """A code accepted by the portal is not asked again when reading fails."""
    mock_webuser.login = AsyncMock(return_value=MFA_REQUIRED)
    result = await _start_account_flow(hass, mock_webuser)

    mock_webuser.submit_mfa_code = AsyncMock(return_value=SUCCESS)
    mock_webuser.get_info = AsyncMock(side_effect=RuntimeError("boom"))
    with patch("custom_components.hydroqc.config_flow.base.WebUser", return_value=mock_webuser):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_MFA_CODE: "123456"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "account"
    assert result["errors"] == {"base": "cannot_connect"}
    mock_webuser.request_mfa_code.assert_not_awaited()
    mock_webuser.close_session.assert_awaited()


async def test_expired_step_requests_a_new_code(
    hass: HomeAssistant,
    mock_webuser: MagicMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """An expired verification step is restarted and a new code is sent."""
    mock_webuser.login = AsyncMock(return_value=MFA_REQUIRED)
    result = await _start_account_flow(hass, mock_webuser)

    mock_webuser.submit_mfa_code = AsyncMock(side_effect=HydroQcMFAExpiredError())
    with patch("custom_components.hydroqc.config_flow.base.WebUser", return_value=mock_webuser):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_MFA_CODE: "123456"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "mfa"
    assert result["errors"] == {"base": "mfa_code_resent"}
    assert mock_webuser.login.await_count == 2


async def test_reauth_persists_the_new_session(
    hass: HomeAssistant,
    hass_storage: dict,
    mock_config_entry: MockConfigEntry,
    mock_webuser: MagicMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """The session obtained during reauthentication replaces the expired one."""
    mock_config_entry.add_to_hass(hass)
    mock_webuser.login = AsyncMock(return_value=MFA_REQUIRED)
    mock_webuser.submit_mfa_code = AsyncMock(return_value=SUCCESS)
    mock_webuser.export_session_state = MagicMock(
        return_value={"refresh_token": "reauth-token", "cookies": []}
    )

    with patch("custom_components.hydroqc.config_flow.base.WebUser", return_value=mock_webuser):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_REAUTH, "entry_id": mock_config_entry.entry_id},
            data=mock_config_entry.data,
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "new_password"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_MFA_CODE: "123456"}
        )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    state = await async_load_session(hass, mock_config_entry)
    assert state is not None
    assert state["refresh_token"] == "reauth-token"


async def test_reauth_asks_for_the_code_and_stores_the_password(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_webuser: MagicMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """Reauthentication supports the verification step too."""
    mock_config_entry.add_to_hass(hass)
    mock_webuser.login = AsyncMock(return_value=MFA_REQUIRED)
    mock_webuser.submit_mfa_code = AsyncMock(return_value=SUCCESS)

    with patch("custom_components.hydroqc.config_flow.base.WebUser", return_value=mock_webuser):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_REAUTH, "entry_id": mock_config_entry.entry_id},
            data=mock_config_entry.data,
        )
        assert result["step_id"] == "reauth_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "new_password"}
        )
        assert result["step_id"] == "mfa"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_MFA_CODE: "123456"}
        )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_PASSWORD] == "new_password"
