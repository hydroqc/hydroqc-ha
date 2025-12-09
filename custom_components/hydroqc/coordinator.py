"""DataUpdateCoordinator for Hydro-Québec integration.

This module re-exports the HydroQcDataCoordinator from the coordinator package
and related imports for backward compatibility with tests and other modules.
"""

# Re-export main coordinator class
# Re-export dependencies for backward compatibility (used by tests)
from hydroqc.webuser import WebUser

from . import calendar_manager
from .coordinator import HydroQcDataCoordinator
from .public_data_client import PublicDataClient

__all__ = ["HydroQcDataCoordinator", "PublicDataClient", "WebUser", "calendar_manager"]
