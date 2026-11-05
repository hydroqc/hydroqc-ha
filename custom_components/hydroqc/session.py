"""Persistence of the portal session between Home Assistant restarts.

The wrapper exports the OAuth tokens and the Azure AD B2C cookies of a session.
Restoring them lets a later start skip a full login, and therefore skip a new
e-mail verification code, while the refresh token or the single sign-on cookie
is still valid.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
_PENDING_SESSIONS_KEY = f"{DOMAIN}_pending_sessions"


def stage_pending_session(hass: HomeAssistant, unique_id: str, state: dict[str, Any]) -> None:
    """Keep a session obtained before its config entry existed.

    The initial setup flow logs in before Home Assistant creates the entry, so
    the session cannot be stored under an entry id yet. The coordinator takes it
    over on the first refresh, which avoids a second login and a second code.
    """
    hass.data.setdefault(_PENDING_SESSIONS_KEY, {})[unique_id] = state


def take_pending_session(hass: HomeAssistant, unique_id: str) -> dict[str, Any] | None:
    """Return and forget the session staged for ``unique_id``."""
    pending = hass.data.get(_PENDING_SESSIONS_KEY)
    if not isinstance(pending, dict):
        return None
    state = pending.pop(unique_id, None)
    if not pending:
        hass.data.pop(_PENDING_SESSIONS_KEY, None)
    return state if isinstance(state, dict) else None


def _session_store(hass: HomeAssistant, entry: ConfigEntry) -> Store[dict[str, Any]]:
    """Return the store holding the portal session of ``entry``."""
    return Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.session")


async def async_load_session(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any] | None:
    """Load the persisted session, ignoring an unreadable or missing one."""
    try:
        state = await _session_store(hass, entry).async_load()
    except Exception:  # pylint: disable=broad-except
        _LOGGER.warning(
            "Could not read the stored Hydro-Québec session, a new login is needed",
            exc_info=True,
        )
        return None
    return state if isinstance(state, dict) else None


async def async_save_session(
    hass: HomeAssistant, entry: ConfigEntry, state: dict[str, Any]
) -> None:
    """Persist a session produced by ``WebUser.export_session_state``.

    A state without refresh token nor cookies cannot skip a login. Such a state
    only comes from a refused or half-finished login, and writing it would
    replace a stored session that may still work.
    """
    if not state.get("refresh_token") and not state.get("cookies"):
        return
    try:
        await _session_store(hass, entry).async_save(state)
    except Exception:  # pylint: disable=broad-except
        _LOGGER.warning(
            "Could not store the Hydro-Québec session, the next restart will log in again",
            exc_info=True,
        )
