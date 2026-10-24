"""Tests for runtime patches applied to the Hydro-Quebec-API-Wrapper library."""

from __future__ import annotations

import base64
import binascii
import json

import pytest
from hydroqc.hydro_api.client import HydroClient

from custom_components.hydroqc.hydroqc_patches import apply_patches


def _make_id_token(payload: dict[str, str]) -> str:
    """Build an unsigned JWT whose payload segment is base64url without padding."""
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
    body = (
        base64.urlsafe_b64encode(json.dumps(payload, ensure_ascii=False).encode())
        .decode()
        .rstrip("=")
    )
    return f"{header}.{body}.sig"


def _accented_payload() -> dict[str, str]:
    """Return a payload whose base64url encoding contains '-' or '_'."""
    for extra in range(64):
        payload = {
            "sub": "abc",
            "given_name": "Noémie",
            "family_name": "Beaudet",
            "pad": "x" * extra,
        }
        segment = _make_id_token(payload).split(".")[1]
        if "-" in segment or "_" in segment:
            return payload
    raise AssertionError("Could not build a payload with base64url-only characters")


def _client_with_token(token: str) -> HydroClient:
    client = HydroClient("user@example.com", "password")
    client._id_token = token
    return client


def test_token_with_base64url_chars_is_decoded() -> None:
    """A name with an accent must not break id token decoding."""
    apply_patches()
    payload = _accented_payload()
    client = _client_with_token(_make_id_token(payload))

    data = client.get_token_data()

    assert data is not None
    assert data["given_name"] == "Noémie"
    assert data["family_name"] == "Beaudet"
    assert data["sub"] == "abc"


def test_standard_b64decode_fails_on_same_token() -> None:
    """Document the library bug the patch works around."""
    segment = _make_id_token(_accented_payload()).split(".")[1]
    segment += "=" * ((4 - len(segment) % 4) % 4)
    with pytest.raises(binascii.Error):
        base64.b64decode(segment)


def test_no_token_returns_none() -> None:
    apply_patches()
    client = _client_with_token("")
    assert client.get_token_data() is None


def test_apply_patches_is_idempotent() -> None:
    apply_patches()
    first = HydroClient.get_token_data
    apply_patches()
    assert HydroClient.get_token_data is first
