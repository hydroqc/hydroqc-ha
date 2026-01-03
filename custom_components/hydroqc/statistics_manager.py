"""Statistics management for Hydro-Québec integration."""

from __future__ import annotations

import asyncio
import datetime
import logging
import zoneinfo
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from homeassistant.components.recorder import get_instance, statistics  # type: ignore[attr-defined]
from homeassistant.components.recorder.models import StatisticMeanType
from homeassistant.helpers.update_coordinator import UpdateFailed

from hydroqc.error import HydroQcHTTPError

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from hydroqc.contract.common import Contract

_LOGGER = logging.getLogger(__name__)


class StatisticsManager:
    """Manages statistics queries and hourly consumption imports."""

    def __init__(
        self,
        hass: HomeAssistant,
        contract: Contract | None,
        rate: str,
        get_statistic_id_func: Callable[[str], str],
        contract_name: str = "home",
    ) -> None:
        """Initialize the statistics manager.

        Args:
            hass: Home Assistant instance
            contract: Hydro-Québec contract object
            rate: Rate code (D, DT, DPC, M, etc.)
            get_statistic_id_func: Function to get statistic_id for consumption type
            contract_name: Friendly name of the contract for display
        """
        self.hass = hass
        self._contract = contract
        self._rate = rate
        self._get_statistic_id = get_statistic_id_func
        self._contract_name = contract_name

    async def determine_sync_start_date(  # noqa: PLR0911, PLR0915
        self,
    ) -> tuple[bool, datetime.date | None]:
        """Determine the start date for syncing consumption data.

        Logic:
        1. Query last 30 days for statistics
        2. No statistics found → Return (True, None) to trigger 30-day regular sync
        3. Statistics found → Check first day coverage:
           - First day has NO data (state = 0) → Return (True, None) to trigger 30-day regular sync
           - First day has data → Check for corruption and gaps
           - Find most recent valid state > 0
           - Return (False, next_day) for incremental sync or (False, None) if up to date

        Returns:
            Tuple of (needs_initial_sync: bool, sync_start_date: date | None)
            - (True, None): No statistics or first day empty, trigger 30-day regular sync
            - (False, date): Statistics found, sync incrementally from this date
            - (False, None): Statistics are up to date, no action needed
        """
        try:
            # Check last 30 days for existing statistics
            today = datetime.date.today()
            thirty_days_ago = today - datetime.timedelta(days=30)
            tz = zoneinfo.ZoneInfo("America/Toronto")

            statistic_id = self._get_statistic_id("total")

            all_stats = await get_instance(self.hass).async_add_executor_job(
                statistics.statistics_during_period,
                self.hass,
                datetime.datetime.combine(thirty_days_ago, datetime.time.min).replace(tzinfo=tz),
                datetime.datetime.combine(today, datetime.time.max).replace(tzinfo=tz),
                {statistic_id},
                "hour",
                None,
                {"sum", "state"},
            )

            if not all_stats or statistic_id not in all_stats or not all_stats[statistic_id]:
                _LOGGER.info(
                    "No existing statistics found in last 30 days → Will sync last 30 days"
                )
                return (True, None)

            stats_list = all_stats[statistic_id]
            _LOGGER.debug("Found %d statistics in last 30 days", len(stats_list))

            # Check first day - if it has no data (state = 0), sync last 30 days
            first_stat = stats_list[0]
            first_state = first_stat.get("state", 0)
            first_sum = first_stat.get("sum", 0)

            # Convert first stat time for logging
            first_stat_time = first_stat["start"]
            first_date = datetime.datetime.fromtimestamp(first_stat_time, tz=datetime.UTC).date()

            _LOGGER.debug(
                "First day check: date=%s, state=%.2f kWh, sum=%.2f kWh",
                first_date.isoformat(),
                first_state,
                first_sum,
            )

            if first_state == 0:
                _LOGGER.info("First day has no data (state = 0) → Will sync last 30 days")
                return (True, None)

            # We have data - now check for corruption and find last valid date
            last_valid_stat = None
            corruption_index = None

            _LOGGER.debug("Checking for data corruption (decreasing sum)...")

            for i, stat in enumerate(stats_list):
                stat_state = stat.get("state", 0)
                stat_sum = stat.get("sum", 0)

                # Check for corruption: decreasing sum
                if i > 0:
                    prev_sum = stats_list[i - 1].get("sum", 0)
                    if prev_sum is not None and stat_sum is not None and stat_sum < prev_sum:
                        _LOGGER.warning(
                            "Detected decreasing sum at index %d (sum: %.2f → %.2f). "
                            "Will sync from day before corruption.",
                            i,
                            prev_sum,
                            stat_sum,
                        )
                        corruption_index = i
                        break

                    # Log progress every 24 hours (every 24 stats)
                    if i % 24 == 0:
                        _LOGGER.debug(
                            "Corruption check progress: %d/%d statistics checked (sum: %.2f kWh)",
                            i,
                            len(stats_list),
                            stat_sum,
                        )

                # Track last valid data point (state > 0)
                if stat_state is not None and stat_state > 0:
                    last_valid_stat = stat

            if corruption_index is None:
                _LOGGER.debug("No data corruption detected in %d statistics", len(stats_list))

            # If corruption found, sync from the day before corruption
            if corruption_index is not None and corruption_index > 0:
                corrupted_stat = stats_list[corruption_index - 1]
                corrupted_stat_time = corrupted_stat["start"]

                corrupted_date = datetime.datetime.fromtimestamp(
                    corrupted_stat_time, tz=datetime.UTC
                ).date()

                _LOGGER.info(
                    "Syncing from day before corruption: %s",
                    corrupted_date.isoformat(),
                )
                return (False, corrupted_date)

            if not last_valid_stat:
                _LOGGER.info("No valid data found (all states = 0) → Will sync last 30 days")
                return (True, None)

            # Convert timestamp to date
            last_stat_time = last_valid_stat["start"]

            # Home Assistant returns timestamps in seconds (Unix epoch)
            last_date = datetime.datetime.fromtimestamp(last_stat_time, tz=datetime.UTC).date()

            sync_start = last_date + datetime.timedelta(days=1)

            # Don't sync if we're already up to date
            if sync_start >= today:
                _LOGGER.info("Statistics already up to date (last valid: %s)", last_date)
                return (False, None)

            _LOGGER.info(
                "Found valid statistics up to %s (state: %.2f kWh, sum: %.2f kWh) → Incremental sync from %s",
                last_date,
                last_valid_stat.get("state", 0),
                last_valid_stat.get("sum", 0),
                sync_start,
            )

            return (False, sync_start)

        except Exception as err:
            _LOGGER.error("Error determining sync start date: %s", err, exc_info=True)
            # On error, trigger CSV import to be safe
            return (True, None)

    async def fetch_and_import_hourly_consumption(
        self, start_date: datetime.date, end_date: datetime.date
    ) -> None:
        """Fetch hourly consumption data and import to Home Assistant energy dashboard.

        Uses recorder API to import statistics directly into HA energy dashboard.

        Args:
            start_date: Start date for fetch
            end_date: End date for fetch
        """
        if not self._contract:
            _LOGGER.warning("Contract not initialized")
            return

        try:
            # Determine consumption types based on rate
            consumption_types = self._get_consumption_types()

            tz = zoneinfo.ZoneInfo("America/Toronto")
            current_date = start_date

            # Fetch and import data for each day in range
            while current_date <= end_date:
                try:
                    _LOGGER.info("Fetching hourly consumption for %s", current_date)

                    # Get hourly data for this specific date
                    hourly_data = await self._contract.get_hourly_consumption(current_date)

                    hourly_list = hourly_data["results"].get("listeDonneesConsoEnergieHoraire", [])
                    if not hourly_list:
                        _LOGGER.debug("Empty hourly consumption list for %s", current_date)
                        current_date += datetime.timedelta(days=1)
                        continue

                    # Process each consumption type
                    await self._process_day_consumption(
                        current_date,
                        hourly_list,  # type: ignore[arg-type]
                        consumption_types,
                        tz,
                    )

                    current_date += datetime.timedelta(days=1)

                    # Yield control to event loop to allow HA to process other tasks
                    await asyncio.sleep(0)

                except HydroQcHTTPError as err:
                    # Expected error for dates without data (e.g., today, future dates)
                    if "No data available for date" in str(err):
                        _LOGGER.debug(
                            "No consumption data available for %s (data not yet published by HQ)",
                            current_date,
                        )
                    else:
                        _LOGGER.error(
                            "HTTP error fetching consumption for %s: %s", current_date, err
                        )
                    current_date += datetime.timedelta(days=1)

                except Exception as err:
                    _LOGGER.exception(
                        "Failed to fetch/import consumption for %s: %s",
                        current_date,
                        err,
                    )
                    current_date += datetime.timedelta(days=1)
                    continue

            _LOGGER.info(
                "Completed hourly consumption sync from %s to %s",
                start_date,
                end_date,
            )

        except Exception as err:
            _LOGGER.exception("Error fetching hourly consumption")
            raise UpdateFailed(f"Failed to fetch hourly consumption: {err}") from err

    def _get_consumption_types(self) -> list[str]:
        """Get consumption types based on rate."""
        if self._rate in {"DT", "DPC"}:
            # Dual tariff rates have reg, haut, and total
            return ["total", "reg", "haut"]
        # Single tariff rates only have total
        return ["total"]

    def build_statistics_metadata(self, consumption_type: str) -> dict[str, Any]:
        """Build metadata for statistics import.

        Args:
            consumption_type: Type of consumption (total, reg, haut)

        Returns:
            Metadata dictionary for statistics import
        """
        statistic_id = self._get_statistic_id(consumption_type)
        # Include contract name in display name for clarity
        display_name = (
            f"{self._contract_name.title()} {consumption_type.capitalize()} Hourly Consumption"
        )
        return {
            "source": "hydroqc",
            "statistic_id": statistic_id,
            "unit_of_measurement": "kWh",
            "has_mean": False,
            "has_sum": True,
            "mean_type": StatisticMeanType.NONE,
            "name": display_name,
            "unit_class": "energy",
        }

    async def get_base_sum(self, consumption_type: str, reference_date: datetime.date) -> float:
        """Get the last cumulative sum for a consumption type.

        Queries statistics for the reference date and returns the last known sum.
        This maintains continuity when importing new statistics.
        If no data is found on reference_date, it will look back up to 30 days.

        Args:
            consumption_type: Type of consumption (total, reg, haut)
            reference_date: Date to query (typically yesterday)

        Returns:
            Last cumulative sum, or 0.0 if no previous statistics found
        """
        statistic_id = self._get_statistic_id(consumption_type)
        tz = zoneinfo.ZoneInfo("America/Toronto")

        # Try to find last stat, looking back up to 30 days
        for i in range(30):
            current_date = reference_date - datetime.timedelta(days=i)
            start_datetime = datetime.datetime.combine(current_date, datetime.time.min).replace(
                tzinfo=tz
            )
            end_datetime = datetime.datetime.combine(current_date, datetime.time.max).replace(
                tzinfo=tz
            )

            try:
                last_stats = await get_instance(self.hass).async_add_executor_job(
                    statistics.statistics_during_period,
                    self.hass,
                    start_datetime,
                    end_datetime,
                    {statistic_id},
                    "hour",
                    None,
                    {"sum"},
                )

                if last_stats and statistic_id in last_stats and last_stats[statistic_id]:
                    stats_for_id = last_stats[statistic_id]
                    if stats_for_id:
                        base_sum = stats_for_id[-1]["sum"]
                        _LOGGER.debug(
                            "Found base sum %.2f kWh for %s from %s (looked back %d days)",
                            base_sum,
                            consumption_type,
                            current_date,
                            i,
                        )
                        return float(base_sum) if base_sum is not None else 0.0
            except Exception as err:
                _LOGGER.debug(
                    "No previous statistics found for %s on %s: %s",
                    consumption_type,
                    current_date,
                    err,
                )

        _LOGGER.warning(
            "Could not find any statistics for %s in the last 30 days (from %s). Starting sum at 0.",
            consumption_type,
            reference_date,
        )
        return 0.0

    async def _process_day_consumption(
        self,
        current_date: datetime.date,
        hourly_list: list[dict[str, Any]],
        consumption_types: list[str],
        tz: zoneinfo.ZoneInfo,
    ) -> None:
        """Process and import consumption for a single day.

        Args:
            current_date: Date being processed
            hourly_list: List of hourly consumption data from API
            consumption_types: List of consumption types to process
            tz: Timezone for datetime objects
        """
        for consumption_type in consumption_types:
            # Get last known sum from yesterday
            yesterday = current_date - datetime.timedelta(days=1)
            base_sum = await self.get_base_sum(consumption_type, yesterday)

            # Build statistics list for today
            stats_list = []
            cumulative_sum = base_sum

            for hour_data in hourly_list:
                # Parse hour time (format: "HH:MM:SS")
                hour_str = hour_data["heure"]
                hour_parts = [int(p) for p in hour_str.split(":")]
                hour_time = datetime.time(hour_parts[0], hour_parts[1], hour_parts[2])

                # Create timezone-aware datetime
                hour_datetime = datetime.datetime.combine(current_date, hour_time)
                hour_datetime_tz = hour_datetime.replace(tzinfo=tz)

                # Get consumption value for this type
                consumption_key = f"conso{consumption_type.capitalize()}"
                consumption_kwh = hour_data.get(consumption_key, 0.0)

                # Update cumulative sum
                cumulative_sum += consumption_kwh

                stats_list.append(
                    {
                        "start": hour_datetime_tz,
                        "state": consumption_kwh,
                        "sum": round(cumulative_sum, 2),
                    }
                )

            # Import statistics using recorder API
            if stats_list:
                metadata = self.build_statistics_metadata(consumption_type)

                await get_instance(self.hass).async_add_executor_job(
                    statistics.async_add_external_statistics,
                    self.hass,
                    metadata,
                    stats_list,
                )

                _LOGGER.info(
                    "Imported %d hourly statistics for %s on %s (sum: %.2f kWh)",
                    len(stats_list),
                    consumption_type,
                    current_date,
                    cumulative_sum,
                )
