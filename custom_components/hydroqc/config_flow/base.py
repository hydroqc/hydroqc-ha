"""Base config flow for Hydro-Québec integration."""

from __future__ import annotations

import logging
from typing import Any, cast

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

import hydroqc
from hydroqc.webuser import WebUser

from ..const import (
    AUTH_MODE_OPENDATA,
    AUTH_MODE_PORTAL,
    CONF_ACCOUNT_ID,
    CONF_AUTH_MODE,
    CONF_CALENDAR_ENTITY_ID,
    CONF_CONTRACT_ID,
    CONF_CONTRACT_NAME,
    CONF_CUSTOMER_ID,
    CONF_HISTORY_DAYS,
    CONF_PREHEAT_DURATION,
    CONF_RATE,
    CONF_RATE_OPTION,
    DEFAULT_PREHEAT_DURATION,
    DOMAIN,
)
from .helpers import SECTOR_MAPPING, fetch_available_sectors, fetch_offers_for_sector
from .options import HydroQcOptionsFlow

_LOGGER = logging.getLogger(__name__)


class HydroQcConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Hydro-Québec."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._selected_contract: dict[str, Any] | None = None
        self._webuser: WebUser | None = None
        self._contracts: list[dict[str, Any]] = []
        self._auth_mode: str | None = None
        self._username: str | None = None
        self._password: str | None = None
        self._contract_name: str | None = None
        self._available_sectors: list[str] = []
        self._selected_sector: str | None = None
        self._available_rates: list[dict[str, str]] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step - choose auth mode."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_AUTH_MODE): SelectSelector(
                            SelectSelectorConfig(
                                options=cast(
                                    list[SelectOptionDict],
                                    [
                                        {
                                            "value": AUTH_MODE_PORTAL,
                                            "label": "Portal Mode (requires login)",
                                        },
                                        {
                                            "value": AUTH_MODE_OPENDATA,
                                            "label": "OpenData Mode (no login required)",
                                        },
                                    ],
                                ),
                                mode=SelectSelectorMode.LIST,
                            )
                        )
                    }
                ),
            )

        self._auth_mode = user_input[CONF_AUTH_MODE]

        if self._auth_mode == AUTH_MODE_PORTAL:
            return await self.async_step_account()
        return await self.async_step_opendata()

    async def async_step_account(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle portal mode account setup."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]
            self._contract_name = user_input[CONF_CONTRACT_NAME]

            try:
                # Try to login and fetch contracts
                self._webuser = WebUser(
                    self._username,
                    self._password,
                    verify_ssl=True,
                    log_level="INFO",
                    http_log_level="WARNING",
                )
                await self._webuser.login()
                await self._webuser.get_info()
                await self._webuser.fetch_customers_info()

                # Collect all contracts from all customers/accounts
                self._contracts = []
                for customer in self._webuser.customers:
                    await customer.get_info()
                    for account in customer.accounts:
                        for contract in account.contracts:
                            self._contracts.append(
                                {
                                    "customer_id": customer.customer_id,
                                    "account_id": account.account_id,
                                    "contract_id": contract.contract_id,
                                    "rate": contract.rate,
                                    "rate_option": contract.rate_option or "",
                                    "label": f"Contract {contract.contract_id} - {contract.rate}{contract.rate_option or ''}",
                                }
                            )

                if not self._contracts:
                    errors["base"] = "no_contracts"
                else:
                    return await self.async_step_select_contract()

            except hydroqc.error.HydroQcHTTPError:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception during login")
                errors["base"] = "cannot_connect"
            finally:
                if self._webuser:
                    await self._webuser.close_session()

        return self.async_show_form(
            step_id="account",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Required(CONF_CONTRACT_NAME): str,
                }
            ),
            errors=errors,
        )

    async def async_step_select_contract(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle contract selection."""
        if user_input is not None:
            # Find selected contract
            selected_contract = next(
                (c for c in self._contracts if c["contract_id"] == user_input["contract"]),
                None,
            )

            if selected_contract:
                # Store selected contract info
                self._selected_contract = selected_contract

                # Check if this rate needs preheat configuration
                rate_with_option = f"{selected_contract['rate']}{selected_contract['rate_option']}"
                if rate_with_option in ["DPC", "DCPC"]:
                    # Show preheat configuration step
                    return await self.async_step_configure_preheat()

                # For other rates, skip preheat and go directly to import history step
                return await self.async_step_import_history()

        # Build contract selection options
        contract_options = [
            {"value": c["contract_id"], "label": c["label"]} for c in self._contracts
        ]

        return self.async_show_form(
            step_id="select_contract",
            data_schema=vol.Schema(
                {
                    vol.Required("contract"): SelectSelector(
                        SelectSelectorConfig(
                            options=cast(list[SelectOptionDict], contract_options),
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
        )

    async def async_step_configure_preheat(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure preheat duration for DPC/DCPC rates."""
        if user_input is not None:
            # Store preheat duration and proceed to calendar step
            if self._selected_contract is not None:
                self._selected_contract["preheat_duration"] = user_input.get(
                    CONF_PREHEAT_DURATION, DEFAULT_PREHEAT_DURATION
                )
            return await self.async_step_calendar()

        if self._selected_contract is None:
            return self.async_abort(reason="missing_contract")

        rate_name = (
            "Flex-D (DPC)" if self._selected_contract["rate"] == "DPC" else "Winter Credits (D+CPC)"
        )
        return self.async_show_form(
            step_id="configure_preheat",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_PREHEAT_DURATION,
                        default=DEFAULT_PREHEAT_DURATION,
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            max=240,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement="minutes",
                        )
                    ),
                }
            ),
            description_placeholders={"rate_name": rate_name},
        )

    async def async_step_calendar(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure calendar entity for peak events (DPC/DCPC rates only)."""
        if self._selected_contract is None:
            return self.async_abort(reason="missing_contract")

        if user_input is not None:
            # Store calendar configuration
            calendar_entity_id = user_input.get(CONF_CALENDAR_ENTITY_ID, "").strip()
            if calendar_entity_id:
                self._selected_contract["calendar_entity_id"] = calendar_entity_id

            # Proceed to import history step
            return await self.async_step_import_history()

        # Show calendar configuration form
        return self.async_show_form(
            step_id="calendar",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_CALENDAR_ENTITY_ID): EntitySelector(
                        EntitySelectorConfig(domain="calendar")
                    ),
                }
            ),
            description_placeholders={"contract_name": self._contract_name or "Contract"},
        )

    async def async_step_import_history(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask user how many days of consumption history to import."""
        if self._selected_contract is None:
            return self.async_abort(reason="missing_contract")

        if user_input is not None:
            # Check if already configured
            await self.async_set_unique_id(self._selected_contract["contract_id"])
            self._abort_if_unique_id_configured()

            history_days = user_input.get(CONF_HISTORY_DAYS, 0)
            preheat_duration = self._selected_contract.get(
                "preheat_duration", DEFAULT_PREHEAT_DURATION
            )
            calendar_entity_id = self._selected_contract.get("calendar_entity_id", "")

            entry_data: dict[str, Any] = {
                CONF_AUTH_MODE: AUTH_MODE_PORTAL,
                CONF_USERNAME: self._username,
                CONF_PASSWORD: self._password,
                CONF_CONTRACT_NAME: self._contract_name,
                CONF_CUSTOMER_ID: self._selected_contract["customer_id"],
                CONF_ACCOUNT_ID: self._selected_contract["account_id"],
                CONF_CONTRACT_ID: self._selected_contract["contract_id"],
                CONF_RATE: self._selected_contract["rate"],
                CONF_RATE_OPTION: self._selected_contract["rate_option"],
                CONF_PREHEAT_DURATION: preheat_duration,
                CONF_HISTORY_DAYS: history_days,
            }

            # Add calendar configuration if provided
            if calendar_entity_id:
                entry_data[CONF_CALENDAR_ENTITY_ID] = calendar_entity_id

            return self.async_create_entry(
                title=f"{self._contract_name} ({self._selected_contract['rate']}{self._selected_contract['rate_option']})",
                data=entry_data,
            )

        return self.async_show_form(
            step_id="import_history",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_HISTORY_DAYS, default=0): NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            max=800,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement="days",
                        )
                    ),
                }
            ),
        )

    async def async_step_opendata(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle opendata mode setup - select sector."""
        errors: dict[str, str] = {}

        # Fetch available sectors from API if not already done
        if not self._available_sectors:
            self._available_sectors = await fetch_available_sectors()

        if user_input is not None:
            # Store selected sector and move to offer selection
            self._selected_sector = user_input["sector"]
            return await self.async_step_opendata_rate()

        # Build sector selection dropdown
        sector_options = [
            {"value": sector, "label": SECTOR_MAPPING.get(sector, sector)}
            for sector in self._available_sectors
        ]

        return self.async_show_form(
            step_id="opendata",
            data_schema=vol.Schema(
                {
                    vol.Required("sector"): SelectSelector(
                        SelectSelectorConfig(
                            options=cast(list[SelectOptionDict], sector_options),
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_opendata_rate(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle opendata mode setup - select offer for chosen sector."""
        if self._selected_sector is None:
            return self.async_abort(reason="missing_sector")

        errors: dict[str, str] = {}

        # Fetch offers for selected sector
        if not self._available_rates:
            self._available_rates = await fetch_offers_for_sector(self._selected_sector)

        if user_input is not None:
            contract_name = user_input[CONF_CONTRACT_NAME]

            # Parse rate selection (format: "RATE|OPTION")
            rate_selection = user_input["rate_selection"]
            rate, rate_option = rate_selection.split("|")
            rate_with_option = f"{rate}{rate_option}"

            # Store for calendar step
            self._contract_name = contract_name
            if self._selected_contract is None:
                self._selected_contract = {}

            self._selected_contract["rate"] = rate
            self._selected_contract["rate_option"] = rate_option
            self._selected_contract["sector"] = self._selected_sector

            # Only save preheat duration for rates that use it (DPC, D+CPC, and commercial peak rates)
            preheat_duration = DEFAULT_PREHEAT_DURATION
            if rate_with_option in [
                "DPC",
                "DCPC",
                "M-GDP",
                "M-CPC",
                "M-GPC",
                "M-ENG",
                "M-OEA",
            ]:
                preheat_duration = user_input.get(CONF_PREHEAT_DURATION, DEFAULT_PREHEAT_DURATION)

            self._selected_contract["preheat_duration"] = preheat_duration

            # Check if this rate needs calendar configuration
            if rate_with_option in ["DPC", "DCPC"]:
                return await self.async_step_calendar_opendata()

            # For other rates, create entry directly
            await self.async_set_unique_id(f"opendata_{contract_name.lower().replace(' ', '_')}")
            self._abort_if_unique_id_configured()

            sector_label = (
                SECTOR_MAPPING.get(self._selected_sector, self._selected_sector)
                if self._selected_sector
                else "Unknown"
            )
            return self.async_create_entry(
                title=f"{contract_name} ({sector_label} - {rate}{rate_option})",
                data={
                    CONF_AUTH_MODE: AUTH_MODE_OPENDATA,
                    CONF_CONTRACT_NAME: contract_name,
                    CONF_RATE: rate,
                    CONF_RATE_OPTION: rate_option,
                    CONF_PREHEAT_DURATION: preheat_duration,
                },
            )

        # Build rate selection dropdown from API data
        rate_options = [{"value": r["value"], "label": r["label"]} for r in self._available_rates]

        sector_label = (
            SECTOR_MAPPING.get(self._selected_sector, self._selected_sector)
            if self._selected_sector
            else "Unknown"
        )
        return self.async_show_form(
            step_id="opendata_rate",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CONTRACT_NAME, default="Home"): str,
                    vol.Required("rate_selection"): SelectSelector(
                        SelectSelectorConfig(
                            options=cast(list[SelectOptionDict], rate_options),
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required(
                        CONF_PREHEAT_DURATION,
                        default=DEFAULT_PREHEAT_DURATION,
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            max=240,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement="minutes",
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={"sector": sector_label},
        )

    async def async_step_calendar_opendata(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure calendar entity for peak events (OpenData mode with DPC/DCPC rates)."""
        if self._selected_contract is None or self._contract_name is None:
            return self.async_abort(reason="missing_contract")

        if user_input is not None:
            # Use contract name as unique ID for opendata mode
            await self.async_set_unique_id(
                f"opendata_{self._contract_name.lower().replace(' ', '_')}"
            )
            self._abort_if_unique_id_configured()

            # Store calendar configuration
            calendar_entity_id = user_input.get(CONF_CALENDAR_ENTITY_ID, "").strip()

            entry_data: dict[str, Any] = {
                CONF_AUTH_MODE: AUTH_MODE_OPENDATA,
                CONF_CONTRACT_NAME: self._contract_name,
                CONF_RATE: self._selected_contract["rate"],
                CONF_RATE_OPTION: self._selected_contract["rate_option"],
                CONF_PREHEAT_DURATION: self._selected_contract.get(
                    "preheat_duration", DEFAULT_PREHEAT_DURATION
                ),
            }

            # Add calendar configuration if provided
            if calendar_entity_id:
                entry_data[CONF_CALENDAR_ENTITY_ID] = calendar_entity_id

            sector_label = (
                SECTOR_MAPPING.get(self._selected_sector, self._selected_sector)
                if self._selected_sector
                else "Unknown"
            )

            return self.async_create_entry(
                title=f"{self._contract_name} ({sector_label} - {self._selected_contract['rate']}{self._selected_contract['rate_option']})",
                data=entry_data,
            )

        # Show calendar configuration form
        return self.async_show_form(
            step_id="calendar_opendata",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_CALENDAR_ENTITY_ID): EntitySelector(
                        EntitySelectorConfig(domain="calendar")
                    ),
                }
            ),
            description_placeholders={"contract_name": self._contract_name or "Contract"},
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,  # noqa: ARG004
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return HydroQcOptionsFlow()
