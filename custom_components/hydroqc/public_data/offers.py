"""Hydro-Québec peak offer catalog and value normalization.

Hydro-Québec publishes peak events on two feeds and names the offers
differently on each one:

- the Opendatasoft dataset (``evenements-pointe``) returns short codes such as
  ``CPC-D`` or ``TPC-DPC``;
- the legacy JSON feed (``pointeshivernales.json``) returns labels that carry
  the code in parentheses, such as
  ``Credit hivernal Residentiel (CPC-D)``.

Config entries only store the internal rate codes (``DCPC``, ``DPC``, ...), so
every offer value coming from a feed is normalized back to a catalog code
before it is compared with what the integration stores.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class PeakOffer:
    """A Hydro-Québec offer that has peak events."""

    code: str
    rate: str
    rate_option: str
    internal_rate: str
    label: str


# Canonical offer codes, mapped to the internal rate they belong to.
PEAK_OFFERS: dict[str, PeakOffer] = {
    "CPC-D": PeakOffer("CPC-D", "D", "CPC", "DCPC", "Rate D + Winter Credits (CPC)"),
    "TPC-DPC": PeakOffer("TPC-DPC", "DPC", "", "DPC", "Flex-D (Dynamic Pricing)"),
    "GDP-Affaires": PeakOffer("GDP-Affaires", "M", "GDP", "M-GDP", "Commercial Rate M + GDP"),
    "CPC-G": PeakOffer("CPC-G", "M", "CPC", "M-CPC", "Commercial Rate M + Winter Credits (CPC)"),
    "TPC-GPC": PeakOffer("TPC-GPC", "M", "GPC", "M-GPC", "Commercial Rate M + GPC"),
    "ENG01": PeakOffer("ENG01", "M", "ENG", "M-ENG", "Commercial Rate M + ENG01"),
    "OEA": PeakOffer("OEA", "M", "OEA", "M-OEA", "Commercial Rate M + OEA"),
}

# Backward-compatible view: HQ offer code -> internal rate code.
RATE_CODE_MAPPING: dict[str, str] = {
    code: offer.internal_rate for code, offer in PEAK_OFFERS.items()
}

# A trailing parenthesised code: "Credit hivernal Residentiel (CPC-D)".
_TRAILING_CODE_RE = re.compile(r"\(\s*([A-Za-z0-9][A-Za-z0-9_.-]*)\s*\)\s*$")


def fold_text(value: object) -> str:
    """Fold a string for comparison: strip accents, collapse case and spaces."""
    if not isinstance(value, str):
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(without_accents.split()).casefold()


def normalize_offer(value: object) -> str:
    """Return the canonical offer code for a value coming from a feed.

    ``"CPC-D"``, ``"cpc-d"``, ``"Credit hivernal Residentiel (CPC-D)"`` and
    ``"Crédit hivernal résidentiel (cpc-d)"`` all normalize to ``"CPC-D"``.
    Unknown values are returned stripped and unchanged, so an unexpected new
    offer is still visible in logs instead of being dropped silently.
    """
    if not isinstance(value, str):
        return ""

    raw = value.strip()
    if not raw:
        return ""

    if raw in PEAK_OFFERS:
        return raw

    folded = fold_text(raw)
    for code in PEAK_OFFERS:
        if fold_text(code) == folded:
            return code

    match = _TRAILING_CODE_RE.search(raw)
    if match:
        candidate = match.group(1)
        for code in PEAK_OFFERS:
            if fold_text(code) == fold_text(candidate):
                return code

    for code, offer in PEAK_OFFERS.items():
        if fold_text(offer.label) == folded:
            return code

    return raw


def is_known_offer(value: object) -> bool:
    """Return True when the value resolves to a catalog offer code."""
    return normalize_offer(value) in PEAK_OFFERS


def offers_for_rate(internal_rate: str) -> list[str]:
    """Return the catalog offer codes that serve an internal rate code.

    The coordinator builds the code as ``rate + rate_option`` (``MGDP``) while
    the catalog spells commercial codes with a hyphen (``M-GDP``); both match.
    """
    wanted = fold_text(internal_rate).replace("-", "")
    return [
        code
        for code, offer in PEAK_OFFERS.items()
        if offer.internal_rate.replace("-", "").casefold() == wanted
    ]


def offer_field_names(code: str) -> list[str]:
    """Return the accepted raw feed values for an offer code.

    Includes the code itself, its catalog label and the labelled form seen on
    the legacy JSON feed ("<label> (<code>)"), so a record is recognized
    whichever name Hydro-Québec uses.
    """
    offer = PEAK_OFFERS.get(code)
    if offer is None:
        return [code]
    return [code, offer.label, f"{offer.label} ({code})"]
