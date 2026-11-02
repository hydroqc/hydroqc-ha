"""Base config flow for Hydro-Québec integration."""

from __future__ import annotations

import logging
from typing import Any, cast

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
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
    TextSelector,
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
    CONF_ENABLE_CONSUMPTION_SYNC,
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


@callback
def _async_migrate_contract_registries(
    hass: HomeAssistant, entry_id: str, old_contract_id: str, new_contract_id: str
) -> None:
    """Move the entry's device and entities to the new contract id.

    Entity unique ids and the device identifier are built from the contract id,
    without this the reload would create a second set of entities (suffixed _2).
    """
    ent_reg = er.async_get(hass)
    old_prefix = f"{old_contract_id}_"
    for entity in er.async_entries_for_config_entry(ent_reg, entry_id):
        if entity.unique_id.startswith(old_prefix):
            ent_reg.async_update_entity(
                entity.entity_id,
                new_unique_id=f"{new_contract_id}_{entity.unique_id.removeprefix(old_prefix)}",
            )

    dev_reg = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(dev_reg, entry_id):
        if (DOMAIN, old_contract_id) in device.identifiers:
            dev_reg.async_update_device(device.id, new_identifiers={(DOMAIN, new_contract_id)})


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

            errors = await self._async_fetch_contracts()
            if not errors:
                return await self.async_step_select_contract()

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

    async def _async_fetch_contracts(self) -> dict[str, str]:
        """Log in to the portal and collect every contract of the account.

        Returns the form errors, empty on success.
        """
        errors: dict[str, str] = {}
        assert self._username is not None
        assert self._password is not None

        try:
            # Check portal status first
            temp_webuser = WebUser(
                self._username,
                self._password,
                verify_ssl=True,
                log_level="INFO",
                http_log_level="WARNING",
            )

            portal_available = await temp_webuser.check_hq_portal_status()
            if not portal_available:
                errors["base"] = "portal_unavailable"
                await temp_webuser.close_session()
                raise RuntimeError("Portal unavailable")

            # Try to login and fetch contracts
            self._webuser = temp_webuser
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

        except hydroqc.error.HydroQcHTTPError as err:
            # Check if it's a 500 error (portal maintenance)
            if hasattr(err, "status_code") and err.status_code == 500:
                errors["base"] = "portal_maintenance"
            else:
                errors["base"] = "invalid_auth"
        except RuntimeError:
            # Portal unavailable - error already set above
            pass
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception during login")
            errors["base"] = "cannot_connect"
        finally:
            if self._webuser:
                await self._webuser.close_session()

        return errors

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

                # Check if this rate needs calendar configuration
                rate_with_option = f"{selected_contract['rate']}{selected_contract['rate_option']}"
                if rate_with_option in ["DPC", "DCPC"]:
                    # Show calendar configuration step
                    return await self.async_step_calendar()

                # For other rates, skip calendar and go directly to import history step
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

    async def async_step_calendar(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure calendar entity for peak events (DPC/DCPC rates only)."""
        if self._selected_contract is None:
            return self.async_abort(reason="missing_contract")

        errors: dict[str, str] = {}

        if user_input is not None:
            # Calendar is required for DPC/DCPC rates
            calendar_entity_id = user_input.get(CONF_CALENDAR_ENTITY_ID, "").strip()
            if not calendar_entity_id:
                errors["base"] = "calendar_required"
            elif not self.hass.states.get(calendar_entity_id):
                errors[CONF_CALENDAR_ENTITY_ID] = "calendar_not_found"
            else:
                # Store calendar configuration
                self._selected_contract["calendar_entity_id"] = calendar_entity_id
                # Proceed to import history step
                return await self.async_step_import_history()

        # Show calendar configuration form
        return self.async_show_form(
            step_id="calendar",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CALENDAR_ENTITY_ID): EntitySelector(
                        EntitySelectorConfig(domain="calendar")
                    ),
                }
            ),
            errors=errors,
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
            enable_consumption_sync = user_input.get(CONF_ENABLE_CONSUMPTION_SYNC, True)
            # Use default preheat duration during setup (can be changed in options)
            preheat_duration = DEFAULT_PREHEAT_DURATION
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
                CONF_ENABLE_CONSUMPTION_SYNC: enable_consumption_sync,
                CONF_HISTORY_DAYS: history_days if enable_consumption_sync else 0,
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
                    vol.Optional(CONF_ENABLE_CONSUMPTION_SYNC, default=True): bool,
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
            description_placeholders={
                "note": "Enable consumption sync to import hourly consumption data for the Energy Dashboard. If disabled, no consumption sensors will be created and the service to sync history will not be available."
            },
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

            # Use default preheat duration during setup (can be changed in options)
            preheat_duration = DEFAULT_PREHEAT_DURATION

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
                    vol.Required(CONF_CONTRACT_NAME, default="Home"): TextSelector(),
                    vol.Required("rate_selection"): SelectSelector(
                        SelectSelectorConfig(
                            options=cast(list[SelectOptionDict], rate_options),
                            mode=SelectSelectorMode.DROPDOWN,
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

        errors: dict[str, str] = {}

        if user_input is not None:
            # Calendar is required for DPC/DCPC rates
            calendar_entity_id = user_input.get(CONF_CALENDAR_ENTITY_ID, "").strip()
            if not calendar_entity_id:
                errors["base"] = "calendar_required"
            elif not self.hass.states.get(calendar_entity_id):
                errors[CONF_CALENDAR_ENTITY_ID] = "calendar_not_found"
            else:
                # Use contract name as unique ID for opendata mode
                await self.async_set_unique_id(
                    f"opendata_{self._contract_name.lower().replace(' ', '_')}"
                )
                self._abort_if_unique_id_configured()

                entry_data: dict[str, Any] = {
                    CONF_AUTH_MODE: AUTH_MODE_OPENDATA,
                    CONF_CONTRACT_NAME: self._contract_name,
                    CONF_RATE: self._selected_contract["rate"],
                    CONF_RATE_OPTION: self._selected_contract["rate_option"],
                    CONF_PREHEAT_DURATION: DEFAULT_PREHEAT_DURATION,
                    CONF_CALENDAR_ENTITY_ID: calendar_entity_id,
                }

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
                    vol.Required(CONF_CALENDAR_ENTITY_ID): EntitySelector(
                        EntitySelectorConfig(domain="calendar")
                    ),
                }
            ),
            errors=errors,
            description_placeholders={"contract_name": self._contract_name or "Contract"},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Re-enter portal credentials, then pick the contract again."""
        entry = self._get_reconfigure_entry()
        if entry.data.get(CONF_AUTH_MODE) != AUTH_MODE_PORTAL:
            return self.async_abort(reason="reconfigure_portal_only")

        errors: dict[str, str] = {}

        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            # A blank password keeps the stored one
            self._password = user_input.get(CONF_PASSWORD) or entry.data[CONF_PASSWORD]

            errors = await self._async_fetch_contracts()
            if not errors:
                return await self.async_step_reconfigure_contract()

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=entry.data.get(CONF_USERNAME, "")): str,
                    vol.Optional(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
            description_placeholders={"contract_id": entry.data.get(CONF_CONTRACT_ID, "")},
        )

    async def async_step_reconfigure_contract(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Point the entry at the selected contract, keeping its entities and name."""
        entry = self._get_reconfigure_entry()
        old_contract_id = entry.data[CONF_CONTRACT_ID]

        if user_input is not None:
            selected = next(
                (c for c in self._contracts if c["contract_id"] == user_input["contract"]),
                None,
            )
            if selected is None:
                return self.async_abort(reason="missing_contract")

            new_contract_id = selected["contract_id"]
            if new_contract_id != old_contract_id:
                if any(
                    e.unique_id == new_contract_id and e.entry_id != entry.entry_id
                    for e in self._async_current_entries(include_ignore=False)
                ):
                    return self.async_abort(reason="already_configured")
                _async_migrate_contract_registries(
                    self.hass, entry.entry_id, old_contract_id, new_contract_id
                )

            contract_name = entry.data[CONF_CONTRACT_NAME]
            return self.async_update_reload_and_abort(
                entry,
                unique_id=new_contract_id,
                title=f"{contract_name} ({selected['rate']}{selected['rate_option']})",
                data_updates={
                    CONF_USERNAME: self._username,
                    CONF_PASSWORD: self._password,
                    CONF_CUSTOMER_ID: selected["customer_id"],
                    CONF_ACCOUNT_ID: selected["account_id"],
                    CONF_CONTRACT_ID: new_contract_id,
                    CONF_RATE: selected["rate"],
                    CONF_RATE_OPTION: selected["rate_option"],
                },
            )

        contract_options = [
            {"value": c["contract_id"], "label": c["label"]} for c in self._contracts
        ]
        contract_ids = [c["contract_id"] for c in self._contracts]
        default_contract = old_contract_id if old_contract_id in contract_ids else contract_ids[0]

        return self.async_show_form(
            step_id="reconfigure_contract",
            data_schema=vol.Schema(
                {
                    vol.Required("contract", default=default_contract): SelectSelector(
                        SelectSelectorConfig(
                            options=cast(list[SelectOptionDict], contract_options),
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            description_placeholders={"contract_id": old_contract_id},
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,  # noqa: ARG004
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return HydroQcOptionsFlow()
