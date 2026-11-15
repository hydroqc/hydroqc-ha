"""Statistics management for Hydro-Québec integration."""

from __future__ import annotations

import asyncio
import datetime
import logging
import zoneinfo
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from homeassistant.components.recorder import history as recorder_history, statistics
from homeassistant.components.recorder.models import StatisticMeanType
from homeassistant.helpers.recorder import get_instance
from homeassistant.helpers.update_coordinator import UpdateFailed

from hydroqc.error import HydroQcHTTPError

from .const import TARIF_D_HISTORY_PERIOD_DAYS
from .tarif_d_split import PeriodLookup, TarifDSplitter

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
        *,
        billing_duration_entity: str | None = None,
    ) -> None:
        """Initialize the statistics manager.

        Args:
            hass: Home Assistant instance
            contract: Hydro-Québec contract object
            rate: Rate code (D, DT, DPC, M, etc.)
            get_statistic_id_func: Function to get statistic_id for consumption type
            contract_name: Friendly name of the contract for display
            billing_duration_entity: Optional entity_id of a sensor tracking billing
                period duration in days. Used for accurate historical re-splitting
                of Tarif D consumption into reg/haut streams. Falls back to
                TARIF_D_HISTORY_PERIOD_DAYS if not provided.
        """
        self.hass = hass
        self._contract = contract
        self._rate = rate
        self._get_statistic_id = get_statistic_id_func
        self._contract_name = contract_name
        self._billing_duration_entity = billing_duration_entity

    async def determine_sync_start_date(
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
            # Dual tariff rates have reg, haut, and total (from API)
            return ["total", "reg", "haut"]
        if self._rate == "D":
            # Tarif D: total from API + reg/haut computed from 40 kWh/day threshold
            return ["total", "reg", "haut"]
        # Other single tariff rates only have total
        return ["total"]

    async def _get_period_consumption_before_date(
        self,
        statistic_id: str,
        target_date: datetime.date,
        period_start: Any,
    ) -> float:
        """Get cumulative total consumption from billing period start up to (not including) target_date.

        Used to calculate how much of the 40 kWh/day threshold has already been
        consumed before the current day being processed.

        Args:
            statistic_id: The total consumption statistic ID to query
            target_date: The date we are processing (exclusive)
            period_start: Billing period start date (from contract.cp_start_date)

        Returns:
            Total kWh consumed since billing period start, or 0.0 if unavailable
        """
        tz = zoneinfo.ZoneInfo("America/Toronto")

        # Determine start of billing period
        if period_start is not None:
            try:
                if isinstance(period_start, datetime.date):
                    start_date = period_start
                else:
                    start_date = datetime.date.fromisoformat(str(period_start))
            except (ValueError, TypeError):
                start_date = target_date - datetime.timedelta(days=60)
        else:
            start_date = target_date - datetime.timedelta(days=60)

        if start_date >= target_date:
            return 0.0

        try:
            start_dt = datetime.datetime.combine(start_date, datetime.time.min).replace(tzinfo=tz)
            end_dt = datetime.datetime.combine(
                target_date - datetime.timedelta(days=1), datetime.time.max
            ).replace(tzinfo=tz)

            stats = await get_instance(self.hass).async_add_executor_job(
                statistics.statistics_during_period,
                self.hass,
                start_dt,
                end_dt,
                {statistic_id},
                "hour",
                None,
                {"state"},
            )

            if not stats or statistic_id not in stats:
                return 0.0

            return float(sum(s.get("state", 0.0) or 0.0 for s in stats[statistic_id]))

        except Exception as err:
            _LOGGER.debug("Could not get period consumption before %s: %s", target_date, err)
            return 0.0

    async def resplit_tarif_d_history(self) -> None:
        """Re-split existing Tarif D total statistics into reg/haut streams.

        Called once when the feature is first enabled (or manually via service).
        Reads the existing total hourly statistics and splits them into:
          - reg: consumption within the 40 kWh/day x billing_period_days threshold
          - haut: consumption beyond the threshold

        The total stream is left untouched as a rollback safety net.

        Billing period durations are sourced from:
          1. The configured billing_duration_entity recorder history (most accurate)
          2. TARIF_D_HISTORY_PERIOD_DAYS (60 days) as fallback approximation
        """
        _LOGGER.warning(
            "Tarif D historical re-split STARTING — processing up to 800 days of hourly data. "
            "This may take several minutes. The total stream will not be modified."
        )
        tz = zoneinfo.ZoneInfo("America/Toronto")

        total_statistic_id = self._get_statistic_id("total")

        # Query all existing total statistics (up to 800 days back)
        today = datetime.datetime.now(tz).date()
        start_dt = datetime.datetime.combine(
            today - datetime.timedelta(days=800), datetime.time.min
        ).replace(tzinfo=tz)
        end_dt = datetime.datetime.combine(today, datetime.time.max).replace(tzinfo=tz)

        try:
            all_stats = await get_instance(self.hass).async_add_executor_job(
                statistics.statistics_during_period,
                self.hass,
                start_dt,
                end_dt,
                {total_statistic_id},
                "hour",
                None,
                {"state", "sum"},
            )
        except Exception as err:
            _LOGGER.error("Failed to query existing statistics for re-split: %s", err)
            return

        if not all_stats or total_statistic_id not in all_stats:
            _LOGGER.warning("No existing total statistics found for Tarif D re-split")
            return

        stats_list = all_stats[total_statistic_id]
        _LOGGER.info("Found %d hourly records to re-split", len(stats_list))

        # Get billing period durations from entity recorder history if available
        period_durations = await self._get_billing_period_durations(today)
        if not period_durations:
            _LOGGER.warning(
                "No billing period history found — using %d-day approximation",
                TARIF_D_HISTORY_PERIOD_DAYS,
            )

        # Process each hour and assign to reg or haut
        reg_stats: list[dict[str, Any]] = []
        haut_stats: list[dict[str, Any]] = []

        reg_cumulative = 0.0
        haut_cumulative = 0.0

        # One splitter for the whole history: it restarts the allowance whenever
        # an hour falls in a new billing period.
        splitter = TarifDSplitter(self.build_period_lookup(period_durations))

        for stat in stats_list:
            stat_dt = datetime.datetime.fromtimestamp(stat["start"], tz=datetime.UTC)
            stat_date = stat_dt.astimezone(tz).date()
            kwh = float(stat.get("state", 0.0) or 0.0)

            reg_kwh, haut_kwh = splitter.split(stat_date, kwh)

            reg_cumulative += reg_kwh
            haut_cumulative += haut_kwh

            stat_dt_local = stat_dt.astimezone(tz)
            reg_stats.append(
                {
                    "start": stat_dt_local,
                    "state": reg_kwh,
                    "sum": round(reg_cumulative, 2),
                }
            )
            haut_stats.append(
                {
                    "start": stat_dt_local,
                    "state": haut_kwh,
                    "sum": round(haut_cumulative, 2),
                }
            )

        # Import reg and haut streams
        for consumption_type, stats in [("reg", reg_stats), ("haut", haut_stats)]:
            if not stats:
                continue
            metadata = self.build_statistics_metadata(consumption_type)
            BATCH_SIZE = 168
            total_batches = (len(stats) + BATCH_SIZE - 1) // BATCH_SIZE
            for i in range(total_batches):
                batch = stats[i * BATCH_SIZE : (i + 1) * BATCH_SIZE]
                await get_instance(self.hass).async_add_executor_job(
                    statistics.async_add_external_statistics,
                    self.hass,
                    metadata,
                    batch,
                )
                _LOGGER.info(
                    "Re-split: imported batch %d/%d for %s (%d records)",
                    i + 1,
                    total_batches,
                    consumption_type,
                    len(batch),
                )
                await asyncio.sleep(0.5)

        _LOGGER.warning(
            "Tarif D historical re-split COMPLETE — %d low price records, "
            "%d high price records imported. Add 'Low Price Hourly Consumption' "
            "and 'High Price Hourly Consumption' streams to your energy dashboard.",
            len(reg_stats),
            len(haut_stats),
        )

    async def _get_billing_period_durations(self, today: datetime.date) -> dict[datetime.date, int]:
        """Query recorder history of the billing duration entity.

        Returns a dict mapping period_start_date → duration_days.
        Falls back to empty dict if no entity configured or no history found.
        """
        entity_id = self._billing_duration_entity
        if not entity_id:
            _LOGGER.debug(
                "No billing_duration_entity configured — using %d-day approximation for history",
                TARIF_D_HISTORY_PERIOD_DAYS,
            )
            return {}

        tz = zoneinfo.ZoneInfo("America/Toronto")

        _LOGGER.info("Querying recorder history of %s for billing period durations", entity_id)

        try:
            start_dt = datetime.datetime.combine(
                today - datetime.timedelta(days=800), datetime.time.min
            ).replace(tzinfo=tz)

            states = await get_instance(self.hass).async_add_executor_job(
                recorder_history.state_changes_during_period,
                self.hass,
                start_dt,
                None,
                entity_id,
                True,
                False,
                None,
            )

            if not states or entity_id not in states:
                _LOGGER.warning(
                    "No history found for %s — using %d-day approximation",
                    entity_id,
                    TARIF_D_HISTORY_PERIOD_DAYS,
                )
                return {}

            # Build period map from state changes
            # Each unique duration value marks a new billing period
            period_map: dict[datetime.date, int] = {}
            prev_duration: int | None = None
            prev_date: datetime.date | None = None

            for state in states[entity_id]:
                try:
                    duration = int(float(state.state))
                except (ValueError, TypeError):
                    continue

                state_date = state.last_changed.astimezone(tz).date()

                if duration != prev_duration:
                    # Duration changed — new billing period started
                    if prev_date is not None:
                        period_map[prev_date] = prev_duration  # type: ignore[assignment]
                    prev_date = state_date
                    prev_duration = duration

            # Add last period
            if prev_date is not None and prev_duration is not None:
                period_map[prev_date] = prev_duration

            _LOGGER.info(
                "Found %d billing periods from %s history",
                len(period_map),
                entity_id,
            )
            return period_map

        except Exception as err:
            _LOGGER.error(
                "Failed to query billing duration history from %s: %s — using approximation",
                entity_id,
                err,
            )
            return {}

    def _get_period_start_for_date(
        self,
        date: datetime.date,
        period_durations: dict[datetime.date, int],
    ) -> datetime.date | None:
        """Find the billing period start date for a given date.

        Args:
            date: The date to look up
            period_durations: Dict of period_start → duration_days

        Returns:
            The period start date, or None if not found
        """
        if not period_durations:
            # No period data — use fixed 60-day blocks from a reference point
            # Use 2020-01-01 as arbitrary reference and compute block
            ref = datetime.date(2020, 1, 1)
            days_since_ref = (date - ref).days
            block = days_since_ref // TARIF_D_HISTORY_PERIOD_DAYS
            return ref + datetime.timedelta(days=block * TARIF_D_HISTORY_PERIOD_DAYS)

        # Find the period that contains this date
        sorted_starts = sorted(period_durations.keys())

        # Check if date falls within a known period
        for start in sorted_starts:
            duration = period_durations[start]
            end = start + datetime.timedelta(days=duration)
            if start <= date < end:
                return start

        # Date is before all known periods — extrapolate backwards
        # using 60-day approximation anchored to the oldest known period
        oldest_known = sorted_starts[0]
        if date < oldest_known:
            days_before = (oldest_known - date).days
            blocks_before = (
                days_before + TARIF_D_HISTORY_PERIOD_DAYS - 1
            ) // TARIF_D_HISTORY_PERIOD_DAYS
            return oldest_known - datetime.timedelta(
                days=blocks_before * TARIF_D_HISTORY_PERIOD_DAYS
            )

        # Date is after all known periods — return the last known period start
        return sorted_starts[-1]

    def build_statistics_metadata(self, consumption_type: str) -> dict[str, Any]:
        """Build metadata for statistics import.

        Args:
            consumption_type: Type of consumption (total, reg, haut)

        Returns:
            Metadata dictionary for statistics import
        """
        statistic_id = self._get_statistic_id(consumption_type)
        # For Tarif D, use meaningful Low/High Price names instead of Reg/Haut
        # For DT/DPC, keep Reg/Haut for backward compatibility with existing dashboards
        if self._rate == "D":
            type_label = {
                "reg": "Low Price",
                "haut": "High Price",
                "total": "Total",
            }.get(consumption_type, consumption_type.capitalize())
        else:
            type_label = consumption_type.capitalize()
        display_name = f"{self._contract_name.title()} {type_label} Hourly Consumption"
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

    def _current_period(self) -> tuple[datetime.date, int] | None:
        """Return the contract's current billing period as (start date, days), if known."""
        contract = self._contract
        if contract is None:
            return None
        start = getattr(contract, "cp_start_date", None)
        duration = getattr(contract, "cp_duration", None)
        if not start or not duration:
            return None
        try:
            if isinstance(start, datetime.datetime):
                start = start.date()
            elif not isinstance(start, datetime.date):
                start = datetime.date.fromisoformat(str(start))
            return start, int(duration)
        except (ValueError, TypeError):
            return None

    def build_period_lookup(self, period_durations: dict[datetime.date, int]) -> PeriodLookup:
        """Return a function giving (period start, period days) for any calendar day.

        Uses ``period_durations`` (from the billing duration sensor history) when
        available. Without it, the contract's current period is used as the anchor
        and earlier periods are approximated backwards from it in blocks of
        TARIF_D_HISTORY_PERIOD_DAYS, so a day that belongs to the previous period
        is never mistaken for the start of a fresh allowance.
        """
        durations = dict(period_durations)
        if not durations:
            current = self._current_period()
            if current is not None:
                durations[current[0]] = current[1]

        def lookup(day: datetime.date) -> tuple[datetime.date, int]:
            start = self._get_period_start_for_date(day, durations)
            if start is None:
                return day, TARIF_D_HISTORY_PERIOD_DAYS
            return start, durations.get(start, TARIF_D_HISTORY_PERIOD_DAYS)

        return lookup

    async def _split_day_for_tarif_d(
        self,
        day: datetime.date,
        hourly_list: list[dict[str, Any]],
        consumption_type: str,
        tz: zoneinfo.ZoneInfo,
    ) -> list[dict[str, Any]]:
        """Build the reg or haut statistics of one day from its total consumption."""
        lookup = self.build_period_lookup({})
        period_start, _ = lookup(day)

        # How much of the period's allowance was used before this day started
        consumed_before = await self._get_period_consumption_before_date(
            self._get_statistic_id("total"), day, period_start
        )
        splitter = TarifDSplitter(lookup, consumed_before)
        cumulative = await self.get_base_sum(consumption_type, day - datetime.timedelta(days=1))

        stats: list[dict[str, Any]] = []
        for hour_data in hourly_list:
            hour_parts = [int(p) for p in hour_data["heure"].split(":")]
            hour_start = datetime.datetime.combine(
                day, datetime.time(hour_parts[0], hour_parts[1], hour_parts[2])
            ).replace(tzinfo=tz)
            reg, haut = splitter.split(day, float(hour_data.get("consoTotal", 0.0) or 0.0))
            value = reg if consumption_type == "reg" else haut
            cumulative += value
            stats.append({"start": hour_start, "state": value, "sum": round(cumulative, 2)})
        return stats

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

            # For Tarif D, derive reg/haut from the total using the billing period allowance
            if self._rate == "D" and consumption_type in {"reg", "haut"}:
                stats_list = await self._split_day_for_tarif_d(
                    current_date, hourly_list, consumption_type, tz
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
