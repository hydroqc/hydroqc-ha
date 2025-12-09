"""Data models for Hydro-Québec winter peaks."""

from __future__ import annotations

import datetime
import logging
import zoneinfo
from typing import Any

_LOGGER = logging.getLogger(__name__)


class PreHeatPeriod:
    """Represents a pre-heat period before a peak."""

    def __init__(self, peak_start: datetime.datetime, duration_minutes: int) -> None:
        """Initialize pre-heat period."""
        self.start_date = peak_start - datetime.timedelta(minutes=duration_minutes)
        self.end_date = peak_start


class AnchorPeriod:
    """Represents an anchor period (notification) before a peak."""

    def __init__(self, peak_start: datetime.datetime, is_morning: bool, is_critical: bool) -> None:
        """Initialize anchor period.

        Morning peaks (6:00-10:00): Anchor starts 5 hours before, lasts 3 hours
        Evening peaks (16:00-20:00): Anchor starts 4 hours before, lasts 2 hours
        """
        if is_morning:
            # Morning: 5 hours before peak, duration 3 hours
            anchor_start_offset = 5
            anchor_duration = 3
        else:
            # Evening: 4 hours before peak, duration 2 hours
            anchor_start_offset = 4
            anchor_duration = 2

        self.start_date = peak_start - datetime.timedelta(hours=anchor_start_offset)
        self.end_date = self.start_date + datetime.timedelta(hours=anchor_duration)
        self.is_critical = is_critical


class PeakEvent:
    """Represents a winter peak event."""

    def __init__(
        self,
        data: dict[str, Any],
        preheat_duration: int = 120,
        force_critical: bool | None = None,
    ) -> None:
        """Initialize peak event from API data.

        Args:
            data: Peak event data from API
            preheat_duration: Pre-heat duration in minutes
            force_critical: Explicitly set critical status (True=critical from API,
                          False=generated non-critical, None=auto-detect from offer)
        """
        self.offer = data["offre"]
        self._force_critical = force_critical
        # Parse dates and make them timezone-aware (America/Toronto = EST/EDT)
        tz = zoneinfo.ZoneInfo("America/Toronto")

        # API uses lowercase field names: datedebut, datefin, plagehoraire, secteurclient
        start_str = data.get("datedebut") or data.get("dateDebut")
        end_str = data.get("datefin") or data.get("dateFin")

        if not start_str or not end_str:
            raise ValueError(f"Missing date fields in data: {data}")

        # Handle both date formats:
        # - Simple: "YYYY-MM-DD HH:MM" (most common from API)
        # - ISO: "YYYY-MM-DDTHH:MM:SS-05:00" or similar
        try:
            # Try ISO format first
            start_dt = datetime.datetime.fromisoformat(start_str)
            end_dt = datetime.datetime.fromisoformat(end_str)
            # Ensure timezone-aware - if naive, add America/Toronto
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=tz)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=tz)
            self.start_date = start_dt
            self.end_date = end_dt
        except (ValueError, TypeError) as err:
            # Fall back to simple format
            try:
                self.start_date = datetime.datetime.strptime(start_str, "%Y-%m-%d %H:%M").replace(
                    tzinfo=tz
                )
                self.end_date = datetime.datetime.strptime(end_str, "%Y-%m-%d %H:%M").replace(
                    tzinfo=tz
                )
            except (ValueError, TypeError) as err2:
                _LOGGER.error(
                    "Failed to parse dates: start=%r end=%r (ISO error: %s, Simple error: %s)",
                    start_str,
                    end_str,
                    err,
                    err2,
                )
                raise

        self.time_slot = data.get("plagehoraire") or data.get("plageHoraire")  # AM or PM
        self.duration = data.get("duree")
        self.sector = data.get("secteurclient") or data.get(
            "secteurClient"
        )  # Résidentiel or Affaires
        self._preheat_duration = preheat_duration

    @property
    def is_critical(self) -> bool:
        """Determine if this is a critical peak.

        Returns True if:
        - force_critical=True (event from OpenData API announcement)
        - force_critical=None and offer starts with TPC/ENG (backward compatibility)

        Returns False if:
        - force_critical=False (generated non-critical schedule peak)
        - force_critical=None and offer doesn't start with TPC/ENG
        """
        if self._force_critical is not None:
            return self._force_critical
        # Fallback for backward compatibility (should not be used with new code)
        return bool(self.offer.startswith("TPC") or self.offer.startswith("ENG"))

    @property
    def preheat(self) -> PreHeatPeriod:
        """Get pre-heat period for this peak."""
        return PreHeatPeriod(self.start_date, self._preheat_duration)

    @property
    def anchor(self) -> AnchorPeriod:
        """Get anchor period for this peak (Winter Credits)."""
        # Determine if this is a morning peak (6:00-10:00) or evening peak (16:00-20:00)
        is_morning = self.time_slot == "AM"
        return AnchorPeriod(self.start_date, is_morning, self.is_critical)

    @property
    def is_residential(self) -> bool:
        """Check if this peak is for residential sector."""
        return self.sector == "Résidentiel"

    @property
    def is_commercial(self) -> bool:
        """Check if this peak is for commercial sector."""
        return self.sector == "Affaires"
