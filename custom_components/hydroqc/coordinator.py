"""DataUpdateCoordinator for Hydro-Québec integration."""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.storage import Store
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

from . import calendar_manager
from .const import (
    AUTH_MODE_OPENDATA,
    AUTH_MODE_PORTAL,
    CONF_ACCOUNT_ID,
    CONF_AUTH_MODE,
    CONF_CALENDAR_ENTITY_ID,
    CONF_CONTRACT_ID,
    CONF_CONTRACT_NAME,
    CONF_CUSTOMER_ID,
    CONF_INCLUDE_NON_CRITICAL_PEAKS,
    CONF_PREHEAT_DURATION,
    CONF_RATE,
    CONF_RATE_OPTION,
    CONF_UPDATE_INTERVAL,
    DEFAULT_INCLUDE_NON_CRITICAL_PEAKS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .consumption_history import ConsumptionHistoryImporter
from .public_data_client import PublicDataClient
from .statistics_manager import StatisticsManager

_LOGGER = logging.getLogger(__name__)

# Storage for calendar event UIDs (persists across restarts)
STORAGE_VERSION = 1
STORAGE_KEY_CALENDAR_UIDS = "hydroqc.calendar_uids"


class HydroQcDataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
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

        # Track if initial sync has completed
        self._initial_sync_done = False

        # Track background CSV import task (for long historical imports)
        self._csv_import_task: asyncio.Task[None] | None = None
        # Track regular sync task (for recent data updates)
        self._regular_sync_task: asyncio.Task[None] | None = None
        # Track calendar sync task (prevent concurrent syncs)
        self._calendar_sync_task: asyncio.Task[None] | None = None

        # Track first refresh completion (set by __init__.py after setup)
        self._first_refresh_done: bool = False

        # Initialize helper modules (lazy initialization after contract is available)
        self._statistics_manager: StatisticsManager | None = None
        self._history_importer: ConsumptionHistoryImporter | None = None

        # Calendar configuration (for DPC/DCPC rates)
        self._calendar_entity_id = entry.options.get(
            CONF_CALENDAR_ENTITY_ID, entry.data.get(CONF_CALENDAR_ENTITY_ID)
        )
        self._include_non_critical_peaks = entry.options.get(
            CONF_INCLUDE_NON_CRITICAL_PEAKS,
            entry.data.get(CONF_INCLUDE_NON_CRITICAL_PEAKS, DEFAULT_INCLUDE_NON_CRITICAL_PEAKS),
        )

        # Calendar validation state (retry logic to avoid false positives)
        self._calendar_validation_attempts = 0
        self._calendar_validation_passed = False
        self._calendar_max_validation_attempts = 10

        # Track created calendar event UIDs (persisted across restarts)
        self._created_event_uids: set[str] = set()
        # Storage for persisting calendar event UIDs
        self._calendar_uid_store: Store[dict[str, list[str]]] | None = None
        if self._calendar_entity_id:
            # Create unique storage key per contract to avoid conflicts
            storage_key = f"{STORAGE_KEY_CALENDAR_UIDS}.{entry.entry_id}"
            self._calendar_uid_store = Store(hass, STORAGE_VERSION, storage_key, encoder=None)

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

        # Track last peak update hour to ensure hourly updates
        self._last_peak_update_hour: int | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=datetime.timedelta(seconds=update_interval_seconds),
            config_entry=entry,
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

    @property
    def is_consumption_history_syncing(self) -> bool:
        """Return True if CSV import is currently running."""
        if self._csv_import_task is None:
            return False

        is_done = self._csv_import_task.done()
        if is_done:
            # Task is complete, clear the reference
            _LOGGER.debug("CSV import task is done, clearing reference")
            self._csv_import_task = None
            return False

        return True

    async def async_load_calendar_uids(self) -> None:
        """Load persisted calendar event UIDs from storage."""
        if not self._calendar_uid_store:
            _LOGGER.debug("No calendar UID store configured")
            return

        try:
            data = await self._calendar_uid_store.async_load()
            if data and isinstance(data, dict):
                uids = data.get("uids", [])
                self._created_event_uids = set(uids)
                _LOGGER.info(
                    "Loaded %d persisted calendar event UIDs for %s: %s",
                    len(self._created_event_uids),
                    self.contract_name,
                    list(self._created_event_uids)[:3] if self._created_event_uids else "[]",
                )
            else:
                _LOGGER.info("No persisted calendar UIDs found for %s", self.contract_name)
        except Exception as err:
            _LOGGER.warning("Failed to load calendar UIDs from storage: %s", err)
            self._created_event_uids = set()

    async def async_save_calendar_uids(self) -> None:
        """Save calendar event UIDs to persistent storage."""
        if not self._calendar_uid_store:
            return

        try:
            data = {"uids": list(self._created_event_uids)}
            await self._calendar_uid_store.async_save(data)
            _LOGGER.debug(
                "Saved %d calendar event UIDs to storage",
                len(self._created_event_uids),
            )
        except Exception as err:
            _LOGGER.error("Failed to save calendar UIDs to storage: %s", err)

    def _ensure_helper_modules(self) -> None:
        """Ensure helper modules are initialized (lazy initialization)."""
        if self._statistics_manager is None:
            contract_name = self.entry.data.get(CONF_CONTRACT_NAME, "home")
            self._statistics_manager = StatisticsManager(
                self.hass, self._contract, self._rate, self._get_statistic_id, contract_name
            )
        if self._history_importer is None and self._contract is not None:
            self._history_importer = ConsumptionHistoryImporter(
                self.hass,
                self._contract,
                self._rate,
                self._get_statistic_id,
                self._statistics_manager,
            )

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

    async def _async_regular_consumption_sync(self) -> None:
        """Regular consumption sync (called every 60s from _async_update_data).

        Matches hydroqc2mqtt pattern:
        - First sync: Check last 30 days and fill gaps or trigger CSV import
        - Regular sync: Only sync last 24 hours
        - Skips if CSV import is running
        """
        if not self.is_portal_mode:
            return

        # Skip if CSV import is running
        if self.is_consumption_history_syncing:
            _LOGGER.debug("CSV import in progress, skipping regular sync")
            return

        # Ensure helper modules are initialized
        self._ensure_helper_modules()

        # Auto-detect if this is the first sync
        is_initial_sync = not self._initial_sync_done
        if is_initial_sync:
            self._initial_sync_done = True

        try:
            if is_initial_sync:
                # Initial sync: Schedule background task to check and fill gaps
                _LOGGER.info("Starting initial consumption statistics sync (background)")
                self._regular_sync_task = asyncio.create_task(self._async_initial_sync())
            else:
                # Regular sync: Only sync last 24 hours
                _LOGGER.debug("Starting regular consumption statistics sync (last 24h)")
                start_date = datetime.date.today() - datetime.timedelta(days=1)
                await self.async_fetch_hourly_consumption(start_date, datetime.date.today())
        except Exception as err:
            _LOGGER.error("Error during consumption sync: %s", err)

    async def _async_initial_sync(self) -> None:
        """Initial consumption sync - runs in background to not block startup.

        Syncs last 30 days of consumption data. For full history import,
        use the 'hydroqc.sync_consumption_history' service.
        """
        try:
            # Yield control to let HA finish starting
            await asyncio.sleep(0.1)

            if self._statistics_manager is None:
                _LOGGER.warning("Statistics manager not initialized, skipping initial sync")
                return

            (
                needs_csv_import,
                sync_start_date,
            ) = await self._statistics_manager.determine_sync_start_date()

            if needs_csv_import:
                # No statistics found - sync last 30 days
                _LOGGER.info(
                    "No existing statistics found. Syncing last 30 days. "
                    "Use 'hydroqc.sync_consumption_history' service to import full history (up to 2 years)."
                )
                start_date = datetime.date.today() - datetime.timedelta(days=30)
                await self.async_fetch_hourly_consumption(start_date, datetime.date.today())
            elif sync_start_date is not None:
                # Found statistics, fill gap from last valid stat to now
                # Limit to 30 days to avoid long sync on startup
                max_sync_date = datetime.date.today() - datetime.timedelta(days=30)
                actual_start_date = max(sync_start_date, max_sync_date)

                days_to_sync = (datetime.date.today() - actual_start_date).days + 1
                _LOGGER.info(
                    "Syncing %d day(s) from %s to now",
                    days_to_sync,
                    actual_start_date.isoformat(),
                )
                await self.async_fetch_hourly_consumption(actual_start_date, datetime.date.today())

                # If gap is larger than 30 days, inform user
                if sync_start_date < max_sync_date:
                    missing_days = (max_sync_date - sync_start_date).days
                    _LOGGER.warning(
                        "Found %d day(s) of missing data before the last 30 days. "
                        "Use 'hydroqc.sync_consumption_history' service to import full history.",
                        missing_days,
                    )
            else:
                # Statistics are up to date, nothing to do
                _LOGGER.info("Consumption statistics are up to date, no sync needed")
        except Exception as err:
            _LOGGER.error("Error during initial consumption sync: %s", err)

    def async_sync_consumption_history(self, days_back: int = 731) -> None:
        """Import historical consumption data via CSV (background task).

        Note: This is NOT an async method - it schedules a background task and returns immediately.

        Args:
            days_back: Number of days back to import (default 731 = ~2 years)
        """
        if not self.is_portal_mode:
            _LOGGER.warning("Consumption history only available in Portal mode")
            return

        # Ensure helper modules are initialized
        self._ensure_helper_modules()

        _LOGGER.info("Starting consumption history sync task (CSV import)")

        # Start background task with callback to sync recent data after completion
        async def _csv_import_with_followup() -> None:
            """Run CSV import followed by initial sync to get most recent data."""
            try:
                if self._history_importer is None:
                    _LOGGER.error("History importer not initialized")
                    return
                await self._history_importer.import_csv_history(days_back)
                _LOGGER.info("CSV import completed, running initial sync to get recent data")
                await self._async_initial_sync()
            except Exception as err:
                _LOGGER.error("Error during CSV import or follow-up sync: %s", err)

        self._csv_import_task = asyncio.create_task(_csv_import_with_followup())

    async def async_fetch_hourly_consumption(
        self, start_date: datetime.date, end_date: datetime.date
    ) -> None:
        """Fetch hourly consumption data and import to Home Assistant energy dashboard.

        Only available in portal mode (requires login).
        Uses recorder API to import statistics directly into HA energy dashboard.

        Args:
            start_date: Start date for fetch
            end_date: End date for fetch
        """
        if not self.is_portal_mode:
            _LOGGER.warning("Hourly consumption only available in portal mode")
            return

        if not self._contract:
            _LOGGER.warning("Contract not initialized")
            return

        # Ensure helper modules are initialized
        self._ensure_helper_modules()

        if self._statistics_manager is None:
            _LOGGER.error("Statistics manager not initialized")
            return

        # Delegate to StatisticsManager
        await self._statistics_manager.fetch_and_import_hourly_consumption(start_date, end_date)

    def _get_statistic_id(self, consumption_type: str) -> str:
        """Get the statistic_id for a consumption type.

        External statistics don't use entity IDs, they use domain:name format.
        """
        contract_name = self.entry.data.get(CONF_CONTRACT_NAME, "home")
        base_name = slugify(contract_name)

        if consumption_type == "total":
            return f"hydroqc:{base_name}_hourly_consumption"
        return f"hydroqc:{base_name}_{consumption_type}_hourly_consumption"

    def get_sensor_value(self, data_source: str) -> Any:  # noqa: PLR0911, PLR0912
        """Extract sensor value from data using dot-notation path.

        Example: "contract.cp_current_bill" -> walks the object graph.
        Returns None if data not available.

        Special handling for binary sensors (paths ending with is_critical):
        - If intermediate object is None, returns False (not None/Unknown)
        - Ensures binary sensors show False outside season instead of Unknown

        Special handling for DCPC preheat_in_progress:
        - Only returns True if preheat is in progress AND next peak is critical
        - This prevents preheat triggers on non-critical peaks
        """
        if not self.data:
            # For binary sensors ending with is_critical, return False instead of None
            if data_source.endswith(".is_critical"):
                return False
            return None

        # Special handling for DCPC winter credits preheat
        # Only trigger preheat for critical peaks, not regular scheduled peaks
        if (
            data_source == "public_client.peak_handler.preheat_in_progress"
            and self.rate_with_option == "DCPC"
        ):
            public_client = self.data.get("public_client")
            if public_client and public_client.peak_handler:
                preheat_active = public_client.peak_handler.preheat_in_progress
                next_peak_critical = (
                    public_client.peak_handler.next_peak.is_critical
                    if public_client.peak_handler.next_peak
                    else False
                )
                # Only return True if both preheat is active AND next peak is critical
                return preheat_active and next_peak_critical
            return False

        # Special handling for DCPC preheat start timestamp
        # Only show preheat start time if next peak is critical
        if (
            data_source == "public_client.peak_handler.next_peak.preheat.start_date"
            and self.rate_with_option == "DCPC"
        ):
            public_client = self.data.get("public_client")
            if (
                public_client
                and public_client.peak_handler
                and public_client.peak_handler.next_peak
            ):
                # Only return preheat start time if the next peak is critical
                if public_client.peak_handler.next_peak.is_critical:
                    return public_client.peak_handler.next_peak.preheat.start_date
            return None

        parts = data_source.split(".")
        obj = None

        # Start with the root object
        if parts[0] == "contract":
            obj = self.data.get("contract")
        elif parts[0] == "account":
            obj = self.data.get("account")
        elif parts[0] == "customer":
            obj = self.data.get("customer")
        elif parts[0] == "public_client":
            obj = self.data.get("public_client")

        if obj is None:
            # For binary sensors ending with is_critical, return False instead of None
            if data_source.endswith(".is_critical"):
                return False
            return None

        # Walk the path
        for part in parts[1:]:
            if obj is None:
                # If we hit None in the middle of the path
                # For binary sensors ending with is_critical, return False
                if data_source.endswith(".is_critical"):
                    return False
                return None
            try:
                # Check if attribute exists and get it
                # hasattr() can trigger property getters that may raise exceptions
                if not hasattr(obj, part):
                    _LOGGER.debug("Attribute %s not found in %s", part, type(obj).__name__)
                    # For binary sensors ending with is_critical, return False
                    if data_source.endswith(".is_critical"):
                        return False
                    return None
                obj = getattr(obj, part)
            except (AttributeError, TypeError, ValueError) as e:
                # Handle various exceptions that can occur during attribute access:
                # - AttributeError: Attribute doesn't exist or getattr fails
                # - TypeError: Property getter receives None when expecting a number
                # - ValueError: Property getter receives invalid data format
                _LOGGER.debug(
                    "Error accessing attribute %s on %s: %s",
                    part,
                    type(obj).__name__,
                    str(e),
                )
                # For binary sensors ending with is_critical, return False
                if data_source.endswith(".is_critical"):
                    return False
                return None

        return obj

    def is_sensor_seasonal(self, data_source: str) -> bool:
        """Check if a winter credit sensor is in season.

        Winter credit sensors should only show data during the winter season.
        This applies ONLY to Portal mode sensors that fetch from contract data.
        OpenData mode sensors (public_client) are always available.
        """
        # OpenData mode sensors using public_client are never seasonal
        if data_source.startswith("public_client."):
            return True

        if "peak_handler" not in data_source or self.rate_option != "CPC":
            return True  # Not a seasonal sensor

        if not self.data or not self.data.get("contract"):
            return False

        contract = self.data["contract"]
        if not isinstance(contract, ContractDCPC) or not contract.peak_handler:
            return False

        today = datetime.date.today()
        winter_start = contract.peak_handler.winter_start_date.date()
        winter_end = contract.peak_handler.winter_end_date.date()

        return winter_start <= today <= winter_end

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

    async def _async_validate_calendar_entity(self) -> bool:
        """Validate calendar entity exists (non-destructive check).

        Returns True if calendar entity is valid, False otherwise.
        Does not disable calendar feature - just reports validation status.
        """
        if not self._calendar_entity_id:
            return False

        # Check if calendar component is loaded
        if "calendar" not in self.hass.config.components:
            _LOGGER.debug("Calendar component not yet loaded")
            return False

        # Check if calendar entity exists in state registry
        calendar_state = self.hass.states.get(self._calendar_entity_id)
        if not calendar_state:
            _LOGGER.debug(
                "Calendar entity %s not found in state registry",
                self._calendar_entity_id,
            )
            return False

        return True

    async def _async_disable_calendar_permanently(self) -> None:
        """Disable calendar feature permanently after validation failures.

        Only called after multiple validation attempts have failed.
        """
        _LOGGER.error(
            "Calendar entity %s failed validation after %d attempts. Disabling calendar sync for %s.",
            self._calendar_entity_id,
            self._calendar_max_validation_attempts,
            self.contract_name,
        )

        # Update entry to remove calendar configuration
        new_data = dict(self.entry.data)
        new_data.pop(CONF_CALENDAR_ENTITY_ID, None)
        new_data.pop(CONF_INCLUDE_NON_CRITICAL_PEAKS, None)

        self.hass.config_entries.async_update_entry(self.entry, data=new_data)

        # Create persistent notification
        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "message": (
                    f"Le calendrier {self._calendar_entity_id} est introuvable après plusieurs tentatives. "
                    f"La synchronisation des événements de pointe a été désactivée pour {self.contract_name}. "
                    f"Vérifiez que le calendrier existe et reconfigurer dans les options de l'intégration."
                ),
                "title": "Hydro-Québec - Calendrier introuvable",
                "notification_id": f"hydroqc_calendar_missing_{self.contract_id}",
            },
        )

        # Clear calendar config
        self._calendar_entity_id = None

    async def _async_sync_calendar_events(self) -> None:
        """Sync peak events to configured calendar entity.

        Only syncs for DPC/DCPC rates when calendar is configured.
        Validates calendar entity with retry logic before disabling.
        """
        if not self._calendar_entity_id:
            _LOGGER.debug(
                "Calendar sync disabled for %s: no calendar entity configured. "
                "Configure via integration options to enable peak event calendar sync.",
                self.contract_name,
            )
            return

        # Only sync for rates that support calendar (DPC/DCPC)
        if self.rate_with_option not in ["DPC", "DCPC"]:
            _LOGGER.debug(
                "Calendar sync not available for rate %s (only DPC/DCPC supported)",
                self.rate_with_option,
            )
            return

        # Validate calendar entity with retry logic
        if not self._calendar_validation_passed:
            is_valid = await self._async_validate_calendar_entity()

            if is_valid:
                self._calendar_validation_passed = True
                _LOGGER.info(
                    "Calendar entity %s validated successfully for %s",
                    self._calendar_entity_id,
                    self.contract_name,
                )
            else:
                self._calendar_validation_attempts += 1

                if self._calendar_validation_attempts >= self._calendar_max_validation_attempts:
                    # Permanently disable after multiple failures
                    await self._async_disable_calendar_permanently()
                    return
                # Log warning but don't disable yet - will retry on next sync
                _LOGGER.warning(
                    "Calendar entity %s validation failed (attempt %d/%d) for %s. Will retry...",
                    self._calendar_entity_id,
                    self._calendar_validation_attempts,
                    self._calendar_max_validation_attempts,
                    self.contract_name,
                )
                return

        # Get peak events from public client
        if not self.public_client.peak_handler or not self.public_client.peak_handler._events:
            _LOGGER.debug("No peak events available for calendar sync")
            return

        peaks = list(self.public_client.peak_handler._events)

        try:
            _LOGGER.debug(
                "Syncing %d peak events to calendar %s for %s",
                len(peaks),
                self._calendar_entity_id,
                self.contract_name,
            )

            # Sync events using calendar manager
            new_uids = await calendar_manager.async_sync_events(
                self.hass,
                self._calendar_entity_id,
                peaks,
                self._created_event_uids,
                self.contract_id,
                self.contract_name,
                self.rate_with_option,
                self._include_non_critical_peaks or False,
            )

            # Update stored UIDs and persist to storage
            self._created_event_uids = new_uids
            await self.async_save_calendar_uids()

            _LOGGER.info(
                "Calendar sync complete for %s: %d events tracked",
                self.contract_name,
                len(new_uids),
            )

        except Exception as err:
            _LOGGER.warning(
                "Failed to sync calendar events for %s: %s",
                self.contract_name,
                err,
            )
