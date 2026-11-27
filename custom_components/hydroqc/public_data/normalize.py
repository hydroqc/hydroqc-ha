"""Normalization of Hydro-Québec peak event payloads.

The two public feeds do not use the same shape:

- the Opendatasoft API answers ``{"total_count": ..., "results": [...]}`` with
  lowercase field ids (``datedebut``, ``secteurclient``, ...);
- the legacy JSON feed answers
  ``{"offresDisponibles": [...], "evenements": [...]}`` with camelCase keys
  (``dateDebut``, ``secteurClient``, ...).

Both are read here so the rest of the integration never depends on which feed
or which spelling Hydro-Québec uses.
"""

from __future__ import annotations

from typing import Any

from .offers import fold_text

# Payload keys that hold the list of events, in order of preference.
_RECORD_LIST_KEYS = ("results", "evenements", "events", "records")


def _canonical_key(key: object) -> str:
    """Fold a field name: ``dateDebut``, ``date_debut`` and ``datedebut`` match."""
    if not isinstance(key, str):
        return ""
    return key.replace("_", "").replace("-", "").replace(" ", "").casefold()


def get_field(record: Any, *names: str) -> Any:
    """Return the first non-empty field matching one of ``names``.

    Names are compared after folding, so the spelling of the feed does not
    matter (``secteurClient``, ``secteurclient`` and ``secteur_client`` are the
    same field).
    """
    if not isinstance(record, dict):
        return None

    lookup = {_canonical_key(key): value for key, value in record.items()}
    for name in names:
        value = lookup.get(_canonical_key(name))
        if value is not None and value != "":
            return value
    return None


def extract_records(payload: Any) -> list[dict[str, Any]]:
    """Return the peak events from any supported payload shape."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    for key in _RECORD_LIST_KEYS:
        items = payload.get(key)
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]

    return []


def normalize_event(record: Any) -> dict[str, str] | None:
    """Convert a feed record to the dict shape ``PeakEvent`` expects.

    Returns None when the record carries no usable date range.
    """
    start = get_field(record, "datedebut", "debut", "start")
    end = get_field(record, "datefin", "fin", "end")
    if not start or not end:
        return None

    return {
        "offre": str(get_field(record, "offre", "offer", "offres") or ""),
        "dateDebut": str(start),
        "dateFin": str(end),
        "plageHoraire": str(get_field(record, "plagehoraire", "periode") or ""),
        "duree": str(get_field(record, "duree", "duration") or ""),
        "secteurClient": str(
            get_field(record, "secteurclient", "typeclientele", "secteur", "sector") or ""
        ),
    }


def normalize_sector(value: object) -> str:
    """Return the canonical sector name for a value coming from a feed.

    Hydro-Québec used ``Résidentiel`` and now returns ``Residentiel``; both map
    to ``Residentiel``. Unknown values are returned stripped and unchanged.
    """
    if not isinstance(value, str):
        return ""

    raw = value.strip()
    folded = fold_text(raw)
    if folded.startswith("residentiel") or folded == "residential":
        return "Residentiel"
    if folded.startswith("affaire") or folded == "commercial":
        return "Affaires"
    return raw
