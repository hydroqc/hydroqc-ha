"""Coordinator package for Hydro-Québec integration."""

# Re-export dependencies for backward compatibility (used by tests)
from hydroqc.webuser import WebUser

from .. import calendar_manager
from ..public_data_client import PublicDataClient
from .base import HydroQcDataCoordinator

__all__ = ["HydroQcDataCoordinator", "PublicDataClient", "WebUser", "calendar_manager"]
