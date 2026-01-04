"""Options flow for Hydro-Québec integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from ..const import (
    CONF_CALENDAR_ENTITY_ID,
    CONF_ENABLE_CONSUMPTION_SYNC,
    CONF_PREHEAT_DURATION,
    CONF_RATE,
    CONF_RATE_OPTION,
    DEFAULT_PREHEAT_DURATION,
)


class HydroQcOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Hydro-Québec integration."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            # Filter out empty calendar entity ID (calendar is optional)
            if CONF_CALENDAR_ENTITY_ID in user_input:
                calendar_id = user_input.get(CONF_CALENDAR_ENTITY_ID, "").strip()
                if not calendar_id:
                    user_input.pop(CONF_CALENDAR_ENTITY_ID, None)
            return self.async_create_entry(title="", data=user_input)

        # Check if rate supports calendar configuration
        rate = self.config_entry.data.get(CONF_RATE, "")
        rate_option = self.config_entry.data.get(CONF_RATE_OPTION, "")
        rate_with_option = f"{rate}{rate_option}"
        supports_calendar = rate_with_option in ["DPC", "DCPC"]
        is_portal_mode = self.config_entry.data.get("auth_mode", "portal") == "portal"

        # Build schema based on rate capabilities
        schema_dict: dict[Any, Any] = {
            vol.Optional(
                CONF_PREHEAT_DURATION,
                default=self.config_entry.options.get(
                    CONF_PREHEAT_DURATION,
                    self.config_entry.data.get(CONF_PREHEAT_DURATION, DEFAULT_PREHEAT_DURATION),
                ),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0,
                    max=240,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="minutes",
                )
            ),
        }

        # Add consumption sync option for Portal mode only
        if is_portal_mode:
            schema_dict[
                vol.Optional(
                    CONF_ENABLE_CONSUMPTION_SYNC,
                    default=self.config_entry.options.get(
                        CONF_ENABLE_CONSUMPTION_SYNC,
                        self.config_entry.data.get(CONF_ENABLE_CONSUMPTION_SYNC, True),
                    ),
                )
            ] = bool

        # Add calendar options for DPC/DCPC rates
        if supports_calendar:
            current_calendar = self.config_entry.options.get(
                CONF_CALENDAR_ENTITY_ID,
                self.config_entry.data.get(CONF_CALENDAR_ENTITY_ID, ""),
            )
            # Only set default if calendar is actually configured (not empty)
            # This prevents EntitySelector validation errors with empty strings
            if current_calendar:
                schema_dict[vol.Optional(CONF_CALENDAR_ENTITY_ID, default=current_calendar)] = (
                    EntitySelector(EntitySelectorConfig(domain="calendar"))
                )
            else:
                schema_dict[vol.Optional(CONF_CALENDAR_ENTITY_ID)] = EntitySelector(
                    EntitySelectorConfig(domain="calendar")
                )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_dict),
        )
