"""Keep the Flex-D (DPC) and Winter Credits (DCPC) entities aligned.

Both rates describe the same peak concepts, so an entity that exists for one
rate must exist for the other with the same kind and the same visibility.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from custom_components.hydroqc.const import BINARY_SENSORS, SENSORS

TRANSLATIONS_DIR = (
    Path(__file__).resolve().parents[2] / "custom_components" / "hydroqc" / "translations"
)

# Fields that decide how an entity behaves for the user
ALIGNED_FIELDS = (
    "device_class",
    "state_class",
    "unit",
    "icon",
    "diagnostic",
    "disabled_by_default",
)


def _entries_for_rate(registry: dict[str, dict[str, Any]], rate: str) -> dict[str, Any]:
    """Return the entities a rate exposes, keyed by data source."""
    return {
        config["data_source"]: config for config in registry.values() if rate in config["rates"]
    }


def _sources(registry_name: str, rate: str) -> dict[str, Any]:
    registry = SENSORS if registry_name == "SENSORS" else BINARY_SENSORS
    return _entries_for_rate(registry, rate)


@pytest.mark.parametrize("registry_name", ["SENSORS", "BINARY_SENSORS"])
def test_shared_concepts_are_identical(registry_name: str) -> None:
    """Every data source used by both rates carries the same entity metadata."""
    dpc = _sources(registry_name, "DPC")
    dcpc = _sources(registry_name, "DCPC")

    shared = sorted(set(dpc) & set(dcpc))
    assert shared

    mismatches = {
        source: {
            field: (dpc[source].get(field), dcpc[source].get(field))
            for field in ALIGNED_FIELDS
            if dpc[source].get(field) != dcpc[source].get(field)
        }
        for source in shared
        if any(dpc[source].get(field) != dcpc[source].get(field) for field in ALIGNED_FIELDS)
    }
    assert not mismatches


@pytest.mark.parametrize(
    ("registry_name", "dpc_key", "dcpc_key", "data_source"),
    [
        ("SENSORS", "dpc_state", "wc_state", "calendar_peak_handler.current_state"),
        (
            "SENSORS",
            "dpc_next_peak_start",
            "wc_next_peak_start",
            "calendar_peak_handler.next_peak.start_date",
        ),
        (
            "SENSORS",
            "dpc_next_peak_end",
            "wc_next_peak_end",
            "calendar_peak_handler.next_peak.end_date",
        ),
        (
            "SENSORS",
            "dpc_next_pre_heat_start",
            "wc_next_pre_heat_start",
            "calendar_peak_handler.next_peak.preheat.start_date",
        ),
        (
            "BINARY_SENSORS",
            "dpc_peak_in_progress",
            "wc_peak_in_progress",
            "calendar_peak_handler.peak_in_progress",
        ),
        (
            "BINARY_SENSORS",
            "dpc_pre_heat",
            "wc_pre_heat",
            "calendar_peak_handler.preheat_in_progress",
        ),
        (
            "BINARY_SENSORS",
            "dpc_critical_morning_peak_today",
            "wc_critical_morning_peak_today",
            "calendar_peak_handler.today_morning_peak.is_critical",
        ),
        (
            "BINARY_SENSORS",
            "dpc_critical_evening_peak_today",
            "wc_critical_evening_peak_today",
            "calendar_peak_handler.today_evening_peak.is_critical",
        ),
        (
            "BINARY_SENSORS",
            "dpc_critical_morning_peak_tomorrow",
            "wc_critical_morning_peak_tomorrow",
            "calendar_peak_handler.tomorrow_morning_peak.is_critical",
        ),
        (
            "BINARY_SENSORS",
            "dpc_critical_evening_peak_tomorrow",
            "wc_critical_evening_peak_tomorrow",
            "calendar_peak_handler.tomorrow_evening_peak.is_critical",
        ),
    ],
)
def test_peak_concepts_exist_for_both_rates(
    registry_name: str, dpc_key: str, dcpc_key: str, data_source: str
) -> None:
    """Each peak concept has one entity per rate, on the same data source."""
    registry = SENSORS if registry_name == "SENSORS" else BINARY_SENSORS
    assert registry[dpc_key]["data_source"] == data_source
    assert registry[dcpc_key]["data_source"] == data_source


def test_peak_entities_are_primary() -> None:
    """Peak dates and state are main entities, not diagnostics, for both rates."""
    for key in (
        "dpc_state",
        "dpc_next_peak_start",
        "dpc_next_peak_end",
        "wc_state",
        "wc_next_peak_start",
        "wc_next_peak_end",
    ):
        config = SENSORS[key]
        assert not config.get("diagnostic"), key
        assert not config.get("disabled_by_default"), key


@pytest.mark.parametrize("language", ["en", "fr", "es"])
def test_every_entity_has_a_translation(language: str) -> None:
    """Both rates' entities are named in each shipped language."""
    entity = json.loads((TRANSLATIONS_DIR / f"{language}.json").read_text())["entity"]
    for domain, registry in (("sensor", SENSORS), ("binary_sensor", BINARY_SENSORS)):
        missing = [key for key in registry if key not in entity.get(domain, {})]
        assert not missing, f"{language}/{domain} missing names: {missing}"
