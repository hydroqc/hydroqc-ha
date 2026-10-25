"""Unit tests for the config flow reconfigure steps."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import hydroqc
import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydroqc.const import (
    CONF_ACCOUNT_ID,
    CONF_CONTRACT_ID,
    CONF_CONTRACT_NAME,
    CONF_CUSTOMER_ID,
    CONF_RATE,
    CONF_RATE_OPTION,
    DOMAIN,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let the flow manager load the hydroqc custom integration."""


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Keep the reload triggered by the reconfigure flow away from the portal."""
    with (
        patch("custom_components.hydroqc.async_setup_entry", return_value=True) as setup,
        patch("custom_components.hydroqc.async_unload_entry", return_value=True),
    ):
        yield setup


@pytest.fixture
def webuser_two_contracts(mock_webuser: MagicMock) -> MagicMock:
    """Portal account holding the current contract and a new one."""
    customer = mock_webuser.customers[0]
    customer.customer_id = "new_customer_id"
    account = customer.accounts[0]
    account.account_id = "new_account_id"

    old_contract = MagicMock(contract_id="contract123", rate="D", rate_option="")
    new_contract = MagicMock(contract_id="contract456", rate="D", rate_option="CPC")
    account.contracts = [old_contract, new_contract]
    return mock_webuser


async def _start_reconfigure(hass: HomeAssistant, entry: MockConfigEntry) -> dict:
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )


async def test_reconfigure_moves_entry_to_new_contract(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    webuser_two_contracts: MagicMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """The entry, its device and its entities follow the newly selected contract."""
    mock_config_entry.add_to_hass(hass)

    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id=mock_config_entry.entry_id,
        identifiers={(DOMAIN, "contract123")},
    )
    ent_reg = er.async_get(hass)
    balance = ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        "contract123_balance",
        config_entry=mock_config_entry,
        device_id=device.id,
        suggested_object_id="hydro_quebec_home_balance",
    )

    result = await _start_reconfigure(hass, mock_config_entry)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    with patch(
        "custom_components.hydroqc.config_flow.base.WebUser",
        return_value=webuser_two_contracts,
    ):
        # Blank password: the stored one must be reused
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: "test@example.com"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure_contract"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"contract": "contract456"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"

    assert mock_config_entry.unique_id == "contract456"
    assert mock_config_entry.title == "Home (DCPC)"
    assert mock_config_entry.data[CONF_CONTRACT_ID] == "contract456"
    assert mock_config_entry.data[CONF_CUSTOMER_ID] == "new_customer_id"
    assert mock_config_entry.data[CONF_ACCOUNT_ID] == "new_account_id"
    assert mock_config_entry.data[CONF_RATE] == "D"
    assert mock_config_entry.data[CONF_RATE_OPTION] == "CPC"
    assert mock_config_entry.data[CONF_CONTRACT_NAME] == "Home"
    assert mock_config_entry.data[CONF_PASSWORD] == "test_password"

    migrated = ent_reg.async_get(balance.entity_id)
    assert migrated is not None
    assert migrated.unique_id == "contract456_balance"
    assert migrated.entity_id == "sensor.hydro_quebec_home_balance"

    migrated_device = dev_reg.async_get(device.id)
    assert migrated_device is not None
    assert migrated_device.identifiers == {(DOMAIN, "contract456")}


async def test_reconfigure_same_contract_updates_password(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    webuser_two_contracts: MagicMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """Keeping the contract only refreshes the credentials."""
    mock_config_entry.add_to_hass(hass)

    result = await _start_reconfigure(hass, mock_config_entry)
    with patch(
        "custom_components.hydroqc.config_flow.base.WebUser",
        return_value=webuser_two_contracts,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "test@example.com", CONF_PASSWORD: "new_password"},
        )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"contract": "contract123"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.unique_id == "contract123"
    assert mock_config_entry.data[CONF_PASSWORD] == "new_password"


async def test_reconfigure_rejects_contract_of_another_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    webuser_two_contracts: MagicMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """A contract already followed by another entry cannot be taken over."""
    mock_config_entry.add_to_hass(hass)
    other = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_CONTRACT_ID: "contract456"},
        unique_id="contract456",
    )
    other.add_to_hass(hass)

    result = await _start_reconfigure(hass, mock_config_entry)
    with patch(
        "custom_components.hydroqc.config_flow.base.WebUser",
        return_value=webuser_two_contracts,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: "test@example.com"}
        )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"contract": "contract456"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert mock_config_entry.unique_id == "contract123"


async def test_reconfigure_invalid_auth_shows_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    webuser_two_contracts: MagicMock,
) -> None:
    """A login failure keeps the user on the credentials form."""
    mock_config_entry.add_to_hass(hass)
    webuser_two_contracts.login = AsyncMock(
        side_effect=hydroqc.error.HydroQcHTTPError("bad credentials")
    )

    result = await _start_reconfigure(hass, mock_config_entry)
    with patch(
        "custom_components.hydroqc.config_flow.base.WebUser",
        return_value=webuser_two_contracts,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: "test@example.com", CONF_PASSWORD: "wrong"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reconfigure_opendata_entry_aborts(
    hass: HomeAssistant,
    mock_config_entry_opendata: MockConfigEntry,
) -> None:
    """OpenData entries have no contract to change."""
    mock_config_entry_opendata.add_to_hass(hass)

    result = await _start_reconfigure(hass, mock_config_entry_opendata)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_portal_only"
