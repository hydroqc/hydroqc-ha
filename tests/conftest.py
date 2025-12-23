"""Fixtures for Hydro-Québec integration tests."""

from collections.abc import Generator
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.components.recorder import Recorder
from homeassistant.components.recorder.models import StatisticMeanType
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hydroqc.const import (
    AUTH_MODE_PORTAL,
    CONF_ACCOUNT_ID,
    CONF_AUTH_MODE,
    CONF_CONTRACT_ID,
    CONF_CONTRACT_NAME,
    CONF_CUSTOMER_ID,
    CONF_PREHEAT_DURATION,
    CONF_RATE,
    CONF_RATE_OPTION,
    DOMAIN,
)

# Timezone for all date/time operations
EST_TIMEZONE = ZoneInfo("America/Toronto")


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a mock config entry for testing."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Test Account",
        data={
            CONF_AUTH_MODE: AUTH_MODE_PORTAL,
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "test_password",
            CONF_CUSTOMER_ID: "test_customer_id",
            CONF_ACCOUNT_ID: "test_account_id",
            CONF_CONTRACT_ID: "contract123",
            CONF_CONTRACT_NAME: "Home",
            CONF_RATE: "D",
            CONF_RATE_OPTION: "",
            CONF_PREHEAT_DURATION: 120,
        },
        unique_id="contract123",
    )


@pytest.fixture
def mock_webuser() -> MagicMock:
    """Return a mock WebUser instance."""
    webuser = MagicMock()
    webuser.login = AsyncMock(return_value=True)
    webuser.session_expired = False
    webuser.close_session = AsyncMock()
    webuser.get_info = AsyncMock()
    webuser.fetch_customers_info = AsyncMock()
    webuser.check_hq_portal_status = AsyncMock(return_value=True)
    webuser.get_customer = MagicMock()

    # Mock customer
    customer = MagicMock()
    customer.customer_id = "test_customer_id"
    customer.get_info = AsyncMock()
    customer.get_account = MagicMock()

    # Mock account
    account = MagicMock()
    account.account_id = "test_account_id"
    account.balance = 123.45
    account.get_contract = MagicMock()

    # Mock contract
    contract = MagicMock()
    contract.contract_id = "test_contract_id"
    contract.rate = "D"
    contract.rate_option = ""
    contract.address = "123 Test St"
    contract.cp_current_bill = 45.67
    contract.cp_current_kWh = 350
    contract.cp_avg_kWh = 320
    contract.cp_projection_price = 75.00
    contract.cp_projection_kwh = 500
    contract.cp_avg_bill = 55.00
    contract.cp_start_date = datetime(2024, 11, 1, tzinfo=EST_TIMEZONE).date()
    contract.cp_end_date = datetime(2024, 11, 30, tzinfo=EST_TIMEZONE).date()
    contract.get_periods_info = AsyncMock()
    contract.refresh_outages = AsyncMock()
    contract.get_hourly_consumption = AsyncMock()
    contract.get_csv_consumption_history = AsyncMock()

    # Link objects
    customer.accounts = [account]
    account.contracts = [contract]
    webuser.customers = [customer]

    # Setup return values for get methods to return from lists
    def get_customer(customer_id: str) -> MagicMock:
        return webuser.customers[0]

    def get_account(account_id: str) -> MagicMock:
        return customer.accounts[0]

    def get_contract(contract_id: str) -> MagicMock:
        return account.contracts[0]

    webuser.get_customer = get_customer
    customer.get_account = get_account
    account.get_contract = get_contract

    return webuser


@pytest.fixture
def mock_contract() -> MagicMock:
    """Return a mock Contract instance."""
    contract = MagicMock()
    contract.contract_id = "test_contract_id"
    contract.rate = "D"
    contract.rate_option = ""
    contract.address = "123 Test St"
    contract.cp_current_bill = 45.67
    contract.cp_current_kWh = 350
    contract.cp_avg_kWh = 320
    contract.cp_projection_price = 75.00
    contract.cp_projection_kwh = 500
    contract.cp_avg_bill = 55.00
    contract.cp_start_date = datetime(2024, 11, 1, tzinfo=EST_TIMEZONE).date()
    contract.cp_end_date = datetime(2024, 11, 30, tzinfo=EST_TIMEZONE).date()

    # Mock methods
    contract.get_info = AsyncMock()
    contract.get_periods_info = AsyncMock()
    contract.refresh_outages = AsyncMock()
    contract.get_hourly_consumption = AsyncMock(
        return_value={"results": {"listeDonneesConsoEnergieHoraire": []}}
    )
    contract.get_hourly_energy = AsyncMock(
        return_value={
            "results": {
                "listeDonneesConsoEnergieHoraire": [
                    {
                        "dateHeureDebutPeriode": "2024-11-26 00:00",
                        "consoReg": 1.234,
                    },
                    {
                        "dateHeureDebutPeriode": "2024-11-26 01:00",
                        "consoReg": 1.567,
                    },
                ]
            }
        }
    )

    return contract


@pytest.fixture
def mock_contract_dpc() -> MagicMock:
    """Return a mock ContractDPC instance with peak handler."""
    contract = MagicMock()
    contract.contract_id = "test_contract_dpc"
    contract.rate = "DPC"
    contract.rate_option = ""
    contract.address = "456 Peak St"
    contract.cp_current_bill = 55.00
    contract.cp_current_kWh = 400
    contract.cp_avg_kWh = 380
    contract.cp_projection_price = 85.00
    contract.cp_projection_kwh = 600
    contract.cp_avg_bill = 65.00
    contract.cp_start_date = datetime(2024, 11, 1, tzinfo=EST_TIMEZONE).date()
    contract.cp_end_date = datetime(2024, 11, 30, tzinfo=EST_TIMEZONE).date()

    # Mock peak handler
    peak_handler = MagicMock()
    peak_handler.current_state = "Regular"
    peak_handler.next_event_date = datetime(2024, 12, 15, 13, 0, tzinfo=EST_TIMEZONE)
    peak_handler.next_event_hour = "13"
    peak_handler.is_critical = False
    peak_handler.is_preheat = False
    peak_handler.critical_peak_count = 2
    contract.peak_handler = peak_handler

    # Mock methods
    contract.get_info = AsyncMock()
    contract.get_periods_info = AsyncMock()
    contract.refresh_outages = AsyncMock()
    contract.get_hourly_consumption = AsyncMock(
        return_value={"results": {"listeDonneesConsoEnergieHoraire": []}}
    )
    contract.get_annual_consumption = AsyncMock()
    contract.get_dpc_data = AsyncMock()

    # Mock peak_handler methods
    peak_handler.refresh_data = AsyncMock()

    contract.get_hourly_energy = AsyncMock(
        return_value={
            "results": {
                "listeDonneesConsoEnergieHoraire": [
                    {
                        "dateHeureDebutPeriode": "2024-11-26 00:00",
                        "consoReg": 1.234,
                    },
                ]
            }
        }
    )

    return contract


@pytest.fixture
def mock_contract_dcpc() -> MagicMock:
    """Return a mock ContractDCPC instance with winter credits."""
    contract = MagicMock()
    contract.contract_id = "test_contract_dcpc"
    contract.rate = "D"
    contract.rate_option = "CPC"
    contract.address = "789 Credit St"
    contract.cp_current_bill = 50.00
    contract.cp_current_kWh = 375
    contract.cp_avg_kWh = 350
    contract.cp_projection_price = 80.00
    contract.cp_projection_kwh = 550
    contract.cp_avg_bill = 60.00
    contract.cp_start_date = datetime(2024, 11, 1, tzinfo=EST_TIMEZONE).date()
    contract.cp_end_date = datetime(2024, 11, 30, tzinfo=EST_TIMEZONE).date()

    # Mock peak handler with winter credits
    peak_handler = MagicMock()
    peak_handler.cumulated_credit = 5.25
    peak_handler.yesterday_peak_performance = "Good"
    peak_handler.yesterday_peak_hour = "17"
    peak_handler.current_state = "Regular"
    peak_handler.next_event_date = datetime(2024, 12, 10, 17, 0, tzinfo=EST_TIMEZONE)
    peak_handler.next_event_hour = "17"
    peak_handler.is_critical = False
    contract.peak_handler = peak_handler

    # Mock methods
    contract.get_info = AsyncMock()
    contract.get_periods_info = AsyncMock()
    contract.refresh_outages = AsyncMock()
    contract.get_hourly_consumption = AsyncMock(
        return_value={"results": {"listeDonneesConsoEnergieHoraire": []}}
    )

    # Mock peak_handler methods
    peak_handler.refresh_data = AsyncMock()

    contract.get_hourly_energy = AsyncMock(
        return_value={
            "results": {
                "listeDonneesConsoEnergieHoraire": [
                    {
                        "dateHeureDebutPeriode": "2024-11-26 00:00",
                        "consoReg": 1.234,
                    },
                ]
            }
        }
    )

    return contract


@pytest.fixture
def sample_statistics() -> list[dict[str, Any]]:
    """Return sample statistics for testing."""
    base_time = datetime(2024, 11, 26, 0, 0, tzinfo=EST_TIMEZONE)
    stats = []
    cumulative = 0.0

    for hour in range(24):
        consumption = 1.5 + (hour % 3) * 0.5
        cumulative += consumption
        stats.append(
            {
                "start": base_time.replace(hour=hour).timestamp(),
                "state": consumption,
                "sum": cumulative,
            }
        )

    return stats


@pytest.fixture
def sample_csv_data() -> str:
    """Return sample CSV data for testing."""
    return """Date,Heure début,Heure fin,Consommation (kWh)
2024-11-26,00:00,01:00,1.234
2024-11-26,01:00,02:00,1.567
2024-11-26,02:00,03:00,1.890
"""


@pytest.fixture
def sample_hourly_json() -> dict[str, Any]:
    """Return sample hourly consumption JSON for testing."""
    return {
        "results": {
            "listeDonneesConsoEnergieHoraire": [
                {
                    "dateHeureDebutPeriode": "2024-11-26 00:00",
                    "consoReg": 1.234,
                    "consoHaut": None,
                    "consoTotal": 1.234,
                },
                {
                    "dateHeureDebutPeriode": "2024-11-26 01:00",
                    "consoReg": 1.567,
                    "consoHaut": None,
                    "consoTotal": 1.567,
                },
                {
                    "dateHeureDebutPeriode": "2024-11-26 02:00",
                    "consoReg": 1.890,
                    "consoHaut": None,
                    "consoTotal": 1.890,
                },
            ]
        }
    }


@pytest.fixture
def mock_recorder_instance() -> Generator[MagicMock]:
    """Mock the recorder instance."""
    with patch("custom_components.hydroqc.coordinator.get_instance") as mock:
        instance = MagicMock(spec=Recorder)
        instance.async_add_executor_job = AsyncMock()
        mock.return_value = instance
        yield instance


@pytest.fixture
def mock_statistics_api() -> Generator[MagicMock]:
    """Mock the recorder statistics API."""
    with patch("homeassistant.components.recorder.statistics") as mock:
        mock.async_add_external_statistics = MagicMock()
        mock.get_last_statistics = MagicMock(return_value={})
        mock.list_statistic_ids = MagicMock(return_value=[])
        mock.clear_statistics = MagicMock()
        yield mock


@pytest.fixture
def statistics_metadata() -> dict[str, Any]:
    """Return sample statistics metadata."""
    return {
        "source": "hydroqc",
        "statistic_id": "hydroqc:test_contract_id_total_hourly_consumption",
        "unit_of_measurement": "kWh",
        "has_mean": False,
        "has_sum": True,
        "mean_type": StatisticMeanType.NONE,
        "name": "Total Hourly Consumption",
        "unit_class": "energy",
    }


@pytest.fixture
def mock_integration_version() -> Generator[AsyncMock]:
    """Mock the integration version API for both sensor and binary_sensor."""
    mock_integration = MagicMock()
    mock_integration.version = "0.1.4-beta.1"

    # Patch where it's imported (in sensor.py and binary_sensor.py)
    with (
        patch(
            "custom_components.hydroqc.sensor.async_get_integration",
            new=AsyncMock(return_value=mock_integration),
        ) as mock_sensor,
        patch(
            "custom_components.hydroqc.binary_sensor.async_get_integration",
            new=AsyncMock(return_value=mock_integration),
        ),
    ):
        yield mock_sensor


@pytest.fixture
async def hass_with_recorder(hass: HomeAssistant) -> HomeAssistant:
    """Return a Home Assistant instance with recorder set up."""
    # The recorder component will be automatically set up by pytest-homeassistant
    # Just return the hass instance
    return hass


# OpenData mode fixtures


@pytest.fixture
def mock_config_entry_opendata() -> MockConfigEntry:
    """Return a mock config entry for OpenData mode testing."""
    from custom_components.hydroqc.const import AUTH_MODE_OPENDATA

    return MockConfigEntry(
        domain=DOMAIN,
        title="Test OpenData DPC",
        data={
            CONF_AUTH_MODE: AUTH_MODE_OPENDATA,
            CONF_RATE: "DPC",
            CONF_RATE_OPTION: "",
            CONF_PREHEAT_DURATION: 120,
        },
        unique_id="opendata_dpc",
    )


@pytest.fixture
def mock_config_entry_opendata_dcpc() -> MockConfigEntry:
    """Return a mock config entry for OpenData mode DCPC testing."""
    from custom_components.hydroqc.const import AUTH_MODE_OPENDATA

    return MockConfigEntry(
        domain=DOMAIN,
        title="Test OpenData DCPC",
        data={
            CONF_AUTH_MODE: AUTH_MODE_OPENDATA,
            CONF_RATE: "D",
            CONF_RATE_OPTION: "CPC",
            CONF_PREHEAT_DURATION: 120,
        },
        unique_id="opendata_dcpc",
    )


@pytest.fixture
def mock_public_client() -> MagicMock:
    """Return a mock PublicDataClient instance."""
    client = MagicMock()
    client.rate_code = "DPC"
    client.fetch_peak_data = AsyncMock()
    client.close_session = AsyncMock()

    # Mock peak handler
    peak_handler = MagicMock()
    peak_handler.current_state = "normal"
    peak_handler.next_peak = None
    peak_handler.next_critical_peak = None
    peak_handler.current_peak = None
    peak_handler.preheat_in_progress = False
    peak_handler.peak_in_progress = False
    peak_handler.is_any_critical_peak_coming = False
    peak_handler.today_morning_peak = None
    peak_handler.today_evening_peak = None
    peak_handler.tomorrow_morning_peak = None
    peak_handler.tomorrow_evening_peak = None
    client.peak_handler = peak_handler

    return client


@pytest.fixture
def mock_public_client_dcpc() -> MagicMock:
    """Return a mock PublicDataClient instance for DCPC (Winter Credits)."""
    client = MagicMock()
    client.rate_code = "DCPC"
    client.fetch_peak_data = AsyncMock()
    client.close_session = AsyncMock()

    # Mock peak handler with winter credits data
    peak_handler = MagicMock()
    peak_handler.current_state = "normal"
    peak_handler.next_peak = None
    peak_handler.next_critical_peak = None
    peak_handler.current_peak = None
    peak_handler.preheat_in_progress = False
    peak_handler.peak_in_progress = False
    peak_handler.is_any_critical_peak_coming = False

    # Mock today's peaks (non-critical generated schedule)
    today_morning = MagicMock()
    today_morning.start_date = datetime(2024, 12, 15, 6, 0, tzinfo=EST_TIMEZONE)
    today_morning.end_date = datetime(2024, 12, 15, 10, 0, tzinfo=EST_TIMEZONE)
    today_morning.is_critical = False
    today_morning.time_slot = "AM"

    today_evening = MagicMock()
    today_evening.start_date = datetime(2024, 12, 15, 16, 0, tzinfo=EST_TIMEZONE)
    today_evening.end_date = datetime(2024, 12, 15, 20, 0, tzinfo=EST_TIMEZONE)
    today_evening.is_critical = False
    today_evening.time_slot = "PM"

    peak_handler.today_morning_peak = today_morning
    peak_handler.today_evening_peak = today_evening
    peak_handler.tomorrow_morning_peak = None
    peak_handler.tomorrow_evening_peak = None

    client.peak_handler = peak_handler

    return client


@pytest.fixture
def sample_opendata_api_response() -> dict[str, Any]:
    """Return sample OpenData API response for testing."""
    return {
        "total_count": 2,
        "results": [
            {
                "offre": "TPC-DPC",
                "datedebut": "2024-12-15 13:00",
                "datefin": "2024-12-15 17:00",
                "plagehoraire": "PM",
                "duree": "PT04H00MS",
                "secteurclient": "Résidentiel",
            },
            {
                "offre": "TPC-DPC",
                "datedebut": "2024-12-16 13:00",
                "datefin": "2024-12-16 17:00",
                "plagehoraire": "PM",
                "duree": "PT04H00MS",
                "secteurclient": "Résidentiel",
            },
        ],
    }


@pytest.fixture
def sample_opendata_api_response_dcpc() -> dict[str, Any]:
    """Return sample OpenData API response for DCPC (Winter Credits) testing."""
    return {
        "total_count": 2,
        "results": [
            {
                "offre": "CPC-D",
                "datedebut": "2024-12-15 06:00",
                "datefin": "2024-12-15 10:00",
                "plagehoraire": "AM",
                "duree": "PT04H00MS",
                "secteurclient": "Résidentiel",
            },
            {
                "offre": "CPC-D",
                "datedebut": "2024-12-15 16:00",
                "datefin": "2024-12-15 20:00",
                "plagehoraire": "PM",
                "duree": "PT04H00MS",
                "secteurclient": "Résidentiel",
            },
        ],
    }
