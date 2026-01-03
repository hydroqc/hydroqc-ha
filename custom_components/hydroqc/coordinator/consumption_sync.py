"""Consumption synchronization functionality for HydroQc coordinator."""

# mypy: disable-error-code="attr-defined"

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import TYPE_CHECKING

from homeassistant.util import slugify

from ..const import CONF_CONTRACT_NAME
from ..consumption_history import ConsumptionHistoryImporter
from ..statistics_manager import StatisticsManager

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)


class ConsumptionSyncMixin:
    """Mixin for consumption synchronization functionality."""

    def _init_consumption_sync(self) -> None:
        """Initialize consumption synchronization attributes."""
        # Track if initial sync has completed
        self._initial_sync_done = False

        # Track background CSV import task (for long historical imports)
        self._csv_import_task: asyncio.Task[None] | None = None
        # Track regular sync task (for recent data updates)
        self._regular_sync_task: asyncio.Task[None] | None = None

        # Initialize helper modules (lazy initialization after contract is available)
        self._statistics_manager: StatisticsManager | None = None
        self._history_importer: ConsumptionHistoryImporter | None = None

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

    def _is_near_billing_period_change(self) -> bool:
        """Check if we are within 2-3 days of billing period start or end.

        Known issue: Hydro-Québec portal does not provide consumption data
        2-3 days before and after the end of a billing period.

        Returns:
            bool: True if within 3 days of billing period boundary
        """
        if not self._contract:
            return False

        try:
            today = datetime.date.today()
            period_start = getattr(self._contract, "cp_start_date", None)
            period_end = getattr(self._contract, "cp_end_date", None)

            if period_start is None or period_end is None:
                return False

            # Check if within 3 days before period end
            days_to_end = (period_end - today).days
            if 0 <= days_to_end <= 3:
                return True

            # Check if within 3 days after period start (new period just started)
            days_from_start = (today - period_start).days
            return bool(0 <= days_from_start <= 3)
        except Exception:
            return False

    async def _async_regular_consumption_sync(self) -> None:
        """Regular consumption sync (called hourly from _async_update_data).

        Matches hydroqc2mqtt pattern:
        - First sync: Check last 30 days and fill gaps or trigger CSV import
        - Regular sync: Only sync last 24 hours
        - Skips if CSV import is running or portal is offline
        """
        if not self.is_portal_mode:
            return

        # Check portal status before attempting sync
        if self._webuser:
            try:
                portal_available = await self._webuser.check_hq_portal_status()
                if not portal_available:
                    _LOGGER.warning("[Portal] Portal offline, skipping consumption sync")
                    return
            except Exception as err:
                _LOGGER.warning(
                    "[Portal] Failed to check portal status: %s, skipping consumption sync", err
                )
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
            # Check if error might be due to billing period change
            if self._is_near_billing_period_change():
                _LOGGER.warning(
                    "[Portal] Error during consumption sync (near billing period boundary, "
                    "consumption data may be temporarily unavailable): %s",
                    err,
                )
            else:
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
            # Check if error might be due to billing period change
            if self._is_near_billing_period_change():
                _LOGGER.warning(
                    "[Portal] Error during initial consumption sync (near billing period boundary, "
                    "consumption data may be temporarily unavailable): %s",
                    err,
                )
            else:
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
