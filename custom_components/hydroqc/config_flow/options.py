"""Options flow for Hydro-Québec integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.data_entry_flow import section
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from ..const import (
    AUTH_CLIENTS,
    CONF_AUTH_CLIENT,
    CONF_BILLING_DURATION_ENTITY,
    CONF_CALENDAR_ENTITY_ID,
    CONF_ENABLE_CONSUMPTION_SYNC,
    CONF_PREHEAT_DURATION,
    CONF_RATE,
    CONF_RATE_OPTION,
    DEFAULT_AUTH_CLIENT,
    DEFAULT_PREHEAT_DURATION,
    SECTION_ADVANCED,
)


class HydroQcOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Hydro-Québec integration."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Check if rate supports calendar configuration
            rate = self.config_entry.data.get(CONF_RATE, "")
            rate_option = self.config_entry.data.get(CONF_RATE_OPTION, "")
            rate_with_option = f"{rate}{rate_option}"
            supports_calendar = rate_with_option in ["DPC", "DCPC"]

            # Validate calendar for DPC/DCPC rates
            if supports_calendar:
                calendar_id = user_input.get(CONF_CALENDAR_ENTITY_ID, "").strip()
                if not calendar_id:
                    errors["base"] = "calendar_required"
                elif not self.hass.states.get(calendar_id):
                    errors[CONF_CALENDAR_ENTITY_ID] = "calendar_not_found"

            if not errors:
                # Sections nest their fields: store them flat like the other options
                data = dict(user_input)
                data.update(data.pop(SECTION_ADVANCED, {}))
                return self.async_create_entry(title="", data=data)

        # Check if rate supports calendar configuration
        rate = self.config_entry.data.get(CONF_RATE, "")
        rate_option = self.config_entry.data.get(CONF_RATE_OPTION, "")
        rate_with_option = f"{rate}{rate_option}"
        supports_calendar = rate_with_option in ["DPC", "DCPC"]
        is_portal_mode = self.config_entry.data.get("auth_mode", "portal") == "portal"
        is_tarif_d = rate in ["D"] and is_portal_mode

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

        # Add billing duration entity picker for Tarif D/DCPC (optional)
        if is_tarif_d or rate_with_option == "DCPC":
            current_billing_entity = self.config_entry.options.get(
                CONF_BILLING_DURATION_ENTITY,
                self.config_entry.data.get(CONF_BILLING_DURATION_ENTITY, ""),
            )
            # A suggested value, not a default: the entity selector rejects the empty
            # string, so a default of "" would make the form fail to save while no
            # sensor is chosen. Left empty, the key is simply absent from the options.
            schema_dict[
                vol.Optional(
                    CONF_BILLING_DURATION_ENTITY,
                    description={"suggested_value": current_billing_entity or None},
                )
            ] = EntitySelector(EntitySelectorConfig(domain="sensor"))

        # Add calendar options for DPC/DCPC rates (required)
        if supports_calendar:
            current_calendar = self.config_entry.options.get(
                CONF_CALENDAR_ENTITY_ID,
                self.config_entry.data.get(CONF_CALENDAR_ENTITY_ID, ""),
            )
            # Calendar is required for DPC/DCPC rates
            if current_calendar:
                schema_dict[vol.Required(CONF_CALENDAR_ENTITY_ID, default=current_calendar)] = (
                    EntitySelector(EntitySelectorConfig(domain="calendar"))
                )
            else:
                schema_dict[vol.Required(CONF_CALENDAR_ENTITY_ID)] = EntitySelector(
                    EntitySelectorConfig(domain="calendar")
                )

        if is_portal_mode:
            schema_dict[vol.Required(SECTION_ADVANCED)] = section(
                vol.Schema(
                    {
                        vol.Required(
                            CONF_AUTH_CLIENT,
                            default=self.config_entry.options.get(
                                CONF_AUTH_CLIENT, DEFAULT_AUTH_CLIENT
                            ),
                        ): SelectSelector(
                            SelectSelectorConfig(
                                options=AUTH_CLIENTS,
                                translation_key=CONF_AUTH_CLIENT,
                                mode=SelectSelectorMode.LIST,
                            )
                        ),
                    }
                ),
                {"collapsed": True},
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )
