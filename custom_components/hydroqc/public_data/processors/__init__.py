"""Processors for OpenData datasets."""

from .base import DatasetProcessor
from .peak_events import PeakEventsProcessor

__all__ = [
    "DatasetProcessor",
    "PeakEventsProcessor",
]
