"""Public data package for Hydro-Québec winter peaks."""

from .client import PublicDataClient
from .models import AnchorPeriod, PeakEvent, PreHeatPeriod
from .normalize import extract_records, normalize_event, normalize_sector
from .offers import PEAK_OFFERS, is_known_offer, normalize_offer, offers_for_rate
from .peak_handler import RATE_CODE_MAPPING, PeakHandler

__all__ = [
    "PEAK_OFFERS",
    "RATE_CODE_MAPPING",
    "AnchorPeriod",
    "PeakEvent",
    "PeakHandler",
    "PreHeatPeriod",
    "PublicDataClient",
    "extract_records",
    "is_known_offer",
    "normalize_event",
    "normalize_offer",
    "normalize_sector",
    "offers_for_rate",
]
