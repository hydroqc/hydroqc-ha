from typing import Any

import pytest

from custom_components.hydroqc.coordinator.sensor_data import SensorDataMixin

_WINTER_DATA: dict[str, list[dict[str, int]]] = {"periodesHiver": [{}]}
_NO_PERIODS: dict[str, list[dict[str, int]]] = {"periodesHiver": []}


class _DpcPeakHandler:
    @property
    def is_critical(self) -> bool:
        return bool(_WINTER_DATA["periodesHiver"][0]["critique"])


class _DpcContract:
    @property
    def max_critical_called_hours(self) -> int:
        return _WINTER_DATA["periodesHiver"][0]["hrsCritiquesAppeleesMax"]

    @property
    def critical_called_hours(self) -> int:
        return _NO_PERIODS["periodesHiver"][0]["hrsCritiquesAppelees"]

    @property
    def peak_handler(self) -> _DpcPeakHandler:
        return _DpcPeakHandler()


class _CalendarPeakHandler:
    @property
    def next_peak(self) -> Any:
        return _NO_PERIODS["periodesHiver"][0]

    @property
    def current_peak(self) -> Any:
        return _WINTER_DATA["periodesHiver"][0]["pointe"]


class _Coordinator(SensorDataMixin):
    def __init__(self) -> None:
        self.data = {"contract": _DpcContract()}
        self.periods_unavailable = False
        self.rate_with_option = "DPC"
        self.calendar_peak_handler = _CalendarPeakHandler()


@pytest.mark.parametrize(
    ("data_source", "expected"),
    [
        ("contract.max_critical_called_hours", None),
        ("contract.critical_called_hours", None),
        ("contract.peak_handler.is_critical", False),
        ("calendar_peak_handler.next_peak.is_critical", False),
        ("calendar_peak_handler.current_peak", None),
    ],
)
def test_get_sensor_value_handles_missing_payload_keys(data_source: str, expected: Any) -> None:
    assert _Coordinator().get_sensor_value(data_source) is expected
