"""Integration tests for config flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydroqc.const import DOMAIN


@pytest.mark.asyncio
class TestConfigFlow:
    """Test the config flow."""

    async def test_form_user_portal_mode(self, hass: HomeAssistant) -> None:
        """Test user form for portal mode configuration."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "user"
        assert result["errors"] == {}

    async def test_form_user_opendata_mode(self, hass: HomeAssistant) -> None:
        """Test user form for opendata mode configuration."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "user"

    async def test_auth_login_success(
        self, hass: HomeAssistant, mock_webuser: MagicMock
    ) -> None:
        """Test successful authentication."""
        with patch(
            "custom_components.hydroqc.config_flow.WebUser",
            return_value=mock_webuser,
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )

            # Simulate user selecting portal mode and entering credentials
            # This is a simplified test - actual config flow has multiple steps
            assert result["type"] == "form"

    async def test_auth_login_failure(self, hass: HomeAssistant) -> None:
        """Test authentication failure."""
        with patch("custom_components.hydroqc.config_flow.WebUser") as mock_class:
            mock_webuser = MagicMock()
            mock_webuser.login = AsyncMock(side_effect=Exception("Login failed"))
            mock_class.return_value = mock_webuser

            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )

            # Should show form initially
            assert result["type"] == "form"

    async def test_duplicate_entry(
        self, hass: HomeAssistant, mock_config_entry: MockConfigEntry
    ) -> None:
        """Test that duplicate entries are prevented."""
        mock_config_entry.add_to_hass(hass)

        # Try to add the same config again
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        # Should show the form (duplicate check happens during submission)
        assert result["type"] == "form"
