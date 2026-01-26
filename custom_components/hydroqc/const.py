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
CONF_HISTORY_DAYS: Final = "history_days"
CONF_CALENDAR_ENTITY_ID: Final = "calendar_entity_id"
CONF_ENABLE_CONSUMPTION_SYNC: Final = "enable_consumption_sync"

# Auth modes
AUTH_MODE_PORTAL: Final = "portal"
AUTH_MODE_OPENDATA: Final = "opendata"

# Defaults
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
        "data_source": "account.balance",
        "device_class": "monetary",
        "state_class": "total",
        "icon": "mdi:currency-usd",
        "unit": "CAD",
        "rates": ["ALL"],
    },
    # Contract sensors - Current billing period
    "current_billing_period_current_day": {
        "data_source": "contract.cp_current_day",
        "device_class": None,
        "state_class": "measurement",
        "icon": "mdi:calendar-start",
        "unit": "days",
        "rates": ["ALL"],
        "diagnostic": True,
    },
    "current_billing_period_duration": {
        "data_source": "contract.cp_duration",
        "device_class": None,
        "state_class": "measurement",
        "icon": "mdi:calendar-expand-horizontal",
        "unit": "days",
        "rates": ["ALL"],
        "diagnostic": True,
    },
    "current_billing_period_total_to_date": {
        "data_source": "contract.cp_current_bill",
        "device_class": "monetary",
        "state_class": "total",
        "icon": "mdi:currency-usd",
        "unit": "CAD",
        "rates": ["ALL"],
    },
    "current_billing_period_projected_bill": {
        "data_source": "contract.cp_projected_bill",
        "device_class": "monetary",
        "state_class": "total",
        "icon": "mdi:currency-usd",
        "unit": "CAD",
        "rates": ["ALL"],
    },
    "current_billing_period_daily_bill_mean": {
        "data_source": "contract.cp_daily_bill_mean",
        "device_class": "monetary",
        "state_class": "total",
        "icon": "mdi:currency-usd",
        "unit": "CAD",
        "rates": ["ALL"],
        "diagnostic": True,
    },
    "current_billing_period_daily_consumption_mean": {
        "data_source": "contract.cp_daily_consumption_mean",
        "device_class": "energy",
        "icon": "mdi:home-lightning-bolt",
        "unit": "kWh",
        "rates": ["ALL"],
        "diagnostic": True,
    },
    "current_billing_period_total_consumption": {
        "data_source": "contract.cp_total_consumption",
        "device_class": "energy",
        "state_class": "total_increasing",
        "icon": "mdi:home-lightning-bolt",
        "unit": "kWh",
        "rates": ["ALL"],
    },
    "current_billing_period_projected_total_consumption": {
        "data_source": "contract.cp_projected_total_consumption",
        "device_class": "energy",
        "icon": "mdi:home-lightning-bolt",
        "unit": "kWh",
        "rates": ["ALL"],
    },
    "current_billing_period_average_temperature": {
        "data_source": "contract.cp_average_temperature",
        "device_class": "temperature",
        "state_class": "measurement",
        "icon": "mdi:thermometer",
        "unit": "°C",
        "rates": ["ALL"],
        "diagnostic": True,
    },
    "current_billing_period_kwh_cost_mean": {
        "data_source": "contract.cp_kwh_cost_mean",
        "device_class": "monetary",
        "state_class": "total",
        "icon": "mdi:currency-usd",
        "unit": "CAD/kWh",
        "rates": ["ALL"],
        "diagnostic": True,
    },
    "current_billing_period_rate": {
        "data_source": "contract.rate",
        "device_class": None,
        "state_class": None,
        "icon": "mdi:playlist-check",
        "unit": None,
        "rates": ["ALL"],
        "diagnostic": True,
        "disabled_by_default": True,
    },
    "current_billing_period_rate_option": {
        "data_source": "contract.rate_option",
        "device_class": None,
        "state_class": None,
        "icon": "mdi:playlist-star",
        "unit": None,
        "rates": ["ALL"],
        "diagnostic": True,
        "disabled_by_default": True,
    },
    # Outage sensor with attributes
    "outage": {
        "data_source": "contract.next_outage.start_date",
        "device_class": "timestamp",
        "icon": "mdi:calendar-start",
        "rates": ["ALL"],
        "diagnostic": True,
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
        "data_source": "contract.cp_higher_price_consumption",
        "device_class": "energy",
        "icon": "mdi:home-lightning-bolt",
        "unit": "kWh",
        "rates": ["DT", "DPC"],
    },
    "current_billing_period_lower_price_consumption": {
        "data_source": "contract.cp_lower_price_consumption",
        "device_class": "energy",
        "icon": "mdi:home-lightning-bolt-outline",
        "unit": "kWh",
        "rates": ["DT", "DPC"],
    },
    "amount_saved_vs_base_rate": {
        "data_source": "contract.amount_saved_vs_base_rate",
        "device_class": "monetary",
        "state_class": "total",
        "icon": "mdi:currency-usd",
        "unit": "CAD",
        "rates": ["DT", "DPC"],
    },
    # DPC (Flex-D) sensors - sourced from calendar
    "dpc_state": {
        "data_source": "calendar_peak_handler.current_state",
        "device_class": None,
        "icon": None,
        "unit": None,
        "rates": ["DPC"],
    },
    "dpc_next_peak_start": {
        "data_source": "calendar_peak_handler.next_peak.start_date",
        "device_class": "timestamp",
        "icon": "mdi:clock-start",
        "rates": ["DPC"],
    },
    "dpc_next_peak_end": {
        "data_source": "calendar_peak_handler.next_peak.end_date",
        "device_class": "timestamp",
        "icon": "mdi:clock-end",
        "rates": ["DPC"],
    },
    "dpc_next_pre_heat_start": {
        "data_source": "calendar_peak_handler.next_peak.preheat.start_date",
        "device_class": "timestamp",
        "icon": "mdi:clock-start",
        "rates": ["DPC"],
        "diagnostic": True,
        "disabled_by_default": True,
    },
    "dpc_critical_hours_count": {
        "data_source": "contract.critical_called_hours",
        "icon": "mdi:clock-alert-outline",
        "rates": ["DPC"],
        "attributes": {
            "max": "contract.max_critical_called_hours",
        },
        "diagnostic": True,
    },
    "dpc_winter_days_count": {
        "data_source": "contract.winter_total_days_last_update",
        "icon": "mdi:calendar-range-outline",
        "rates": ["DPC"],
        "attributes": {
            "max": "contract.winter_total_days",
        },
        "diagnostic": True,
        "disabled_by_default": True,
    },
    # Winter Credits (DCPC) sensors - peak sensors sourced from calendar
    "wc_state": {
        "data_source": "calendar_peak_handler.current_state",
        "device_class": None,
        "icon": None,
        "unit": None,
        "rates": ["DCPC"],
        "diagnostic": True,
    },
    "wc_cumulated_credit": {
        "data_source": "contract.peak_handler.cumulated_credit",
        "device_class": "monetary",
        "state_class": "total",
        "icon": "mdi:currency-usd",
        "unit": "CAD",
        "rates": ["DCPC"],
    },
    "wc_projected_cumulated_credit": {
        "data_source": "contract.peak_handler.projected_cumulated_credit",
        "device_class": "monetary",
        "state_class": "total",
        "icon": "mdi:currency-usd",
        "unit": "CAD",
        "rates": ["DCPC"],
    },
    "wc_next_anchor_start": {
        "data_source": "calendar_peak_handler.next_peak.anchor.start_date",
        "device_class": "timestamp",
        "icon": "mdi:clock-start",
        "rates": ["DCPC"],
        "diagnostic": True,
        "attributes": {
            "critical": "calendar_peak_handler.next_peak.is_critical",
        },
    },
    "wc_next_anchor_end": {
        "data_source": "calendar_peak_handler.next_peak.anchor.end_date",
        "device_class": "timestamp",
        "icon": "mdi:clock-end",
        "rates": ["DCPC"],
        "diagnostic": True,
        "attributes": {
            "critical": "calendar_peak_handler.next_peak.is_critical",
        },
    },
    "wc_next_peak_start": {
        "data_source": "calendar_peak_handler.next_peak.start_date",
        "device_class": "timestamp",
        "icon": "mdi:clock-start",
        "rates": ["DCPC"],
        "diagnostic": True,
        "attributes": {
            "critical": "calendar_peak_handler.next_peak.is_critical",
        },
    },
    "wc_next_peak_end": {
        "data_source": "calendar_peak_handler.next_peak.end_date",
        "device_class": "timestamp",
        "icon": "mdi:clock-end",
        "rates": ["DCPC"],
        "diagnostic": True,
        "attributes": {
            "critical": "calendar_peak_handler.next_peak.is_critical",
        },
    },
    "wc_next_critical_peak_start": {
        "data_source": "calendar_peak_handler.next_critical_peak.start_date",
        "device_class": "timestamp",
        "icon": "mdi:clock-start",
        "rates": ["DCPC"],
    },
    "wc_next_critical_peak_end": {
        "data_source": "calendar_peak_handler.next_critical_peak.end_date",
        "device_class": "timestamp",
        "icon": "mdi:clock-end",
        "rates": ["DCPC"],
    },
    "wc_next_pre_heat_start": {
        "data_source": "calendar_peak_handler.next_peak.preheat.start_date",
        "device_class": "timestamp",
        "icon": "mdi:clock-start",
        "rates": ["DCPC"],
        "diagnostic": True,
        "attributes": {
            "critical": "calendar_peak_handler.next_peak.is_critical",
        },
    },
    # Yesterday's winter credit performance
    "wc_yesterday_morning_peak_credit": {
        "data_source": "contract.peak_handler.yesterday_morning_peak.credit",
        "device_class": "monetary",
        "state_class": "total",
        "icon": "mdi:currency-usd",
        "unit": "CAD",
        "rates": ["DCPC"],
    },
    "wc_yesterday_morning_peak_actual_consumption": {
        "data_source": "contract.peak_handler.yesterday_morning_peak.actual_consumption",
        "device_class": "energy",
        "icon": "mdi:home-lightning-bolt",
        "unit": "kWh",
        "rates": ["DCPC"],
    },
    "wc_yesterday_morning_peak_ref_consumption": {
        "data_source": "contract.peak_handler.yesterday_morning_peak.ref_consumption",
        "device_class": "energy",
        "icon": "mdi:home-lightning-bolt",
        "unit": "kWh",
        "rates": ["DCPC"],
    },
    "wc_yesterday_morning_peak_saved_consumption": {
        "data_source": "contract.peak_handler.yesterday_morning_peak.saved_consumption",
        "device_class": "energy",
        "icon": "mdi:home-lightning-bolt",
        "unit": "kWh",
        "rates": ["DCPC"],
    },
    "wc_yesterday_evening_peak_credit": {
        "data_source": "contract.peak_handler.yesterday_evening_peak.credit",
        "device_class": "monetary",
        "state_class": "total",
        "icon": "mdi:currency-usd",
        "unit": "CAD",
        "rates": ["DCPC"],
    },
    "wc_yesterday_evening_peak_actual_consumption": {
        "data_source": "contract.peak_handler.yesterday_evening_peak.actual_consumption",
        "device_class": "energy",
        "icon": "mdi:home-lightning-bolt",
        "unit": "kWh",
        "rates": ["DCPC"],
    },
    "wc_yesterday_evening_peak_ref_consumption": {
        "data_source": "contract.peak_handler.yesterday_evening_peak.ref_consumption",
        "device_class": "energy",
        "icon": "mdi:home-lightning-bolt",
        "unit": "kWh",
        "rates": ["DCPC"],
    },
    "wc_yesterday_evening_peak_saved_consumption": {
        "data_source": "contract.peak_handler.yesterday_evening_peak.saved_consumption",
        "device_class": "energy",
        "icon": "mdi:home-lightning-bolt",
        "unit": "kWh",
        "rates": ["DCPC"],
    },
}

BINARY_SENSORS: Final = {
    # Diagnostic sensors
    "portal_status": {
        "data_source": "portal_available",
        "icon": "mdi:web-check",
        "rates": ["ALL"],
        "diagnostic": True,
        "disabled_by_default": True,
    },
    # Contract binary sensors
    "current_period_epp_enabled": {
        "data_source": "contract.cp_epp_enabled",
        "icon": "mdi:code-equal",
        "rates": ["ALL"],
        "diagnostic": True,
        "disabled_by_default": True,
    },
    # Winter Credits binary sensors - sourced from calendar
    "wc_critical": {
        "data_source": "calendar_peak_handler.next_peak.is_critical",
        "icon": "mdi:flash-alert",
        "rates": ["DCPC"],
        "diagnostic": True,
    },
    "wc_critical_peak_in_progress": {
        "data_source": "calendar_peak_handler.current_peak_is_critical",
        "icon": "mdi:flash-alert",
        "rates": ["DCPC"],
        "diagnostic": True,
    },
    "wc_pre_heat": {
        "data_source": "calendar_peak_handler.preheat_in_progress",
        "icon": "mdi:flash-alert",
        "rates": ["DCPC"],
        "diagnostic": True,
        "disabled_by_default": True,
    },
    "wc_next_anchor_critical": {
        "data_source": "calendar_peak_handler.next_anchor.is_critical",
        "icon": "mdi:flash-alert",
        "rates": ["DCPC"],
        "diagnostic": True,
    },
    "wc_next_peak_critical": {
        "data_source": "calendar_peak_handler.next_peak.is_critical",
        "icon": "mdi:flash-alert",
        "rates": ["DCPC"],
        "diagnostic": True,
    },
    "wc_upcoming_critical_peak": {
        "data_source": "calendar_peak_handler.is_any_critical_peak_coming",
        "icon": "mdi:flash-alert",
        "rates": ["DCPC"],
        "diagnostic": True,
    },
    "wc_critical_morning_peak_today": {
        "data_source": "calendar_peak_handler.today_morning_peak.is_critical",
        "icon": "mdi:message-flash",
        "rates": ["DCPC"],
        "diagnostic": True,
        "disabled_by_default": True,
    },
    "wc_critical_evening_peak_today": {
        "data_source": "calendar_peak_handler.today_evening_peak.is_critical",
        "icon": "mdi:message-flash",
        "rates": ["DCPC"],
        "diagnostic": True,
        "disabled_by_default": True,
    },
    "wc_critical_morning_peak_tomorrow": {
        "data_source": "calendar_peak_handler.tomorrow_morning_peak.is_critical",
        "icon": "mdi:message-flash",
        "rates": ["DCPC"],
        "diagnostic": True,
        "disabled_by_default": True,
    },
    "wc_critical_evening_peak_tomorrow": {
        "data_source": "calendar_peak_handler.tomorrow_evening_peak.is_critical",
        "icon": "mdi:message-flash",
        "rates": ["DCPC"],
        "diagnostic": True,
        "disabled_by_default": True,
    },
    # DPC binary sensors - sourced from calendar
    "dpc_pre_heat": {
        "data_source": "calendar_peak_handler.preheat_in_progress",
        "icon": "mdi:flash-alert",
        "rates": ["DPC"],
        "diagnostic": True,
        "disabled_by_default": True,
    },
    "dpc_peak_in_progress": {
        "data_source": "calendar_peak_handler.peak_in_progress",
        "icon": "mdi:flash-alert",
        "rates": ["DPC"],
        "diagnostic": True,
    },
    "dpc_critical_morning_peak_today": {
        "data_source": "calendar_peak_handler.today_morning_peak.is_critical",
        "icon": "mdi:message-flash",
        "rates": ["DPC"],
        "diagnostic": True,
        "disabled_by_default": True,
    },
    "dpc_critical_evening_peak_today": {
        "data_source": "calendar_peak_handler.today_evening_peak.is_critical",
        "icon": "mdi:message-flash",
        "rates": ["DPC"],
        "diagnostic": True,
        "disabled_by_default": True,
    },
    "dpc_critical_morning_peak_tomorrow": {
        "data_source": "calendar_peak_handler.tomorrow_morning_peak.is_critical",
        "icon": "mdi:message-flash",
        "rates": ["DPC"],
        "diagnostic": True,
        "disabled_by_default": True,
    },
    "dpc_critical_evening_peak_tomorrow": {
        "data_source": "calendar_peak_handler.tomorrow_evening_peak.is_critical",
        "icon": "mdi:message-flash",
        "rates": ["DPC"],
        "diagnostic": True,
        "disabled_by_default": True,
    },
}
