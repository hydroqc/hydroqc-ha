"""Constants for the Hydro-Québec integration."""

from typing import Final

DOMAIN: Final = "hydroqc"

# Config flow constants
CONF_CONTRACT_ID: Final = "contract_id"
CONF_ACCOUNT_ID: Final = "account_id"
CONF_CUSTOMER_ID: Final = "customer_id"
CONF_CONTRACT_NAME: Final = "contract_name"
CONF_RATE: Final = "rate"
CONF_RATE_OPTION: Final = "rate_option"
CONF_AUTH_MODE: Final = "auth_mode"
CONF_PREHEAT_DURATION: Final = "preheat_duration_minutes"
CONF_UPDATE_INTERVAL: Final = "update_interval"
CONF_HISTORY_DAYS: Final = "history_days"
CONF_CALENDAR_ENTITY_ID: Final = "calendar_entity_id"

# Auth modes
AUTH_MODE_PORTAL: Final = "portal"
AUTH_MODE_OPENDATA: Final = "opendata"

# Defaults
DEFAULT_UPDATE_INTERVAL: Final = 60  # seconds
DEFAULT_PREHEAT_DURATION: Final = 120  # minutes

# Supported rates
RATE_D: Final = "D"
RATE_DT: Final = "DT"
RATE_DPC: Final = "DPC"
RATE_M: Final = "M"
RATE_M_GDP: Final = "M-GDP"

RATES: Final = [RATE_D, RATE_DT, RATE_DPC, RATE_M, RATE_M_GDP]

# Rate options
RATE_OPTION_CPC: Final = "CPC"
RATE_OPTION_NONE: Final = ""

# Rate option mappings (which options are valid for which rates)
RATE_OPTIONS: Final = {
    RATE_D: [RATE_OPTION_NONE, RATE_OPTION_CPC],
    RATE_DT: [RATE_OPTION_NONE],
    RATE_DPC: [RATE_OPTION_NONE],
    RATE_M: [RATE_OPTION_NONE],
    RATE_M_GDP: [RATE_OPTION_NONE],
}

# Sensor definitions ported from hydroqc2mqtt
# Each sensor has: name, data_source, device_class, state_class, icon, unit, rates
SENSORS: Final = {
    # Account sensors
    "balance": {
        "name": "Balance",
        "data_source": "account.balance",
        "device_class": "monetary",
        "state_class": "total",
        "icon": "mdi:currency-usd",
        "unit": "CAD",
        "rates": ["ALL"],
    },
    # Contract sensors - Current billing period
    "current_billing_period_current_day": {
        "name": "Current Billing Period Current Day",
        "data_source": "contract.cp_current_day",
        "device_class": None,
        "state_class": "measurement",
        "icon": "mdi:calendar-start",
        "unit": "days",
        "rates": ["ALL"],
    },
    "current_billing_period_duration": {
        "name": "Current Billing Period Duration",
        "data_source": "contract.cp_duration",
        "device_class": None,
        "state_class": "measurement",
        "icon": "mdi:calendar-expand-horizontal",
        "unit": "days",
        "rates": ["ALL"],
    },
    "current_billing_period_total_to_date": {
        "name": "Current Billing Period Total To Date",
        "data_source": "contract.cp_current_bill",
        "device_class": "monetary",
        "state_class": "total",
        "icon": "mdi:currency-usd",
        "unit": "CAD",
        "rates": ["ALL"],
    },
    "current_billing_period_projected_bill": {
        "name": "Current Billing Period Projected Bill",
        "data_source": "contract.cp_projected_bill",
        "device_class": "monetary",
        "state_class": "total",
        "icon": "mdi:currency-usd",
        "unit": "CAD",
        "rates": ["ALL"],
    },
    "current_billing_period_daily_bill_mean": {
        "name": "Current Billing Period Daily Bill Mean",
        "data_source": "contract.cp_daily_bill_mean",
        "device_class": "monetary",
        "state_class": "total",
        "icon": "mdi:currency-usd",
        "unit": "CAD",
        "rates": ["ALL"],
    },
    "current_billing_period_daily_consumption_mean": {
        "name": "Current Billing Period Daily Consumption Mean",
        "data_source": "contract.cp_daily_consumption_mean",
        "device_class": "energy",
        "icon": "mdi:home-lightning-bolt",
        "unit": "kWh",
        "rates": ["ALL"],
    },
    "current_billing_period_total_consumption": {
        "name": "Current Billing Period Total Consumption",
        "data_source": "contract.cp_total_consumption",
        "device_class": "energy",
        "state_class": "total_increasing",
        "icon": "mdi:home-lightning-bolt",
        "unit": "kWh",
        "rates": ["ALL"],
    },
    "current_billing_period_projected_total_consumption": {
        "name": "Current Billing Period Projected Total Consumption",
        "data_source": "contract.cp_projected_total_consumption",
        "device_class": "energy",
        "icon": "mdi:home-lightning-bolt",
        "unit": "kWh",
        "rates": ["ALL"],
    },
    "current_billing_period_average_temperature": {
        "name": "Current Billing Period Average Temperature",
        "data_source": "contract.cp_average_temperature",
        "device_class": "temperature",
        "state_class": "measurement",
        "icon": "mdi:thermometer",
        "unit": "°C",
        "rates": ["ALL"],
    },
    "current_billing_period_kwh_cost_mean": {
        "name": "Current Billing Period kWh Cost Mean",
        "data_source": "contract.cp_kwh_cost_mean",
        "device_class": "monetary",
        "state_class": "total",
        "icon": "mdi:currency-usd",
        "unit": "CAD/kWh",
        "rates": ["ALL"],
    },
    "current_billing_period_rate": {
        "name": "Current Billing Period Rate",
        "data_source": "contract.rate",
        "device_class": None,
        "state_class": None,
        "icon": "mdi:playlist-check",
        "unit": None,
        "rates": ["ALL"],
    },
    "current_billing_period_rate_option": {
        "name": "Current Billing Period Rate Option",
        "data_source": "contract.rate_option",
        "device_class": None,
        "state_class": None,
        "icon": "mdi:playlist-star",
        "unit": None,
        "rates": ["ALL"],
    },
    # Outage sensor with attributes
    "outage": {
        "name": "Next Or Current Outage",
        "data_source": "contract.next_outage.start_date",
        "device_class": "timestamp",
        "icon": "mdi:calendar-start",
        "rates": ["ALL"],
        "attributes": {
            "end_date": "contract.next_outage.end_date",
            "cause": "contract.next_outage.cause.name",
            "planned_duration": "contract.next_outage.planned_duration",
            "code": "contract.next_outage.code.name",
            "state": "contract.next_outage.status.name",
            "emergency_level": "contract.next_outage.emergency_level",
            "is_planned": "contract.next_outage.is_planned",
        },
    },
    # FlexD and DT sensors
    "current_billing_period_higher_price_consumption": {
        "name": "Current Billing Period Higher Price Consumption",
        "data_source": "contract.cp_higher_price_consumption",
        "device_class": "energy",
        "icon": "mdi:home-lightning-bolt",
        "unit": "kWh",
        "rates": ["DT", "DPC"],
    },
    "current_billing_period_lower_price_consumption": {
        "name": "Current Billing Period Lower Price Consumption",
        "data_source": "contract.cp_lower_price_consumption",
        "device_class": "energy",
        "icon": "mdi:home-lightning-bolt-outline",
        "unit": "kWh",
        "rates": ["DT", "DPC"],
    },
    "amount_saved_vs_base_rate": {
        "name": "Net Saving/Loss vs Rate D",
        "data_source": "contract.amount_saved_vs_base_rate",
        "device_class": "monetary",
        "state_class": "total",
        "icon": "mdi:currency-usd",
        "unit": "CAD",
        "rates": ["DT", "DPC"],
    },
    # DPC (Flex-D) sensors
    "dpc_state": {
        "name": "Current DPC Period Detail",
        "data_source": "public_client.peak_handler.current_state",
        "device_class": None,
        "icon": None,
        "unit": None,
        "rates": ["DPC"],
    },
    "dpc_next_peak_start": {
        "name": "Next Peak Start",
        "data_source": "public_client.peak_handler.next_peak.start_date",
        "device_class": "timestamp",
        "icon": "mdi:clock-start",
        "rates": ["DPC"],
    },
    "dpc_next_peak_end": {
        "name": "Next Peak End",
        "data_source": "public_client.peak_handler.next_peak.end_date",
        "device_class": "timestamp",
        "icon": "mdi:clock-end",
        "rates": ["DPC"],
    },
    "dpc_next_pre_heat_start": {
        "name": "Next Pre-heat Start",
        "data_source": "public_client.peak_handler.next_peak.preheat.start_date",
        "device_class": "timestamp",
        "icon": "mdi:clock-start",
        "rates": ["DPC"],
    },
    "dpc_critical_hours_count": {
        "name": "Number of Critical Hours",
        "data_source": "contract.critical_called_hours",
        "icon": "mdi:clock-alert-outline",
        "rates": ["DPC"],
        "attributes": {
            "max": "contract.max_critical_called_hours",
        },
    },
    "dpc_winter_days_count": {
        "name": "Number of Winter Days",
        "data_source": "contract.winter_total_days_last_update",
        "icon": "mdi:calendar-range-outline",
        "rates": ["DPC"],
        "attributes": {
            "max": "contract.winter_total_days",
        },
    },
    # Winter Credits (DCPC) sensors
    "wc_state": {
        "name": "Current WC Period Detail",
        "data_source": "public_client.peak_handler.current_state",
        "device_class": None,
        "icon": None,
        "unit": None,
        "rates": ["DCPC"],
    },
    "wc_cumulated_credit": {
        "name": "Cumulated Winter Credit",
        "data_source": "contract.peak_handler.cumulated_credit",
        "device_class": "monetary",
        "state_class": "total",
        "icon": "mdi:currency-usd",
        "unit": "CAD",
        "rates": ["DCPC"],
    },
    "wc_projected_cumulated_credit": {
        "name": "Projected Cumulated Winter Credit",
        "data_source": "contract.peak_handler.projected_cumulated_credit",
        "device_class": "monetary",
        "state_class": "total",
        "icon": "mdi:currency-usd",
        "unit": "CAD",
        "rates": ["DCPC"],
    },
    "wc_next_anchor_start": {
        "name": "Next Anchor Start",
        "data_source": "public_client.peak_handler.next_peak.anchor.start_date",
        "device_class": "timestamp",
        "icon": "mdi:clock-start",
        "rates": ["DCPC"],
        "attributes": {
            "critical": "public_client.peak_handler.next_peak.is_critical",
        },
    },
    "wc_next_anchor_end": {
        "name": "Next Anchor End",
        "data_source": "public_client.peak_handler.next_peak.anchor.end_date",
        "device_class": "timestamp",
        "icon": "mdi:clock-end",
        "rates": ["DCPC"],
        "attributes": {
            "critical": "public_client.peak_handler.next_peak.is_critical",
        },
    },
    "wc_next_peak_start": {
        "name": "Next Peak Start",
        "data_source": "public_client.peak_handler.next_peak.start_date",
        "device_class": "timestamp",
        "icon": "mdi:clock-start",
        "rates": ["DCPC"],
        "attributes": {
            "critical": "public_client.peak_handler.next_peak.is_critical",
        },
    },
    "wc_next_peak_end": {
        "name": "Next Peak End",
        "data_source": "public_client.peak_handler.next_peak.end_date",
        "device_class": "timestamp",
        "icon": "mdi:clock-end",
        "rates": ["DCPC"],
        "attributes": {
            "critical": "public_client.peak_handler.next_peak.is_critical",
        },
    },
    "wc_next_critical_peak_start": {
        "name": "Next Critical Peak Start",
        "data_source": "public_client.peak_handler.next_critical_peak.start_date",
        "device_class": "timestamp",
        "icon": "mdi:clock-start",
        "rates": ["DCPC"],
    },
    "wc_next_critical_peak_end": {
        "name": "Next Critical Peak End",
        "data_source": "public_client.peak_handler.next_critical_peak.end_date",
        "device_class": "timestamp",
        "icon": "mdi:clock-end",
        "rates": ["DCPC"],
    },
    "wc_next_pre_heat_start": {
        "name": "Next Pre-heat Start",
        "data_source": "public_client.peak_handler.next_peak.preheat.start_date",
        "device_class": "timestamp",
        "icon": "mdi:clock-start",
        "rates": ["DCPC"],
        "attributes": {
            "critical": "public_client.peak_handler.next_peak.is_critical",
        },
    },
    # Yesterday's winter credit performance
    "wc_yesterday_morning_peak_credit": {
        "name": "Yesterday Morning Peak Saved Credit",
        "data_source": "contract.peak_handler.yesterday_morning_peak.credit",
        "device_class": "monetary",
        "state_class": "total",
        "icon": "mdi:currency-usd",
        "unit": "CAD",
        "rates": ["DCPC"],
    },
    "wc_yesterday_morning_peak_actual_consumption": {
        "name": "Yesterday Morning Peak Actual Consumption",
        "data_source": "contract.peak_handler.yesterday_morning_peak.actual_consumption",
        "device_class": "energy",
        "icon": "mdi:home-lightning-bolt",
        "unit": "kWh",
        "rates": ["DCPC"],
    },
    "wc_yesterday_morning_peak_ref_consumption": {
        "name": "Yesterday Morning Peak Reference Consumption",
        "data_source": "contract.peak_handler.yesterday_morning_peak.ref_consumption",
        "device_class": "energy",
        "icon": "mdi:home-lightning-bolt",
        "unit": "kWh",
        "rates": ["DCPC"],
    },
    "wc_yesterday_morning_peak_saved_consumption": {
        "name": "Yesterday Morning Peak Saved Consumption",
        "data_source": "contract.peak_handler.yesterday_morning_peak.saved_consumption",
        "device_class": "energy",
        "icon": "mdi:home-lightning-bolt",
        "unit": "kWh",
        "rates": ["DCPC"],
    },
    "wc_yesterday_evening_peak_credit": {
        "name": "Yesterday Evening Peak Saved Credit",
        "data_source": "contract.peak_handler.yesterday_evening_peak.credit",
        "device_class": "monetary",
        "state_class": "total",
        "icon": "mdi:currency-usd",
        "unit": "CAD",
        "rates": ["DCPC"],
    },
    "wc_yesterday_evening_peak_actual_consumption": {
        "name": "Yesterday Evening Peak Actual Consumption",
        "data_source": "contract.peak_handler.yesterday_evening_peak.actual_consumption",
        "device_class": "energy",
        "icon": "mdi:home-lightning-bolt",
        "unit": "kWh",
        "rates": ["DCPC"],
    },
    "wc_yesterday_evening_peak_ref_consumption": {
        "name": "Yesterday Evening Peak Reference Consumption",
        "data_source": "contract.peak_handler.yesterday_evening_peak.ref_consumption",
        "device_class": "energy",
        "icon": "mdi:home-lightning-bolt",
        "unit": "kWh",
        "rates": ["DCPC"],
    },
    "wc_yesterday_evening_peak_saved_consumption": {
        "name": "Yesterday Evening Peak Saved Consumption",
        "data_source": "contract.peak_handler.yesterday_evening_peak.saved_consumption",
        "device_class": "energy",
        "icon": "mdi:home-lightning-bolt",
        "unit": "kWh",
        "rates": ["DCPC"],
    },
}

BINARY_SENSORS: Final = {
    # Contract binary sensors
    "current_period_epp_enabled": {
        "name": "Current Period EPP Enabled",
        "data_source": "contract.cp_epp_enabled",
        "icon": "mdi:code-equal",
        "rates": ["ALL"],
    },
    # Winter Credits binary sensors
    "wc_critical": {
        "name": "Critical",
        "data_source": "public_client.peak_handler.next_peak.is_critical",
        "icon": "mdi:flash-alert",
        "rates": ["DCPC"],
    },
    "wc_critical_peak_in_progress": {
        "name": "Critical Peak In Progress",
        "data_source": "public_client.peak_handler.current_peak_is_critical",
        "icon": "mdi:flash-alert",
        "rates": ["DCPC"],
    },
    "wc_pre_heat": {
        "name": "Pre-heat In Progress",
        "data_source": "public_client.peak_handler.preheat_in_progress",
        "icon": "mdi:flash-alert",
        "rates": ["DCPC"],
    },
    "wc_next_anchor_critical": {
        "name": "Next Anchor Period Critical",
        "data_source": "public_client.peak_handler.next_anchor.is_critical",
        "icon": "mdi:flash-alert",
        "rates": ["DCPC"],
    },
    "wc_next_peak_critical": {
        "name": "Next Peak Period Critical",
        "data_source": "public_client.peak_handler.next_peak.is_critical",
        "icon": "mdi:flash-alert",
        "rates": ["DCPC"],
    },
    "wc_upcoming_critical_peak": {
        "name": "Upcoming Critical Peak",
        "data_source": "public_client.peak_handler.is_any_critical_peak_coming",
        "icon": "mdi:flash-alert",
        "rates": ["DCPC"],
    },
    "wc_critical_morning_peak_today": {
        "name": "Critical Morning Peak Today",
        "data_source": "public_client.peak_handler.today_morning_peak.is_critical",
        "icon": "mdi:message-flash",
        "rates": ["DCPC"],
    },
    "wc_critical_evening_peak_today": {
        "name": "Critical Evening Peak Today",
        "data_source": "public_client.peak_handler.today_evening_peak.is_critical",
        "icon": "mdi:message-flash",
        "rates": ["DCPC"],
    },
    "wc_critical_morning_peak_tomorrow": {
        "name": "Critical Morning Peak Tomorrow",
        "data_source": "public_client.peak_handler.tomorrow_morning_peak.is_critical",
        "icon": "mdi:message-flash",
        "rates": ["DCPC"],
    },
    "wc_critical_evening_peak_tomorrow": {
        "name": "Critical Evening Peak Tomorrow",
        "data_source": "public_client.peak_handler.tomorrow_evening_peak.is_critical",
        "icon": "mdi:message-flash",
        "rates": ["DCPC"],
    },
    # DPC binary sensors
    "dpc_pre_heat": {
        "name": "Pre-heat In Progress",
        "data_source": "public_client.peak_handler.preheat_in_progress",
        "icon": "mdi:flash-alert",
        "rates": ["DPC"],
    },
    "dpc_peak_in_progress": {
        "name": "Critical Peak In Progress",
        "data_source": "public_client.peak_handler.peak_in_progress",
        "icon": "mdi:flash-alert",
        "rates": ["DPC"],
    },
    "dpc_critical_morning_peak_today": {
        "name": "Critical Morning Peak Today",
        "data_source": "public_client.peak_handler.today_morning_peak.is_critical",
        "icon": "mdi:message-flash",
        "rates": ["DPC"],
    },
    "dpc_critical_evening_peak_today": {
        "name": "Critical Evening Peak Today",
        "data_source": "public_client.peak_handler.today_evening_peak.is_critical",
        "icon": "mdi:message-flash",
        "rates": ["DPC"],
    },
    "dpc_critical_morning_peak_tomorrow": {
        "name": "Critical Morning Peak Tomorrow",
        "data_source": "public_client.peak_handler.tomorrow_morning_peak.is_critical",
        "icon": "mdi:message-flash",
        "rates": ["DPC"],
    },
    "dpc_critical_evening_peak_tomorrow": {
        "name": "Critical Evening Peak Tomorrow",
        "data_source": "public_client.peak_handler.tomorrow_evening_peak.is_critical",
        "icon": "mdi:message-flash",
        "rates": ["DPC"],
    },
}
