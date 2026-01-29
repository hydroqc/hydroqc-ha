"""Base DataUpdateCoordinator for Hydro-Québec integration."""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import (
    async_track_time_change,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import slugify

import hydroqc
from hydroqc.account import Account
from hydroqc.contract import ContractDCPC, ContractDPC, ContractDT
from hydroqc.contract.common import Contract
from hydroqc.customer import Customer
from hydroqc.webuser import WebUser

from ..utils import is_winter_season

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

        # Smart scheduling: track last update times for OpenData and Portal
        self._last_opendata_update: datetime.datetime | None = None
        self._last_portal_update: datetime.datetime | None = None
        self._last_consumption_sync: datetime.datetime | None = None

        # Track critical peak events signature for calendar sync optimization
        # Using signature instead of count to detect additions, removals, and time changes
        self._last_critical_events_signature: str = ""

        # Calculate random minute and second offsets based on integration start time
        # This distributes API calls across users to avoid thundering herd
        _now = datetime.datetime.now()
        self._schedule_offset_minutes = _now.minute % 15
        self._schedule_offset_seconds = _now.second

        # Track portal offline status to avoid log spam
        self._portal_last_offline_log: datetime.datetime | None = None

        # Track portal availability status
        self._portal_available: bool | None = None

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

        # Disable automatic polling - we'll manage our own schedule
        # This prevents unnecessary sensor updates when no data is fetched
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,  # Disabled - manual scheduling only
            config_entry=entry,
        )

        # Initialize mixin attributes (after super().__init__ so self.hass is available)
        self._init_consumption_sync()
        self._init_calendar_sync()

        # Set up scheduled update triggers
        # OpenData: Every 15 minutes during active window (10:30-15:00), hourly otherwise
        # Use offset based on start time to distribute API calls across users
        opendata_minutes = [(self._schedule_offset_minutes + i * 15) % 60 for i in range(4)]
        async_track_time_change(
            hass,
            self._async_scheduled_opendata_update,
            minute=opendata_minutes,  # Every 15 minutes with offset
            second=self._schedule_offset_seconds,
        )

        # Portal: Hourly during active window (0-8h), every 3 hours otherwise
        # Use offset based on start time to distribute API calls across users
        async_track_time_change(
            hass,
            self._async_scheduled_portal_update,
            minute=self._schedule_offset_minutes,  # Random minute within the hour
            second=self._schedule_offset_seconds,
        )

        # Calendar: Every 15 minutes to catch manual event changes
        # Independent of OpenData - only refreshes calendar-based sensor data
        async_track_time_change(
            hass,
            self._async_scheduled_calendar_refresh,
            minute=[0, 15, 30, 45],
            second=0,
        )

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

    async def _async_scheduled_opendata_update(self, _now: datetime.datetime) -> None:
        """Scheduled callback for OpenData updates.

        Runs every 5 minutes. Checks if update is needed based on time windows.
        Only triggers refresh if data should be fetched.
        """
        if self._should_update_opendata():
            _LOGGER.debug("[OpenData] Scheduled update trigger - fetching data")
            await self.async_request_refresh()
        else:
            _LOGGER.debug("[OpenData] Scheduled update skipped (not needed)")

    async def _async_scheduled_portal_update(self, _now: datetime.datetime) -> None:
        """Scheduled callback for Portal updates.

        Runs every hour. Checks if update is needed based on time windows.
        Only triggers refresh if data should be fetched.
        """
        if self.is_opendata_mode:
            return  # Skip in OpenData-only mode

        if self._should_update_portal():
            _LOGGER.debug("[Portal] Scheduled update trigger - fetching data")
            await self.async_request_refresh()
        else:
            _LOGGER.debug("[Portal] Scheduled update skipped (not needed)")

    async def _async_scheduled_calendar_refresh(self, _now: datetime.datetime) -> None:
        """Scheduled callback for Calendar data refresh.

        Runs every 15 minutes to catch manual calendar event changes.
        Independent of OpenData/Portal - only refreshes calendar-based sensor data.
        Does not trigger a full coordinator refresh.
        """
        if not self.calendar_peak_handler:
            return  # No calendar configured

        if not is_winter_season():
            return  # Off-season, skip calendar refresh

        _LOGGER.debug("[Calendar] Scheduled 15-min calendar refresh")

        # Wait for any pending calendar sync to complete first
        if self._calendar_sync_task and not self._calendar_sync_task.done():
            try:
                _LOGGER.debug("[Calendar] Waiting for pending sync task to complete")
                await asyncio.wait_for(self._calendar_sync_task, timeout=30.0)
            except TimeoutError:
                _LOGGER.warning("[Calendar] Calendar sync task timed out, proceeding anyway")
            except Exception as err:
                _LOGGER.warning("[Calendar] Calendar sync task failed: %s, proceeding anyway", err)

        # Refresh calendar-based sensor data directly (no full coordinator refresh)
        await self.async_load_calendar_peak_events()

        # Notify listeners of updated data without fetching all data sources
        self.async_set_updated_data(self.data)

    def _get_critical_events_signature(self) -> str:
        """Get signature of critical events for change detection.

        Returns a string hash of all critical events sorted by start time.
        This detects:
        - New events added (any position)
        - Events removed
        - Event times modified
        - Event replacements (same count, different events)
        """
        if not self.public_client or not self.public_client.peak_handler:
            return ""

        events = sorted(
            (e for e in self.public_client.peak_handler._events if e.is_critical),
            key=lambda e: e.start_date,
        )
        return "|".join(f"{e.start_date.isoformat()}_{e.end_date.isoformat()}" for e in events)

    def _is_opendata_active_window(self) -> bool:
        """Check if currently in OpenData active hours (10:30-15:00 EST).

        This is the window when Hydro-Québec typically announces critical peaks.
        """
        now = datetime.datetime.now(ZoneInfo("America/Toronto"))
        # Active window: 10:30 to 15:00
        # At 10:30 or later, but before 15:00
        if now.hour == 10:
            return now.minute >= 30  # Only from 10:30
        return 11 <= now.hour < 15

    def _is_portal_active_window(self) -> bool:
        """Check if currently in Portal active hours (00:00-08:00 EST)."""
        now = datetime.datetime.now(ZoneInfo("America/Toronto"))
        return 0 <= now.hour < 8

    def _should_update_opendata(self) -> bool:
        """Determine if OpenData should be updated based on time elapsed and window."""
        # Skip if off-season
        if not is_winter_season():
            return False

        # First update always runs
        if self._last_opendata_update is None:
            return True

        # Calculate time elapsed
        now = datetime.datetime.now(ZoneInfo("America/Toronto"))
        elapsed = (now - self._last_opendata_update).total_seconds()

        # Active window: 15 minutes, Inactive: 60 minutes
        # Note: Hourly updates are handled by async_track_time_change trigger
        if self._is_opendata_active_window():
            return elapsed >= 900  # 15 minutes
        return elapsed >= 3600  # 60 minutes

    def _should_update_portal(self) -> bool:
        """Determine if Portal should be updated based on time elapsed and window."""
        # First update always runs
        if self._last_portal_update is None:
            return True

        # Calculate time elapsed
        now = datetime.datetime.now(ZoneInfo("America/Toronto"))
        elapsed = (now - self._last_portal_update).total_seconds()

        # Active window: 60 minutes, Inactive: 180 minutes
        if self._is_portal_active_window():
            return elapsed >= 3600  # 60 minutes
        return elapsed >= 10800  # 180 minutes

    async def _async_update_data(self) -> dict[str, Any]:  # noqa: PLR0912, PLR0915
        """Fetch data from Hydro-Québec API.

        Called by async_request_refresh() triggered by scheduled callbacks.
        Always fetches new data when called - scheduling logic is external.
        """
        # Start with previous data to preserve values when specific updates are skipped
        data: dict[str, Any] = {
            "contract": self.data.get("contract") if self.data else None,
            "account": self.data.get("account") if self.data else None,
            "customer": self.data.get("customer") if self.data else None,
            "public_client": self.public_client,
        }

        data_fetched = False  # Track if any new data was actually fetched

        # OpenData: Fetch public peak data
        if is_winter_season():
            try:
                await self.public_client.fetch_peak_data()
                self._last_opendata_update = datetime.datetime.now(ZoneInfo("America/Toronto"))
                data_fetched = True

                current_hour = datetime.datetime.now().hour
                if self._last_peak_update_hour != current_hour:
                    self._last_peak_update_hour = current_hour
                    _LOGGER.info("[OpenData] Hourly peak data refresh at %02d:00", current_hour)
                else:
                    _LOGGER.debug("[OpenData] Public peak data fetched successfully")

            except Exception as err:
                _LOGGER.warning("[OpenData] Failed to fetch public peak data: %s", err)
        else:
            _LOGGER.debug("[OpenData] Skipped (off-season)")

        # Calendar sync: Only run if critical peak events changed
        # Uses signature to detect additions, removals, and time changes
        if self._calendar_entity_id and self.public_client.peak_handler:
            current_signature = self._get_critical_events_signature()

            if current_signature != self._last_critical_events_signature:
                if self._calendar_sync_task is None or self._calendar_sync_task.done():
                    self._calendar_sync_task = asyncio.create_task(
                        self._async_sync_calendar_events()
                    )
                    self._last_critical_events_signature = current_signature
                    _LOGGER.debug(
                        "Calendar sync triggered (signature changed: %s)",
                        current_signature[:50] if current_signature else "empty",
                    )
                else:
                    _LOGGER.debug("Calendar sync already in progress, skipping")

        # Load peak events from calendar for sensors (calendar is source of truth)
        # This runs on every update to refresh sensor data from calendar
        if self.calendar_peak_handler:
            await self.async_load_calendar_peak_events()

        # If in OpenData-only mode, return early
        if self.is_opendata_mode:
            _LOGGER.debug("OpenData mode: skipping portal data fetch")
            if not data_fetched:
                # No data fetched, don't update sensors
                _LOGGER.debug("No data fetched, skipping sensor update")
                raise UpdateFailed("No new data available")
            return data

        # Portal mode: fetch contract data
        try:
            # Check portal status before attempting updates
            if self._webuser:
                portal_available = await self._webuser.check_hq_portal_status()
                self._portal_available = portal_available  # Track for sensor
                if not portal_available:
                    now = datetime.datetime.now(ZoneInfo("America/Toronto"))
                    # Log warning once per hour to avoid spam
                    if (
                        self._portal_last_offline_log is None
                        or (now - self._portal_last_offline_log).total_seconds() >= 3600
                    ):
                        _LOGGER.warning("[Portal] Hydro-Québec portal is offline, skipping update")
                        self._portal_last_offline_log = now
                    # Portal offline - if no OpenData fetched either, skip update
                    if not data_fetched:
                        _LOGGER.debug(
                            "No data fetched (portal offline, no OpenData), skipping sensor update"
                        )
                        raise UpdateFailed("Portal offline and no new data")
                    return data

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
                data_fetched = True

                self._last_portal_update = datetime.datetime.now(ZoneInfo("America/Toronto"))
                _LOGGER.debug("[Portal] Successfully fetched authenticated contract data")

        except hydroqc.error.HydroQcHTTPError as err:
            _LOGGER.error("HTTP error fetching Hydro-Québec data: %s", err)
            raise UpdateFailed(f"Error fetching Hydro-Québec data: {err}") from err
        except Exception as err:
            _LOGGER.error("Unexpected error fetching data: %s", err)
            raise UpdateFailed(f"Unexpected error: {err}") from err

        # If no new data was fetched at all, skip sensor update
        if not data_fetched:
            _LOGGER.debug("No new data fetched, skipping sensor update")
            raise UpdateFailed("No new data available")

        # Update timestamp on successful update
        self.last_update_success_time = datetime.datetime.now(datetime.UTC)

        # Trigger consumption sync (hourly, with portal status check)
        # Only if not during first refresh to avoid blocking HA startup
        # AND only if consumption sync is enabled in config (check options first, then data)
        enable_consumption_sync = self.entry.options.get(
            "enable_consumption_sync", self.entry.data.get("enable_consumption_sync", True)
        )
        if (
            self.is_portal_mode
            and self._contract
            and hasattr(self, "_first_refresh_done")
            and enable_consumption_sync
        ):
            # Check if enough time has elapsed (hourly)
            now = datetime.datetime.now(ZoneInfo("America/Toronto"))
            should_sync = (
                self._last_consumption_sync is None
                or (now - self._last_consumption_sync).total_seconds() >= 3600
            )

            if should_sync:
                self._regular_sync_task = asyncio.create_task(
                    self._async_regular_consumption_sync()
                )
                self._last_consumption_sync = now

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
