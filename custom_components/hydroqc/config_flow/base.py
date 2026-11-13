"""Base config flow for Hydro-Québec integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
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

from ..auth import (
    LOGIN_MFA_REQUIRED,
    LOGIN_SUCCESS,
    async_request_mfa_code,
    async_submit_mfa_code,
    login_outcome,
    mfa_error_kind,
    supports_mfa,
    webuser_auth_kwargs,
)
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
    CONF_MFA_CODE,
    CONF_PREHEAT_DURATION,
    CONF_RATE,
    CONF_RATE_OPTION,
    DEFAULT_PREHEAT_DURATION,
    DOMAIN,
)
from ..session import async_save_session as save_session_state, stage_pending_session
from .helpers import SECTOR_MAPPING, fetch_available_sectors, fetch_offers_for_sector
from .options import HydroQcOptionsFlow

_LOGGER = logging.getLogger(__name__)

# Where the login was started from, so the verification step can hand control
# back to the right step once the portal accepts the account.
LOGIN_ORIGIN_USER = "user"
LOGIN_ORIGIN_RECONFIGURE = "reconfigure"
LOGIN_ORIGIN_REAUTH = "reauth"


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
        self._login_origin: str = LOGIN_ORIGIN_USER
        self._mfa_pending: bool = False
        self._maintenance_end: str = ""
        # Session captured during the initial setup: the config entry does not
        # exist yet, so it is written once HA creates it.
        self._pending_session_state: dict[str, Any] | None = None

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
        self._login_origin = LOGIN_ORIGIN_USER

        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]
            self._contract_name = user_input[CONF_CONTRACT_NAME]

            errors = await self._async_fetch_contracts()
            if not errors:
                if self._mfa_pending:
                    return await self.async_step_mfa()
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
            description_placeholders={"maintenance_end": self._maintenance_end},
        )

    async def _async_fetch_contracts(self) -> dict[str, str]:
        """Log in to the portal and collect every contract of the account.

        Returns the form errors, empty on success. When the portal asks for an
        e-mail verification code no error is returned and ``self._mfa_pending``
        is set: the caller has to show :meth:`async_step_mfa`.
        """
        errors = await self._async_start_portal_login()
        try:
            if errors or self._mfa_pending:
                return errors
            return await self._async_finish_login()
        finally:
            if not self._mfa_pending:
                await self._async_save_session()
                await self._async_close_webuser()

    async def _async_portal_unavailable_error(self) -> str:
        """Pick the error for an unavailable portal, naming the announced maintenance end if any."""
        # get_hq_portal_unavailability() only exists in newer hydroqc releases.
        get_window = getattr(self._webuser, "get_hq_portal_unavailability", None)
        if get_window is not None:
            try:
                window = await get_window()
            except Exception:  # pylint: disable=broad-except
                window = None
            if isinstance(window, dict) and window.get("to"):
                self._maintenance_end = str(window["to"])
                return "portal_maintenance_until"
        return "portal_unavailable"

    async def _async_start_portal_login(self) -> dict[str, str]:
        """Check the portal and authenticate the account.

        Keeps the portal client open when Hydro-Québec asks for a verification
        code: the pending transaction only lives in that client.
        """
        assert self._username is not None
        assert self._password is not None
        errors: dict[str, str] = {}
        self._webuser = None
        self._mfa_pending = False

        try:
            self._webuser = WebUser(
                self._username,
                self._password,
                verify_ssl=True,
                log_level="INFO",
                http_log_level="WARNING",
                **webuser_auth_kwargs(self._login_entry_options()),
            )

            if not await self._webuser.check_hq_portal_status():
                errors["base"] = await self._async_portal_unavailable_error()
                return errors

            outcome = login_outcome(await self._webuser.login())
            if outcome == LOGIN_MFA_REQUIRED:
                self._mfa_pending = True
            elif outcome != LOGIN_SUCCESS:
                errors["base"] = "invalid_auth"
        except hydroqc.error.HydroQcHTTPError as err:
            # A non-5xx status during the login can be a password change request, not only a wrong password.
            if getattr(err, "status_code", None) == 500:
                errors["base"] = "portal_maintenance"
            else:
                errors["base"] = "invalid_auth"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception during login")
            errors["base"] = "cannot_connect"

        return errors

    async def _async_finish_login(self) -> dict[str, str]:
        """Collect every contract of the authenticated account."""
        errors: dict[str, str] = {}
        if self._webuser is None:
            return {"base": "invalid_auth"}

        try:
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
            # The login already succeeded: an HTTP error here comes from the portal, not from the credentials.
            if getattr(err, "status_code", None) == 500:
                errors["base"] = "portal_maintenance"
            else:
                _LOGGER.warning("Hydro-Québec portal error while fetching contracts: %s", err)
                errors["base"] = "portal_unavailable"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception while fetching contracts")
            errors["base"] = "cannot_connect"

        return errors

    async def _async_close_webuser(self) -> None:
        """Close and forget the temporary portal client."""
        webuser, self._webuser = self._webuser, None
        if webuser is not None:
            await webuser.close_session()

    def _login_entry_options(self) -> Mapping[str, Any]:
        """Return the options of the entry this login belongs to, if any."""
        if self._login_origin == LOGIN_ORIGIN_REAUTH:
            return self._get_reauth_entry().options
        if self._login_origin == LOGIN_ORIGIN_RECONFIGURE:
            return self._get_reconfigure_entry().options
        return {}

    async def _async_save_session(self) -> None:
        """Persist the session of the login that just succeeded.

        Without it the next start would restore the session that just expired
        and could ask for another verification code immediately.
        """
        if self._webuser is None:
            return

        entry: config_entries.ConfigEntry | None = None
        if self._login_origin == LOGIN_ORIGIN_REAUTH:
            entry = self._get_reauth_entry()
        elif self._login_origin == LOGIN_ORIGIN_RECONFIGURE:
            entry = self._get_reconfigure_entry()

        export_state = getattr(self._webuser, "export_session_state", None)
        if not callable(export_state):
            return

        try:
            state = export_state()
        except Exception:  # pylint: disable=broad-except
            _LOGGER.debug("Could not export the Hydro-Québec session", exc_info=True)
            return

        if not isinstance(state, dict):
            return

        if entry is None:
            # Initial setup: HA has not created the config entry yet. Keep the
            # state until async_step_import_history can write it for the entry,
            # otherwise the coordinator logs in a second time right after setup
            # and asks for another verification code.
            if not state.get("refresh_token") and not state.get("cookies"):
                return
            self._pending_session_state = state
            return

        await save_session_state(self.hass, entry, state)

    async def _async_request_code(self) -> bool:
        """Ask Hydro-Québec for a new verification code."""
        if self._webuser is None or not supports_mfa(self._webuser):
            return False
        try:
            return await async_request_mfa_code(self._webuser)
        except Exception:  # pylint: disable=broad-except
            _LOGGER.warning("Could not request a new verification code", exc_info=True)
            return False

    async def _async_restart_login(self) -> bool:
        """Restart a login whose verification step expired.

        Returns True when a new code is waiting to be entered.
        """
        self._mfa_pending = False
        await self._async_close_webuser()
        errors = await self._async_start_portal_login()
        if errors or not self._mfa_pending:
            _LOGGER.error("Could not restart the Hydro-Québec login: %s", errors)
            return False
        return True

    async def _async_complete_login(self) -> ConfigFlowResult:
        """Hand control back to the step the login was started from."""
        await self._async_save_session()
        await self._async_close_webuser()
        if self._login_origin == LOGIN_ORIGIN_REAUTH:
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(),
                data_updates={CONF_PASSWORD: self._password},
                reason="reauth_successful",
            )
        if self._login_origin == LOGIN_ORIGIN_RECONFIGURE:
            return await self.async_step_reconfigure_contract()
        return await self.async_step_select_contract()

    async def _async_show_origin_form(self, errors: dict[str, str]) -> ConfigFlowResult:
        """Show the step the login was started from, with ``errors``.

        Used when the credentials were accepted but the account could not be
        read: the verification step is over, so re-showing the code form would
        only reject an already consumed code.
        """
        if self._login_origin == LOGIN_ORIGIN_REAUTH:
            entry = self._get_reauth_entry()
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
                errors=errors,
                description_placeholders={
                    "username": entry.data[CONF_USERNAME],
                    "maintenance_end": self._maintenance_end,
                },
            )
        if self._login_origin == LOGIN_ORIGIN_RECONFIGURE:
            entry = self._get_reconfigure_entry()
            return self.async_show_form(
                step_id="reconfigure",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_USERNAME, default=entry.data.get(CONF_USERNAME, "")): str,
                        vol.Optional(CONF_PASSWORD): str,
                    }
                ),
                errors=errors,
                description_placeholders={
                    "contract_id": entry.data.get(CONF_CONTRACT_ID, ""),
                    "maintenance_end": self._maintenance_end,
                },
            )
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
            description_placeholders={"maintenance_end": self._maintenance_end},
        )

    async def async_step_mfa(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the e-mail verification code sent by Hydro-Québec.

        The wrapper requests the first code when the verification step is
        detected. An empty field asks for a new one: the first message may have
        been lost or the code may have expired.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            code = str(user_input.get(CONF_MFA_CODE) or "").strip()
            if not code:
                errors["base"] = (
                    "mfa_code_resent"
                    if await self._async_request_code()
                    else "mfa_code_resend_failed"
                )
            elif self._webuser is None or not supports_mfa(self._webuser):
                errors["base"] = "mfa_unsupported"
            else:
                try:
                    status = await async_submit_mfa_code(self._webuser, code)
                except Exception as err:  # pylint: disable=broad-except
                    kind = mfa_error_kind(err)
                    if kind == "invalid":
                        errors["base"] = "invalid_mfa_code"
                    elif kind in ("expired", "required"):
                        errors["base"] = (
                            "mfa_code_resent"
                            if await self._async_restart_login()
                            else "mfa_expired"
                        )
                    else:
                        _LOGGER.exception("Unexpected error while submitting the verification code")
                        errors["base"] = "cannot_connect"
                else:
                    if login_outcome(status) == LOGIN_SUCCESS:
                        self._mfa_pending = False
                        errors = await self._async_finish_login()
                        if not errors:
                            return await self._async_complete_login()
                        # The code was accepted but the account could not be
                        # read: the verification step is over, hand the errors
                        # back to the step the login started from.
                        await self._async_close_webuser()
                        return await self._async_show_origin_form(errors)
                    errors["base"] = "invalid_mfa_code"

        return self.async_show_form(
            step_id="mfa",
            data_schema=vol.Schema({vol.Required(CONF_MFA_CODE): str}),
            errors=errors,
            description_placeholders={"email": self._username or ""},
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

            # Stage the session under the contract id: the coordinator takes it
            # over once Home Assistant created the entry, so the first refresh
            # does not log in (and ask for a code) a second time.
            if self._pending_session_state is not None:
                stage_pending_session(
                    self.hass,
                    self._selected_contract["contract_id"],
                    self._pending_session_state,
                )
                self._pending_session_state = None

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
        self._login_origin = LOGIN_ORIGIN_RECONFIGURE

        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            # A blank password keeps the stored one
            self._password = user_input.get(CONF_PASSWORD) or entry.data[CONF_PASSWORD]

            errors = await self._async_fetch_contracts()
            if not errors:
                if self._mfa_pending:
                    return await self.async_step_mfa()
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
            description_placeholders={
                "contract_id": entry.data.get(CONF_CONTRACT_ID, ""),
                "maintenance_end": self._maintenance_end,
            },
        )

    async def async_step_reauth(self, _entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start reauthentication after Hydro-Québec refused the stored credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the new portal password."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        self._login_origin = LOGIN_ORIGIN_REAUTH

        if user_input is not None:
            self._username = entry.data[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]

            errors = await self._async_fetch_contracts()
            if not errors:
                if self._mfa_pending:
                    return await self.async_step_mfa()
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_PASSWORD: self._password},
                    reason="reauth_successful",
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
            description_placeholders={
                "username": entry.data[CONF_USERNAME],
                "maintenance_end": self._maintenance_end,
            },
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
                reason="reconfigure_successful",
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
