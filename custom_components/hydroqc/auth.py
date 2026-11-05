"""Authentication helpers shared by the config flow and the coordinator.

Hydro-Québec can now ask for a one-time code sent by e-mail after the password
round trip. The wrapper exposes that step as a ``LoginStatus`` returned by
``WebUser.login`` (``success``/``mfa_required``/``failed``) plus ``submit_mfa_code``
and ``request_mfa_code`` methods.

The integration pins a released wrapper, and the e-mail verification support is
newer than the pinned version. Everything here therefore works with both the old
``login() -> bool`` contract and the new one: nothing imports the new symbols at
module load, a missing attribute must degrade instead of breaking the whole
integration.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any

import hydroqc

_LOGGER = logging.getLogger(__name__)

LOGIN_SUCCESS = "success"
LOGIN_MFA_REQUIRED = "mfa_required"
LOGIN_FAILED = "failed"

# The verification errors are subclasses of each other, so catching the base one
# is enough. An empty tuple is a valid ``except`` target that never matches,
# which keeps the coordinator importable with a wrapper that predates MFA.
MFA_ERRORS: tuple[type[Exception], ...] = tuple(
    error
    for error in (getattr(hydroqc.error, "HydroQcMFARequiredError", None),)
    if error is not None
)


def login_outcome(status: Any) -> str:
    """Normalize the result of ``WebUser.login`` across wrapper versions.

    Older wrappers return a plain boolean, newer ones a ``LoginStatus`` enum
    whose value is one of the constants above.
    """
    if status is True:
        return LOGIN_SUCCESS
    if status is False or status is None:
        return LOGIN_FAILED

    value = getattr(status, "value", status)
    name = getattr(status, "name", "")
    if value == LOGIN_SUCCESS or name == "SUCCESS":
        return LOGIN_SUCCESS
    if value == LOGIN_MFA_REQUIRED or name == "MFA_REQUIRED":
        return LOGIN_MFA_REQUIRED
    return LOGIN_FAILED


def mfa_error_kind(err: BaseException) -> str | None:
    """Classify a verification error without importing the new exception classes.

    Returns ``"expired"`` when the verification step has to be restarted,
    ``"invalid"`` when the code was refused but another can be tried,
    ``"required"`` for an interactive login that is needed elsewhere, and
    ``None`` when the error has nothing to do with the verification step.
    """
    for cls in type(err).__mro__:
        if cls.__name__ == "HydroQcMFAExpiredError":
            return "expired"
        if cls.__name__ == "HydroQcMFAInvalidCodeError":
            return "invalid"
        if cls.__name__ == "HydroQcMFARequiredError":
            return "required"
    return None


def supports_mfa(webuser: Any) -> bool:
    """Tell whether the installed wrapper exposes the e-mail verification API."""
    return hasattr(webuser, "submit_mfa_code") and hasattr(webuser, "request_mfa_code")


async def async_try_silent_login(webuser: Any) -> Any:
    """Replay a stored session, if the wrapper supports it.

    Returns ``None`` when the installed wrapper predates the feature, which the
    callers treat as a failed silent login.
    """
    method = getattr(webuser, "try_silent_login", None)
    if not callable(method):
        return None
    status: Any = await method()
    return status


def _accepts_argument(method: Any, name: str) -> bool:
    """Tell whether ``method`` explicitly accepts the keyword ``name``.

    Mocks expose ``(*args, **kwargs)`` and wrapper versions differ, so the
    signature is the only reliable signal: passing an unknown keyword to a real
    ``login`` would raise ``TypeError``.
    """
    try:
        parameters = inspect.signature(method).parameters
    except (TypeError, ValueError):
        return False
    return name in parameters


async def async_login(webuser: Any, *, send_mfa_code: bool = True) -> Any:
    """Run the portal login, optionally without requesting a verification code.

    Background logins must not send e-mail codes: only the config flow may ask
    for one. Wrappers that expose the ``send_mfa_code`` switch receive it;
    older wrappers (4.3.0) always request a code inside ``login``, so the
    request is neutralized for the duration of the call.
    """
    method = getattr(webuser, "login", None)
    if not callable(method):
        return None
    if send_mfa_code or not supports_mfa(webuser):
        return await method()
    if _accepts_argument(method, "send_mfa_code"):
        return await method(send_mfa_code=False)

    # Compatibility path: the wrapper predates the opt-out. Replace the bound
    # request with a no-op for this login only, then restore it.
    original = webuser.request_mfa_code

    async def _skip_request(*_args: Any, **_kwargs: Any) -> bool:
        return False

    webuser.request_mfa_code = _skip_request
    try:
        return await method()
    finally:
        webuser.request_mfa_code = original


async def async_request_mfa_code(webuser: Any) -> bool:
    """Ask for a new verification code, if the wrapper supports it."""
    method = getattr(webuser, "request_mfa_code", None)
    if not callable(method):
        return False
    sent: Any = await method()
    return bool(sent)


async def async_submit_mfa_code(webuser: Any, code: str) -> Any:
    """Submit a verification code, if the wrapper supports it."""
    method = getattr(webuser, "submit_mfa_code", None)
    if not callable(method):
        return None
    status: Any = await method(code)
    return status
