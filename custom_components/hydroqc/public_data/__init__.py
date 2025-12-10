"""Public data package for Hydro-Québec OpenData (residential rates only)."""

from .client import PublicDataClient
from .models import AnchorPeriod, PeakEvent, PreHeatPeriod
from .opendata_client import OpenDataClient
from .peak_handler import RATE_CODE_MAPPING, PeakHandler
from .processors import DatasetProcessor, PeakEventsProcessor

__all__ = [
    "RATE_CODE_MAPPING",
    "AnchorPeriod",
    "DatasetProcessor",
    "OpenDataClient",
    "PeakEvent",
    "PeakEventsProcessor",
    "PeakHandler",
    "PreHeatPeriod",
    "PublicDataClient",
]
