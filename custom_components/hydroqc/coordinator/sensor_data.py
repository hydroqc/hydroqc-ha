"""Sensor data access functionality for HydroQc coordinator."""

# mypy: disable-error-code="attr-defined"

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)


class SensorDataMixin:
    """Mixin for sensor data access functionality."""

    def get_sensor_value(self, data_source: str) -> Any:  # noqa: PLR0912
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
        # Handle special data sources
        if data_source == "portal_available":
            # Portal mode only - return portal availability status
            if self.is_portal_mode:
                return self._portal_available
            return None

        # Handle calendar_peak_handler data source
        # Returns None if no calendar configured (sensors will be unavailable)
        if data_source.startswith("calendar_peak_handler."):
            return self._get_calendar_peak_handler_value(data_source)

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

    def _get_calendar_peak_handler_value(self, data_source: str) -> Any:
        """Extract value from calendar_peak_handler using dot-notation path.

        Args:
            data_source: Data source path starting with "calendar_peak_handler."

        Returns:
            The value from CalendarPeakHandler, or None if not available.
            For binary sensors ending with is_critical, returns False if unavailable.
        """
        # If no calendar peak handler configured, return None (sensor unavailable)
        if not hasattr(self, "calendar_peak_handler") or self.calendar_peak_handler is None:
            # For binary sensors, return False instead of None
            if data_source.endswith(".is_critical"):
                return False
            return None

        # Special handling for DCPC preheat_in_progress
        # Only trigger preheat for critical peaks
        if (
            data_source == "calendar_peak_handler.preheat_in_progress"
            and self.rate_with_option == "DCPC"
        ):
            handler = self.calendar_peak_handler
            preheat_active = handler.preheat_in_progress
            next_peak = handler.next_peak
            next_peak_critical = next_peak.is_critical if next_peak else False
            return preheat_active and next_peak_critical

        # Special handling for DCPC preheat start timestamp
        # Only show preheat start time if next peak is critical
        if (
            data_source == "calendar_peak_handler.next_peak.preheat.start_date"
            and self.rate_with_option == "DCPC"
        ):
            handler = self.calendar_peak_handler
            next_peak = handler.next_peak
            if next_peak and next_peak.is_critical:
                return next_peak.preheat.start_date
            return None

        # Parse path and walk object graph
        parts = data_source.split(".")
        obj = self.calendar_peak_handler

        # Walk the path (skip first part "calendar_peak_handler")
        for part in parts[1:]:
            if obj is None:
                if data_source.endswith(".is_critical"):
                    return False
                return None
            try:
                if not hasattr(obj, part):
                    _LOGGER.debug("Attribute %s not found in %s", part, type(obj).__name__)
                    if data_source.endswith(".is_critical"):
                        return False
                    return None
                obj = getattr(obj, part)
            except (AttributeError, TypeError, ValueError) as e:
                _LOGGER.debug(
                    "Error accessing attribute %s on %s: %s",
                    part,
                    type(obj).__name__,
                    str(e),
                )
                if data_source.endswith(".is_critical"):
                    return False
                return None

        return obj
