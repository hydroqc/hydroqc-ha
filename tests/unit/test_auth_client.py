"""Tests for the Hydro-Québec login client option."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydroqc.auth import webuser_auth_kwargs
from custom_components.hydroqc.const import (
    AUTH_CLIENT_MOBILE,
    AUTH_CLIENT_WEB,
    CONF_AUTH_CLIENT,
    CONF_ENABLE_CONSUMPTION_SYNC,
    CONF_PREHEAT_DURATION,
    DOMAIN,
    SECTION_ADVANCED,
)


class _WebUserWithClient:
    def __init__(self, username: str, password: str, auth_client: str = "web") -> None:
        pass


class _WebUserWithoutClient:
    def __init__(self, username: str, password: str) -> None:
        pass


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let the flow manager load the hydroqc custom integration."""


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Keep reloads away from the portal."""
    with (
        patch("custom_components.hydroqc.async_setup_entry", return_value=True) as setup,
        patch("custom_components.hydroqc.async_unload_entry", return_value=True),
    ):
        yield setup


def test_web_client_passes_no_keyword() -> None:
    """The web client keeps the WebUser call unchanged."""
    with patch("custom_components.hydroqc.auth.WebUser", _WebUserWithClient):
        assert webuser_auth_kwargs({CONF_AUTH_CLIENT: AUTH_CLIENT_WEB}) == {}


@pytest.mark.parametrize("options", [{}, {CONF_AUTH_CLIENT: AUTH_CLIENT_MOBILE}])
def test_mobile_client_is_passed_to_wrapper(options: dict[str, str]) -> None:
    """The mobile client, also the default, reaches a wrapper that knows auth_client."""
    with patch("custom_components.hydroqc.auth.WebUser", _WebUserWithClient):
        assert webuser_auth_kwargs(options) == {"auth_client": AUTH_CLIENT_MOBILE}


def test_mobile_client_falls_back_on_old_wrapper() -> None:
    """An older wrapper keeps working with the web client."""
    with patch("custom_components.hydroqc.auth.WebUser", _WebUserWithoutClient):
        assert webuser_auth_kwargs({CONF_AUTH_CLIENT: AUTH_CLIENT_MOBILE}) == {}


async def test_options_store_advanced_section_flat(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_setup_entry: AsyncMock,
) -> None:
    """The login client is shown in the advanced section and stored flat."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert SECTION_ADVANCED in result["data_schema"].schema

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_PREHEAT_DURATION: 120,
            CONF_ENABLE_CONSUMPTION_SYNC: True,
            SECTION_ADVANCED: {CONF_AUTH_CLIENT: AUTH_CLIENT_WEB},
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options[CONF_AUTH_CLIENT] == AUTH_CLIENT_WEB
    assert SECTION_ADVANCED not in mock_config_entry.options


async def test_reconfigure_logs_in_with_entry_client(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_webuser: MagicMock,
    mock_setup_entry: AsyncMock,
) -> None:
    """A reconfigure login uses the client chosen in the entry options."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry, options={CONF_AUTH_CLIENT: AUTH_CLIENT_MOBILE}
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": mock_config_entry.entry_id}
    )
    with (
        patch("custom_components.hydroqc.auth.WebUser", _WebUserWithClient),
        patch(
            "custom_components.hydroqc.config_flow.base.WebUser", return_value=mock_webuser
        ) as webuser_cls,
    ):
        await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "test@example.com", CONF_PASSWORD: "test_password"},
        )

    assert webuser_cls.call_args.kwargs["auth_client"] == AUTH_CLIENT_MOBILE
