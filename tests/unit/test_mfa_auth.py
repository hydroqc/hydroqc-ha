"""Unit tests for the background login that must not request an MFA code."""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.hydroqc.auth import LOGIN_MFA_REQUIRED, async_login


class SwitchClient:
    """HydroClient-like object exposing the ``send_mfa_code`` switch (4.3.1+)."""

    def __init__(self) -> None:
        self.requested = False

    async def login(self, *, send_mfa_code: bool = True) -> str:
        if send_mfa_code:
            await self.request_mfa_code()
        return LOGIN_MFA_REQUIRED

    async def request_mfa_code(self) -> bool:
        self.requested = True
        return True

    async def submit_mfa_code(self, _code: str) -> Any:
        return "success"


class LegacyClient(SwitchClient):
    """HydroClient-like object that always requests the code during login (4.3.0)."""

    async def login(self) -> str:
        await self.request_mfa_code()
        return LOGIN_MFA_REQUIRED


class DelegatingWebUser:
    """WebUser-like object that delegates to its client without forwarding (4.3.1)."""

    def __init__(self, client: SwitchClient) -> None:
        self._hydro_client = client

    async def login(self) -> str:
        return await self._hydro_client.login()

    async def request_mfa_code(self) -> bool:
        return await self._hydro_client.request_mfa_code()

    async def submit_mfa_code(self, code: str) -> Any:
        return await self._hydro_client.submit_mfa_code(code)


class DirectWebUser(DelegatingWebUser):
    """WebUser-like object that forwards the switch itself (future wrappers)."""

    async def login(self, *, send_mfa_code: bool = True) -> str:
        return await self._hydro_client.login(send_mfa_code=send_mfa_code)


class LegacyWebUser:
    """WebUser-like object that requests the code on itself, without a client."""

    def __init__(self) -> None:
        self.requested = False

    async def login(self) -> str:
        await self.request_mfa_code()
        return LOGIN_MFA_REQUIRED

    async def request_mfa_code(self) -> bool:
        self.requested = True
        return True

    async def submit_mfa_code(self, _code: str) -> Any:
        return "success"


async def test_delegating_webuser_uses_the_client_switch() -> None:
    """A wrapper that does not forward the switch still has it on its client."""
    client = SwitchClient()
    webuser = DelegatingWebUser(client)

    assert await async_login(webuser, send_mfa_code=False) == LOGIN_MFA_REQUIRED

    assert client.requested is False


async def test_delegating_webuser_suppresses_the_legacy_client_request() -> None:
    """A client without the switch has its request neutralized for the call."""
    client = LegacyClient()
    webuser = DelegatingWebUser(client)

    assert await async_login(webuser, send_mfa_code=False) == LOGIN_MFA_REQUIRED

    assert client.requested is False
    assert callable(client.request_mfa_code)


async def test_direct_switch_is_used_when_the_webuser_forwards_it() -> None:
    """A wrapper exposing ``login(send_mfa_code=...)`` receives the opt-out."""
    client = SwitchClient()
    webuser = DirectWebUser(client)

    assert await async_login(webuser, send_mfa_code=False) == LOGIN_MFA_REQUIRED

    assert client.requested is False


async def test_legacy_webuser_without_a_client_is_suppressed() -> None:
    """The last-resort path still protects a wrapper with no client."""
    webuser = LegacyWebUser()

    assert await async_login(webuser, send_mfa_code=False) == LOGIN_MFA_REQUIRED

    assert webuser.requested is False
    assert callable(webuser.request_mfa_code)


@pytest.mark.parametrize("user_factory", [SwitchClient, LegacyClient])
async def test_default_login_still_requests_the_code(user_factory: type[SwitchClient]) -> None:
    """The interactive path keeps asking for the code."""
    client = user_factory()
    webuser = DelegatingWebUser(client)

    assert await async_login(webuser) == LOGIN_MFA_REQUIRED

    assert client.requested is True
