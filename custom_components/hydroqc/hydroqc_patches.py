"""Runtime fixes for the Hydro-Quebec-API-Wrapper library.

These patches work around bugs in the pinned library version until they are
fixed upstream (https://gitlab.com/hydroqc/hydroqc). Each patch is idempotent.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from hydroqc.hydro_api.client import HydroClient

_LOGGER = logging.getLogger(__name__)

_PATCHED_ATTR = "_hydroqc_ha_patched"


def _get_token_data_base64url(self: HydroClient) -> Any:
    """Decode the id token payload as base64url, per the JWT spec (RFC 7519).

    The library uses ``base64.b64decode``, which silently drops the base64url
    characters ``-`` and ``_``. Payloads that contain them (for example, a name
    with an accent such as "Noémie") then fail with ``binascii.Error: Incorrect
    padding`` right after a successful login.
    """
    if not self._id_token:
        return None
    raw_token_data = self._id_token.split(".")[1]
    raw_token_data += "=" * ((4 - len(raw_token_data) % 4) % 4)
    return self._load_json(base64.urlsafe_b64decode(raw_token_data))


def apply_patches() -> None:
    """Apply all library patches once."""
    if getattr(HydroClient, _PATCHED_ATTR, False):
        return
    HydroClient.get_token_data = _get_token_data_base64url  # type: ignore[method-assign]
    setattr(HydroClient, _PATCHED_ATTR, True)
    _LOGGER.debug("Applied base64url id token decoding patch to HydroClient")
