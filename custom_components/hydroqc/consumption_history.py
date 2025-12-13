"""Consumption history CSV import logic for Hydro-Québec integration."""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import logging
import zoneinfo
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from homeassistant.components.recorder import get_instance, statistics  # type: ignore[attr-defined]
from homeassistant.core import HomeAssistant

if TYPE_CHECKING:
    from hydroqc.contract.common import Contract

    from .statistics_manager import StatisticsManager

_LOGGER = logging.getLogger(__name__)
# Create timezone once at module level to avoid blocking I/O in event loop
_TIMEZONE_TORONTO = zoneinfo.ZoneInfo("America/Toronto")


class ConsumptionHistoryImporter:
    """Handles CSV import of historical consumption data."""

    def __init__(
        self,
        hass: HomeAssistant,
        contract: Contract,
        rate: str,
        get_statistic_id_func: Callable[[str], str],
        statistics_manager: StatisticsManager,
    ) -> None:
        """Initialize the consumption history importer.

        Args:
            hass: Home Assistant instance
            contract: Hydro-Québec contract object
            rate: Rate code (D, DT, DPC, M, etc.)
            get_statistic_id_func: Function to get statistic_id for consumption type
            statistics_manager: StatisticsManager instance for shared utilities
        """
        self.hass = hass
        self._contract = contract
        self._rate = rate
        self._get_statistic_id = get_statistic_id_func
        self._statistics_manager = statistics_manager

    async def import_csv_history(self, days_back: int) -> None:  # noqa: PLR0912, PLR0915
        """Import historical consumption data from CSV using iterative approach.

        Process:
        1. Set start_date to days_back ago, end_date to yesterday
        2. Request CSV data from start_date to now
        3. Parse and import the CSV data
        4. Use last date in CSV to set start_date for next iteration
        5. Loop until we have yesterday's data

        Args:
            days_back: Number of days back to import (default 731 = ~2 years)
        """
        try:
            if not self._contract:
                _LOGGER.warning("Contract not initialized")
                return

            # Calculate date range: days_back ago to yesterday
            today = datetime.date.today()
            yesterday = today - datetime.timedelta(days=1)
            current_start_date = today - datetime.timedelta(days=days_back)

            # Try to get contract start date
            contract_start_date = None
            if hasattr(self._contract, "start_date") and self._contract.start_date:
                with contextlib.suppress(ValueError, TypeError):
                    contract_start_date = datetime.date.fromisoformat(
                        str(self._contract.start_date)
                    )

            # Use the more recent date (contract start or days_back)
            if contract_start_date and contract_start_date > current_start_date:
                current_start_date = contract_start_date
                _LOGGER.info(
                    "CSV import: Using contract start date %s (newer than %d days ago)",
                    current_start_date,
                    days_back,
                )

            _LOGGER.info(
                "CSV import: Starting iterative import from %s to %s (%d days)",
                current_start_date,
                yesterday,
                (yesterday - current_start_date).days,
            )

            # Determine consumption types based on rate
            consumption_types = self._statistics_manager._get_consumption_types()

            iteration = 0
            total_rows_imported = 0

            # Loop until we have data up to yesterday
            while current_start_date <= yesterday:
                iteration += 1
                _LOGGER.info(
                    "CSV import: Iteration %d - Requesting data from %s to now",
                    iteration,
                    current_start_date,
                )

                try:
                    # Step 1: Request CSV data from current_start_date to now
                    _LOGGER.debug(
                        "[PORTAL REQUEST] Iteration %d: Requesting CSV from %s to %s (%d days)",
                        iteration,
                        current_start_date,
                        today,
                        (today - current_start_date).days,
                    )

                    csv_data_raw = await self._contract.get_hourly_energy(current_start_date, today)
                    csv_data = list(csv_data_raw)

                    if len(csv_data) <= 1:  # Only header or empty
                        _LOGGER.warning(
                            "[PORTAL RESPONSE] Iteration %d: No data (from %s), advancing 30 days",
                            iteration,
                            current_start_date,
                        )
                        # Increment start date by 30 days and try again
                        current_start_date += datetime.timedelta(days=30)

                        # Safety check: don't go past yesterday
                        if current_start_date > yesterday:
                            _LOGGER.warning("[PORTAL RESPONSE] No data in range, giving up")
                            break

                        # Continue to next iteration
                        continue

                    data_rows = len(csv_data) - 1  # Exclude header

                    # Get date range from received CSV
                    first_row = csv_data[1] if len(csv_data) > 1 else None
                    last_row = csv_data[-1]

                    first_date_str = (
                        str(first_row[1]) if first_row and len(first_row) > 1 else "unknown"
                    )
                    last_date_str = (
                        str(last_row[1]) if last_row and len(last_row) > 1 else "unknown"
                    )

                    _LOGGER.info(
                        "[PORTAL RESPONSE] Iteration %d: Got %d rows (first: %s, last: %s)",
                        iteration,
                        data_rows,
                        first_date_str,
                        last_date_str,
                    )

                    # Step 2: Parse CSV and import to statistics database
                    _LOGGER.debug(
                        "[CSV PARSE] Iteration %d: Parsing %d rows for types: %s",
                        iteration,
                        data_rows,
                        ", ".join(consumption_types),
                    )

                    stats_by_type = self._parse_csv_data(
                        csv_data,
                        consumption_types,
                    )

                    _LOGGER.debug(
                        "[RECORDER IMPORT] Iteration %d: Importing to Home Assistant recorder",
                        iteration,
                    )

                    await self._import_statistics(
                        stats_by_type, current_start_date, consumption_types
                    )

                    total_rows_imported += data_rows

                    # Step 3: CSV is reversed (newest first, oldest last)
                    # - First row (after header) = newest/latest date
                    # - Last row = oldest date
                    # Check first row to see if we've reached yesterday (target)
                    first_data_row = csv_data[1] if len(csv_data) > 1 else None
                    last_data_row = csv_data[-1]

                    if isinstance(first_data_row, list) and len(first_data_row) > 1:
                        try:
                            # Get newest date (first row) to check if we've reached yesterday
                            newest_date_str = str(first_data_row[1])
                            newest_datetime = datetime.datetime.strptime(
                                newest_date_str, "%Y-%m-%d %H:%M:%S"
                            )
                            newest_date_in_csv = newest_datetime.date()

                            # Get oldest date (last row) for next iteration's start_date
                            oldest_date_str = str(last_data_row[1])
                            oldest_datetime = datetime.datetime.strptime(
                                oldest_date_str, "%Y-%m-%d %H:%M:%S"
                            )
                            oldest_date_in_csv = oldest_datetime.date()

                            _LOGGER.info(
                                "CSV import: Iteration %d - Date range: %s (oldest) to %s (newest)",
                                iteration,
                                oldest_date_in_csv,
                                newest_date_in_csv,
                            )

                            # Step 4: Check if we have yesterday's data (check newest date)
                            if newest_date_in_csv >= yesterday:
                                _LOGGER.info(
                                    "CSV import: Completed - Have data up to %s (target: %s)",
                                    newest_date_in_csv,
                                    yesterday,
                                )
                                break

                            # Set next iteration's start_date to day after newest date in CSV
                            current_start_date = newest_date_in_csv + datetime.timedelta(days=1)

                        except ValueError as e:
                            _LOGGER.error("CSV import: Could not parse dates in CSV: %s", e)
                            break
                    else:
                        _LOGGER.error("CSV import: Invalid row format in CSV data")
                        break

                    # Yield control to event loop to keep HA responsive
                    await asyncio.sleep(0.1)

                except Exception as e:
                    _LOGGER.error(
                        "CSV import: Error in iteration %d (from %s): %s",
                        iteration,
                        current_start_date,
                        e,
                        exc_info=True,
                    )
                    break

            _LOGGER.info(
                "CSV import: Completed %d iteration(s), imported %d total rows",
                iteration,
                total_rows_imported,
            )

        except asyncio.CancelledError:
            _LOGGER.info("CSV consumption history import cancelled")
            raise
        except Exception as err:
            _LOGGER.error("Error importing CSV consumption history: %s", err, exc_info=True)

    def _parse_csv_data(
        self, csv_data: list[Sequence[Any]], consumption_types: list[str]
    ) -> dict[str, list[dict[str, Any]]]:
        """Parse CSV data and build statistics per consumption type.

        Args:
            csv_data: Raw CSV data from Hydro-Québec API
            consumption_types: List of consumption types to process

        Returns:
            Dictionary mapping consumption type to list of statistics
        """
        # Use module-level timezone to avoid blocking I/O
        tz = _TIMEZONE_TORONTO

        # Build statistics per consumption type
        stats_by_type: dict[str, list[dict[str, Any]]] = {ctype: [] for ctype in consumption_types}

        rows_processed = 0
        rows_skipped_header = 0
        rows_skipped_invalid_format = 0
        rows_skipped_dst = 0
        rows_added = 0

        for row in csv_data:
            # Skip header row
            if isinstance(row, list) and len(row) > 2:
                if row[0] == "Contrat" or row[1] == "Date et heure":
                    rows_skipped_header += 1
                    continue

                # Parse date/time (format: "YYYY-MM-DD HH:MM:SS")
                datetime_str = str(row[1])
                try:
                    naive_dt = datetime.datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
                except ValueError as e:
                    _LOGGER.debug(
                        "CSV row %d: Skipping invalid datetime format: %s (error: %s)",
                        rows_processed,
                        datetime_str,
                        e,
                    )
                    rows_skipped_invalid_format += 1
                    continue

                # Attach timezone information.
                # zoneinfo handles DST transitions gracefully. For ambiguous times during a
                # fall-back transition, it defaults to the first occurrence (fold=0).
                # For non-existent times during a spring-forward transition, it adjusts
                # the time, which is the desired behavior for cumulative statistics.
                hour_datetime_tz = naive_dt.replace(tzinfo=tz)

                # Log every 100th hour being processed
                if rows_added % 100 == 0:
                    _LOGGER.debug(
                        "CSV import: Processing hour %s (row %d, added %d)",
                        datetime_str,
                        rows_processed,
                        rows_added,
                    )

                # Extract consumption values based on rate
                self._add_consumption_stats(stats_by_type, row, hour_datetime_tz)
                rows_added += 1

            rows_processed += 1

        _LOGGER.info(
            "CSV import: Processed %d rows total - Added: %d, Skipped: %d (header: %d, invalid: %d, DST: %d)",
            rows_processed,
            rows_added,
            rows_skipped_header + rows_skipped_invalid_format + rows_skipped_dst,
            rows_skipped_header,
            rows_skipped_invalid_format,
            rows_skipped_dst,
        )

        return stats_by_type

    def _add_consumption_stats(
        self,
        stats_by_type: dict[str, list[dict[str, Any]]],
        row: Sequence[Any],
        hour_datetime_tz: datetime.datetime,
    ) -> None:
        """Add consumption statistics for a single hour.

        Args:
            stats_by_type: Dictionary to append statistics to
            row: CSV row data
            hour_datetime_tz: Timezone-aware datetime for this hour
        """

        def safe_float_convert(value: str) -> float | None:
            """Convert string to float, handling N.D. (non-disponible) and French decimals.

            Args:
                value: String value to convert

            Returns:
                Float value or None if not available
            """
            if not value or value.strip().upper() in {"N. D.", "N.D.", "ND"}:
                return None
            try:
                return float(str(value).replace(",", "."))
            except ValueError:
                _LOGGER.debug("Could not convert value '%s' to float", value)
                return None

        if self._rate in {"DT", "DPC"}:
            # CSV columns: [0]=Contract, [1]=DateTime, [2]=kWh Reg, [3]=kWh Haut
            # Handle French decimal format (comma separator) and N.D. (non-disponible)
            reg_kwh = safe_float_convert(row[2]) if len(row) > 2 else None
            haut_kwh = safe_float_convert(row[3]) if len(row) > 3 else None

            # Skip this hour if data is not available
            if reg_kwh is None or haut_kwh is None:
                _LOGGER.debug(
                    "Skipping hour %s: data not available (reg=%s, haut=%s)",
                    hour_datetime_tz,
                    row[2] if len(row) > 2 else "missing",
                    row[3] if len(row) > 3 else "missing",
                )
                return

            if reg_kwh < 0 or haut_kwh < 0:
                _LOGGER.warning(
                    "Skipping hour %s: negative consumption value (reg=%s, haut=%s)",
                    hour_datetime_tz,
                    reg_kwh,
                    haut_kwh,
                )
                return

            total_kwh = reg_kwh + haut_kwh

            stats_by_type["reg"].append(
                {
                    "start": hour_datetime_tz,
                    "state": reg_kwh,
                }
            )
            stats_by_type["haut"].append(
                {
                    "start": hour_datetime_tz,
                    "state": haut_kwh,
                }
            )
            stats_by_type["total"].append(
                {
                    "start": hour_datetime_tz,
                    "state": total_kwh,
                }
            )
        else:
            # CSV columns: [0]=Contract, [1]=DateTime, [2]=kWh Total
            # Handle French decimal format (comma separator) and N.D. (non-disponible)
            total_kwh_value = safe_float_convert(row[2]) if len(row) > 2 else None

            # Skip this hour if data is not available or negative
            if total_kwh_value is None:
                _LOGGER.debug(
                    "Skipping hour %s: data not available (total=%s)",
                    hour_datetime_tz,
                    row[2] if len(row) > 2 else "missing",
                )
                return

            if total_kwh_value < 0:
                _LOGGER.warning(
                    "Skipping hour %s: negative consumption value (total=%s)",
                    hour_datetime_tz,
                    total_kwh_value,
                )
                return

            stats_by_type["total"].append(
                {
                    "start": hour_datetime_tz,
                    "state": total_kwh_value,
                }
            )

    async def _import_statistics(
        self,
        stats_by_type: dict[str, list[dict[str, Any]]],
        start_date: datetime.date,
        consumption_types: list[str],
    ) -> None:
        """Import parsed statistics into Home Assistant recorder.

        Args:
            stats_by_type: Dictionary mapping consumption type to statistics
            start_date: Start date of import period
            consumption_types: List of consumption types to import
        """
        for consumption_type in consumption_types:
            stats_list = stats_by_type[consumption_type]

            if not stats_list:
                _LOGGER.warning("No data found for consumption type %s", consumption_type)
                continue

            # Sort by timestamp
            stats_list.sort(key=lambda x: x["start"])

            first_date = stats_list[0]["start"].date() if stats_list else None
            last_date = stats_list[-1]["start"].date() if stats_list else None

            _LOGGER.debug(
                "[RECORDER IMPORT] Type '%s': Processing %d hourly records (from %s to %s)",
                consumption_type,
                len(stats_list),
                first_date,
                last_date,
            )

            # Log import summary
            if last_date and first_date:
                days_imported = (last_date - first_date).days + 1
                _LOGGER.info(
                    "[RECORDER IMPORT] Type '%s': Importing %d days (%d hours) from %s to %s (requested start: %s)",
                    consumption_type,
                    days_imported,
                    len(stats_list),
                    first_date,
                    last_date,
                    start_date,
                )

            # Query previous day's sum to maintain continuity
            statistic_id = self._get_statistic_id(consumption_type)
            _LOGGER.debug(
                "CSV import: Using statistic_id '%s' for %s",
                statistic_id,
                consumption_type,
            )
            # Base the continuity on the first actual data point we have
            first_stat_date = stats_list[0]["start"].date()
            yesterday = first_stat_date - datetime.timedelta(days=1)
            base_sum = await self._statistics_manager.get_base_sum(consumption_type, yesterday)

            # Add cumulative sums
            cumulative_sum = base_sum
            for stat in stats_list:
                cumulative_sum += stat["state"]
                stat["sum"] = round(cumulative_sum, 2)

            # Import to recorder
            metadata = self._statistics_manager.build_statistics_metadata(consumption_type)

            await get_instance(self.hass).async_add_executor_job(
                statistics.async_add_external_statistics,
                self.hass,
                metadata,
                stats_list,
            )

            _LOGGER.info(
                "Imported %d CSV statistics for %s (sum: %.2f kWh)",
                len(stats_list),
                consumption_type,
                cumulative_sum,
            )
