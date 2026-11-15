"""Tests for the optional billing duration sensor in the options flow."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydroqc.const import (
    AUTH_MODE_PORTAL,
    CONF_AUTH_MODE,
    CONF_BILLING_DURATION_ENTITY,
    CONF_CONTRACT_NAME,
    CONF_PREHEAT_DURATION,
    CONF_RATE,
    CONF_RATE_OPTION,
    DOMAIN,
    SECTION_ADVANCED,
)

SENSOR = "sensor.billing_period_days"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading the custom integration in every test."""


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Keep the reload triggered by saving options away from the portal."""
    with (
        patch("custom_components.hydroqc.async_setup_entry", return_value=True) as setup,
        patch("custom_components.hydroqc.async_unload_entry", return_value=True),
    ):
        yield setup


def make_entry(rate: str, rate_option: str = "", **options: str) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Test Account",
        data={
            CONF_AUTH_MODE: AUTH_MODE_PORTAL,
            "username": "test@example.com",
            "password": "test_password",
            "customer_id": "c",
            "account_id": "a",
            "contract_id": "contract123",
            CONF_CONTRACT_NAME: "Home",
            CONF_RATE: rate,
            CONF_RATE_OPTION: rate_option,
            CONF_PREHEAT_DURATION: 120,
        },
        options=options,
        unique_id="contract123",
    )


def field_keys(result: dict) -> dict[str, object]:
    """Map each top-level form field name to its voluptuous marker."""
    return {str(marker.schema): marker for marker in result["data_schema"].schema}


FORM_INPUT = {
    CONF_PREHEAT_DURATION: 120,
    "enable_consumption_sync": True,
    SECTION_ADVANCED: {"auth_client": "mobile"},
}


async def test_form_saves_while_no_sensor_is_chosen(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Regression: an empty picker must not make the whole options form invalid."""
    entry = make_entry("D")
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], FORM_INPUT)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_BILLING_DURATION_ENTITY not in entry.options


async def test_chosen_sensor_is_stored(hass: HomeAssistant, mock_setup_entry: AsyncMock) -> None:
    entry = make_entry("D")
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**FORM_INPUT, CONF_BILLING_DURATION_ENTITY: SENSOR}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_BILLING_DURATION_ENTITY] == SENSOR


async def test_saved_sensor_is_prefilled_and_can_be_cleared(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    entry = make_entry("D", **{CONF_BILLING_DURATION_ENTITY: SENSOR})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    marker = field_keys(result)[CONF_BILLING_DURATION_ENTITY]
    assert marker.description == {"suggested_value": SENSOR}

    # Clearing the picker sends nothing: the option goes away, which means
    # "use the 60-day approximation" again
    result = await hass.config_entries.options.async_configure(result["flow_id"], FORM_INPUT)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_BILLING_DURATION_ENTITY not in entry.options


async def test_dcpc_gets_the_picker(hass: HomeAssistant, mock_setup_entry: AsyncMock) -> None:
    """DCPC is rate D plus the CPC option, and uses the same split."""
    entry = make_entry("D", "CPC")
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert CONF_BILLING_DURATION_ENTITY in field_keys(result)


@pytest.mark.parametrize("rate", ["DT", "DPC"])
async def test_other_rates_do_not_get_the_picker(
    hass: HomeAssistant, mock_setup_entry: AsyncMock, rate: str
) -> None:
    entry = make_entry(rate)
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert CONF_BILLING_DURATION_ENTITY not in field_keys(result)
