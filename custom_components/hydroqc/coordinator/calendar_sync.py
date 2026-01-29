"""Calendar synchronization functionality for HydroQc coordinator."""

# mypy: disable-error-code="attr-defined"

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import TYPE_CHECKING

from homeassistant.helpers.storage import Store

from hydroqc.contract import ContractDCPC

from .. import calendar_manager
from ..calendar_peak_handler import CalendarPeakHandler
from ..const import (
    CONF_CALENDAR_ENTITY_ID,
)
from ..utils import is_winter_season

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)

# Storage for calendar event UIDs (persists across restarts)
STORAGE_VERSION = 1
STORAGE_KEY_CALENDAR_UIDS = "hydroqc.calendar_uids"


class CalendarSyncMixin:
    """Mixin for calendar synchronization functionality."""

    def _init_calendar_sync(self) -> None:
        """Initialize calendar synchronization attributes."""
        # Calendar configuration (for DPC/DCPC rates)
        self._calendar_entity_id = self.entry.options.get(
            CONF_CALENDAR_ENTITY_ID, self.entry.data.get(CONF_CALENDAR_ENTITY_ID)
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
            storage_key = f"{STORAGE_KEY_CALENDAR_UIDS}.{self.entry.entry_id}"
            self._calendar_uid_store = Store(self.hass, STORAGE_VERSION, storage_key, encoder=None)

        # Track calendar sync task (prevent concurrent syncs)
        self._calendar_sync_task: asyncio.Task[None] | None = None

        # Calendar peak handler for reading events from calendar (sensors source)
        # Only created if calendar is configured for DPC/DCPC rates
        self.calendar_peak_handler: CalendarPeakHandler | None = None
        if self._calendar_entity_id and self.rate_with_option in ["DPC", "DCPC"]:
            self.calendar_peak_handler = CalendarPeakHandler(
                hass=self.hass,
                calendar_entity_id=self._calendar_entity_id,
                rate_code=self.rate_with_option,
                preheat_duration=self._preheat_duration,
            )
            _LOGGER.info(
                "Calendar peak handler initialized for %s with calendar %s",
                self.contract_name,
                self._calendar_entity_id,
            )

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

    async def async_load_calendar_peak_events(self) -> bool:
        """Load peak events from calendar into CalendarPeakHandler.

        This refreshes the calendar-based peak data that sensors read from.
        Should be called on every coordinator refresh.

        Returns:
            True if events were loaded successfully, False otherwise.
        """
        if not self.calendar_peak_handler:
            return False

        success = await self.calendar_peak_handler.async_load_events()

        if success:
            _LOGGER.debug(
                "[Calendar] Loaded %d events from calendar for %s (calendar: %s)",
                len(self.calendar_peak_handler._events),
                self.contract_name,
                self.calendar_peak_handler.calendar_name,
            )
        else:
            _LOGGER.debug(
                "[Calendar] Failed to load events from calendar %s for %s",
                self._calendar_entity_id,
                self.contract_name,
            )

        return success

    def is_sensor_seasonal(self, data_source: str) -> bool:
        """Check if a winter credit sensor is in season.

        Winter credit sensors should only show data during the winter season.
        This applies ONLY to Portal mode sensors that fetch from contract data.
        OpenData mode sensors (public_client) are always available.
        Calendar-based sensors follow winter season rules for DCPC rate.
        """
        # OpenData mode sensors using public_client are never seasonal
        if data_source.startswith("public_client."):
            return True

        # Calendar-based sensors for DCPC follow winter season
        if data_source.startswith("calendar_peak_handler."):
            if self.rate_option != "CPC":
                return True  # DPC is not seasonal
            # For DCPC, check if we're in winter season
            return is_winter_season()

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

            # Sync events using calendar manager (critical peaks only)
            new_uids = await calendar_manager.async_sync_events(
                self.hass,
                self._calendar_entity_id,
                peaks,
                self._created_event_uids,
                self.contract_id,
                self.contract_name,
                self.rate_with_option,
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
