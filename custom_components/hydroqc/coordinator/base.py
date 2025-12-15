"""Base DataUpdateCoordinator for Hydro-Québec integration."""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import slugify

import hydroqc
from hydroqc.account import Account
from hydroqc.contract import ContractDCPC, ContractDPC, ContractDT
from hydroqc.contract.common import Contract
from hydroqc.customer import Customer
from hydroqc.webuser import WebUser

try:
    HYDROQC_VERSION = hydroqc.__version__  # type: ignore[attr-defined]
except AttributeError:
    HYDROQC_VERSION = "unknown"

from ..const import (
    AUTH_MODE_OPENDATA,
    AUTH_MODE_PORTAL,
    CONF_ACCOUNT_ID,
    CONF_AUTH_MODE,
    CONF_CONTRACT_ID,
    CONF_CONTRACT_NAME,
    CONF_CUSTOMER_ID,
    CONF_PREHEAT_DURATION,
    CONF_RATE,
    CONF_RATE_OPTION,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from ..public_data_client import PublicDataClient
from .calendar_sync import CalendarSyncMixin
from .consumption_sync import ConsumptionSyncMixin
from .sensor_data import SensorDataMixin

_LOGGER = logging.getLogger(__name__)


class HydroQcDataCoordinator(
    DataUpdateCoordinator[dict[str, Any]],
    ConsumptionSyncMixin,
    CalendarSyncMixin,
    SensorDataMixin,
):
    """Class to manage fetching Hydro-Québec data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        _LOGGER.info("Hydro-Québec API Wrapper version: %s", HYDROQC_VERSION)
        self.entry = entry
        self._auth_mode = entry.data[CONF_AUTH_MODE]
        self._rate = entry.data[CONF_RATE]
        self._rate_option = entry.data.get(CONF_RATE_OPTION, "")
        self._preheat_duration = entry.data.get(CONF_PREHEAT_DURATION, 120)

        # Portal mode attributes (requires login)
        self._webuser: WebUser | None = None
        self._customer: Customer | None = None
        self._account: Account | None = None
        self._contract: Contract | None = None

        # Public data client for peak data (always used)
        rate_for_client = f"{self._rate}{self._rate_option}"
        self.public_client = PublicDataClient(
            rate_code=rate_for_client, preheat_duration=self._preheat_duration
        )

        # Track last successful update time
        self.last_update_success_time: datetime.datetime | None = None

        # Track first refresh completion (set by __init__.py after setup)
        self._first_refresh_done: bool = False

        # Track last peak update hour to ensure hourly updates
        self._last_peak_update_hour: int | None = None

        # Initialize webuser if in portal mode
        if self._auth_mode == AUTH_MODE_PORTAL:
            self._webuser = WebUser(
                entry.data[CONF_USERNAME],
                entry.data[CONF_PASSWORD],
                verify_ssl=True,
                log_level="INFO",
                http_log_level="WARNING",
            )
            self._customer_id = entry.data[CONF_CUSTOMER_ID]
            self._account_id = entry.data[CONF_ACCOUNT_ID]
            self._contract_id = entry.data[CONF_CONTRACT_ID]

        # Get update interval from options or use default
        update_interval_seconds = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=datetime.timedelta(seconds=update_interval_seconds),
            config_entry=entry,
        )

        # Initialize mixin attributes (after super().__init__ so self.hass is available)
        self._init_consumption_sync()
        self._init_calendar_sync()

    @property
    def is_portal_mode(self) -> bool:
        """Return True if using portal authentication."""
        return bool(self._auth_mode == AUTH_MODE_PORTAL)

    @property
    def is_opendata_mode(self) -> bool:
        """Return True if using open data API only."""
        return bool(self._auth_mode == AUTH_MODE_OPENDATA)

    @property
    def rate(self) -> str:
        """Return the rate code."""
        return str(self._rate)

    @property
    def rate_option(self) -> str:
        """Return the rate option."""
        return str(self._rate_option)

    @property
    def rate_with_option(self) -> str:
        """Return rate + rate_option concatenated (e.g., 'DCPC', 'DT', 'DPC')."""
        return f"{self._rate}{self._rate_option}"

    @property
    def contract_name(self) -> str:
        """Return the contract name for display purposes."""
        return str(self.entry.data.get(CONF_CONTRACT_NAME, "Contract"))

    @property
    def contract_id(self) -> str:
        """Return the contract ID.

        For portal mode, returns the actual contract ID.
        For opendata mode, generates a stable ID from contract name.
        """
        if self.is_portal_mode:
            return str(self._contract_id)
        # For opendata mode, generate stable ID from contract name
        contract_name = self.contract_name
        return f"opendata_{slugify(contract_name)}"

    async def _async_update_data(self) -> dict[str, Any]:  # noqa: PLR0912, PLR0915
        """Fetch data from Hydro-Québec API."""
        data: dict[str, Any] = {
            "contract": None,
            "account": None,
            "customer": None,
            "public_client": self.public_client,
        }

        # Check if we need to update peak data (always on the hour)
        current_hour = datetime.datetime.now().hour
        should_update_peaks = self._last_peak_update_hour != current_hour

        # Always fetch public peak data (especially on the hour for accurate state)
        if should_update_peaks:
            try:
                await self.public_client.fetch_peak_data()
                self._last_peak_update_hour = current_hour
                _LOGGER.info("[OpenData] Hourly peak data refresh at %02d:00", current_hour)
            except Exception as err:
                _LOGGER.warning("[OpenData] Failed to fetch public peak data: %s", err)
        else:
            # Still fetch but don't log as prominently (regular interval update)
            try:
                await self.public_client.fetch_peak_data()
                _LOGGER.debug("[OpenData] Public peak data fetched successfully")
            except Exception as err:
                _LOGGER.warning("[OpenData] Failed to fetch public peak data: %s", err)

        # Sync calendar events if configured and peak data available (for both modes)
        # Only start sync if not already running (prevent duplicate event creation)
        if self._calendar_entity_id and self.public_client.peak_handler:
            if self._calendar_sync_task is None or self._calendar_sync_task.done():
                self._calendar_sync_task = asyncio.create_task(self._async_sync_calendar_events())
            else:
                _LOGGER.debug("Calendar sync already in progress, skipping")

        # If in peak-only mode, we're done
        if self.is_opendata_mode:
            _LOGGER.debug("OpenData mode: skipping portal data fetch")
            return data

        # Portal mode: fetch contract data
        try:
            # Login if session expired
            if self._webuser and self._webuser.session_expired:
                _LOGGER.debug("Session expired, re-authenticating")
                await self._webuser.login()

            # Fetch contract hierarchy
            if self._webuser:
                await self._webuser.get_info()
                await self._webuser.fetch_customers_info()

                self._customer = self._webuser.get_customer(self._customer_id)
                await self._customer.get_info()

                self._account = self._customer.get_account(self._account_id)
                self._contract = self._account.get_contract(self._contract_id)

                # Fetch period data
                await self._contract.get_periods_info()

                # Fetch outages
                await self._contract.refresh_outages()

                # Rate-specific data fetching
                if self.rate == "D" and self.rate_option == "CPC":
                    # Winter Credits
                    contract_dcpc = self._contract
                    if isinstance(contract_dcpc, ContractDCPC):
                        contract_dcpc.set_preheat_duration(self._preheat_duration)
                        await contract_dcpc.peak_handler.refresh_data()
                    _LOGGER.debug("[Portal] Fetched DCPC winter credit data")

                elif self.rate == "DPC":
                    # Flex-D
                    contract_dpc = self._contract
                    if isinstance(contract_dpc, ContractDPC):
                        contract_dpc.set_preheat_duration(self._preheat_duration)
                        await contract_dpc.get_dpc_data()
                        await contract_dpc.peak_handler.refresh_data()
                    _LOGGER.debug("[Portal] Fetched DPC data")

                elif self.rate == "DT":
                    # Dual Tariff
                    contract_dt = self._contract
                    if isinstance(contract_dt, ContractDT):
                        await contract_dt.get_annual_consumption()
                    _LOGGER.debug("Fetched DT annual consumption")

                data["contract"] = self._contract
                data["account"] = self._account
                data["customer"] = self._customer

                _LOGGER.debug("Successfully fetched authenticated contract data")

        except hydroqc.error.HydroQcHTTPError as err:
            _LOGGER.error("HTTP error fetching Hydro-Québec data: %s", err)
            raise UpdateFailed(f"Error fetching Hydro-Québec data: {err}") from err
        except Exception as err:
            _LOGGER.error("Unexpected error fetching data: %s", err)
            raise UpdateFailed(f"Unexpected error: {err}") from err

        # Update timestamp on successful update
        self.last_update_success_time = datetime.datetime.now(datetime.UTC)

        # Trigger consumption sync (matches hydroqc2mqtt pattern)
        # Only if not during first refresh to avoid blocking HA startup
        if self.is_portal_mode and self._contract and hasattr(self, "_first_refresh_done"):
            self._regular_sync_task = asyncio.create_task(self._async_regular_consumption_sync())

        return data

    async def async_shutdown(self) -> None:
        """Shutdown coordinator and close sessions."""
        _LOGGER.debug("Shutting down coordinator")
        # Cancel any running CSV import task
        if hasattr(self, "_csv_import_task") and self._csv_import_task:
            if not self._csv_import_task.done():
                self._csv_import_task.cancel()
                try:
                    await self._csv_import_task
                except asyncio.CancelledError:
                    _LOGGER.debug("Cancelled CSV import task")

        # Cancel any running regular sync task
        if hasattr(self, "_regular_sync_task") and self._regular_sync_task:
            if not self._regular_sync_task.done():
                self._regular_sync_task.cancel()
                try:
                    await self._regular_sync_task
                except asyncio.CancelledError:
                    _LOGGER.debug("Cancelled regular sync task")

        if self._webuser:
            await self._webuser.close_session()
        await self.public_client.close_session()

    def _schedule_hourly_update(self) -> None:
        """Schedule the next update at the top of the hour for peak sensors."""
        now = datetime.datetime.now()
        # Schedule for the next hour
        next_hour = (now + datetime.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

        _LOGGER.debug("Scheduling next peak update at %s", next_hour)

        async_track_point_in_time(
            self.hass,
            self._async_hourly_update,
            next_hour,
        )

    async def _async_hourly_update(self, _now: datetime.datetime) -> None:
        """Perform hourly update for peak sensors."""
        _LOGGER.debug("Triggering hourly peak sensor update")
        await self.async_request_refresh()
        # Schedule the next hourly update
        self._schedule_hourly_update()
