"""Base processor interface for OpenData datasets."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DatasetProcessor(ABC):
    """Abstract base class for dataset-specific processors.

    Each processor handles a specific OpenData dataset and implements
    the logic for fetching, filtering, and processing its data.
    """

    @abstractmethod
    def get_dataset_name(self) -> str:
        """Get the name of the dataset this processor handles.

        Returns:
            Dataset name (e.g., "evenements-pointe", "demande-electricite-quebec")
        """

    @abstractmethod
    def build_fetch_params(self) -> dict[str, Any]:
        """Build query parameters for fetching data from the dataset.

        Returns:
            Dictionary of query parameters for the Opendatasoft API
        """

    @abstractmethod
    async def process_response(self, data: dict[str, Any]) -> None:
        """Process the API response data.

        This method should extract and store relevant information from
        the API response, performing any necessary transformations or filtering.

        Args:
            data: Raw JSON response from the OpenData API
        """
