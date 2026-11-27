"""Small aiohttp test doubles for the Hydro-Québec public data feeds."""

from __future__ import annotations

from typing import Any

import aiohttp


class FakeResponse:
    """Stand-in for ``aiohttp.ClientResponse``."""

    def __init__(self, payload: Any, status: int = 200) -> None:
        self._payload = payload
        self.status = status

    def raise_for_status(self) -> None:
        """Raise when the fake status is an error."""
        if self.status >= 400:
            raise aiohttp.ClientError(f"fake HTTP {self.status}")

    async def json(self) -> Any:
        """Return the canned payload."""
        return self._payload

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


class FakeSession:
    """Stand-in for ``aiohttp.ClientSession`` recording its requests."""

    def __init__(self, payload: Any, status: int = 200) -> None:
        self._payload = payload
        self._status = status
        self.requests: list[dict[str, Any]] = []
        self.closed = False

    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        timeout: aiohttp.ClientTimeout | None = None,
    ) -> FakeResponse:
        """Record the request and return a fake response."""
        self.requests.append({"url": url, "params": params or {}})
        return FakeResponse(self._payload, self._status)

    async def close(self) -> None:
        """Mark the session as closed."""
        self.closed = True

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None
