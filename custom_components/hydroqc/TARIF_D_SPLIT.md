# PR3 — Tarif D Low/High Price Split for Energy Dashboard

## Overview

Hydro-Québec Tarif D (and D+CPC / DCPC) charges two different rates for
electricity consumption:

- **Low price (bas prix / reg):** The first `40 kWh × billing_period_days`
  consumed during a billing period. For a typical 62-day billing period this
  is 2,480 kWh.
- **High price (haut prix / haut):** Any consumption beyond that threshold.

This PR adds two-color energy dashboard support for Tarif D / Tarif D with CPC (DCPC) rates,
mirroring the existing behavior of Tarif DT/DPC (bi-énergie) where the
Hydro-Québec API already provides separate reg/haut streams.

The 40 kWh/day threshold is defined by the constant
`TARIF_D_THRESHOLD_KWH_PER_DAY = 40` in `const.py`. If Hydro-Québec ever
changes this threshold, only that constant needs to be updated.

---

## How the split works

### Split logic

For each billing period:

1. The threshold is calculated: `40 kWh × billing_period_days`
2. Hourly consumption is processed chronologically from the start of the period
3. Each hour's consumption is assigned to:
   - **reg (low price):** `min(hour_kwh, remaining_threshold)`
   - **haut (high price):** `max(0, hour_kwh - remaining_threshold)`
4. The remaining threshold decreases as reg consumption accumulates
5. Once the threshold is exhausted, all subsequent consumption goes to haut
6. The allowance starts over (full `40 kWh × days` again) at the start of each
   new billing period

### Billing period boundaries

The split needs to know when each billing period starts and ends. Sources
used in order of preference:

1. **Recorder history of the configured billing duration sensor**
   (`sensor.hydro_quebec_maison_billing_period_duration`) — most accurate,
   covers the last 90 days (limited by `purge_keep_days`)
2. **The contract's current billing period** (start date and length) — used
   when there is no sensor history, and for the daily sync. Days that fall
   before the current period (for example yesterday, right after a new period
   began) are split against the previous period, never against a fresh one.
3. **60-day approximation** (`TARIF_D_HISTORY_PERIOD_DAYS = 60`) — used
   for data older than what the recorder has. Periods are estimated by
   working backwards from the oldest known period boundary. Since actual
   periods are typically 57-64 days, the approximation error is small.

The daily sync, the CSV history import and the re-split service all use the
same split implementation (`tarif_d_split.py`). They differ only in where the
period boundaries come from: the re-split reads the sensor history, the other two
use the contract's current period.

**Known limitation:** the oldest period covered by the re-split may only be
partly present in the recorder. Hours before the history starts are unknown, so
that first partial period is given a full allowance and its low-price share is
overstated. Every later period is exact (or as exact as its boundaries).

### Statistic IDs

The split writes to these statistic IDs (same as DT/DPC for consistency):

- `hydroqc:maison_reg_hourly_consumption` — Low Price Hourly Consumption
- `hydroqc:maison_haut_hourly_consumption` — High Price Hourly Consumption
- `hydroqc:maison_hourly_consumption` — Total Hourly Consumption (unchanged)

The `total` stream is **never modified** — it always remains as a rollback
safety net.

---

## New features

### 1. Energy dashboard split (Tarif D and Tarif D with CPC / DCPC only)

Dark blue = low price, light blue = high price in the HA energy dashboard.

### 2. Three new sensors (Tarif D and Tarif D with CPC / DCPC only)

| Entity ID | Description |
|-----------|-------------|
| `sensor.hydro_quebec_maison_tarif_d_low_price_threshold_kwh` | Total low-price allowance this billing period (40 × days) |
| `sensor.hydro_quebec_maison_tarif_d_low_price_remaining_kwh` | kWh remaining at low price this period |
| `sensor.hydro_quebec_maison_tarif_d_daily_low_price_budget_kwh` | Average daily low-price budget remaining |

### 3. Service: `hydroqc.resplit_tarif_d_history`

One-time service to re-split all existing total statistics into Low/High
Price streams. Run this once after installing the PR.

### 4. Options flow: billing duration entity picker

An optional `EntitySelector` in the options flow allows selecting the sensor
that tracks billing period duration. Used for accurate historical re-splitting.

---

## Post-install instructions

### Step 1 — Configure billing duration sensor

1. Go to **Settings → Devices & Services → Hydro-Québec → Configure**
2. In the **Billing period duration sensor** field select:
   `sensor.hydro_quebec_maison_billing_period_duration`
3. Click **Save**

> This only saves the sensor selection. It does NOT run the split.

### Step 2 — Run the historical re-split (one time only)

1. Go to **Developer Tools → Actions**
2. Search for `hydroqc.resplit_tarif_d_history`
3. Under **Target** select your Hydro-Québec device (e.g. `maison (DCPC)`)
4. Click **Perform Action**
5. The re-split runs in the background — check **Settings → System → Logs**:
   ```
   WARNING hydroqc: Tarif D historical re-split STARTING
   WARNING hydroqc: Tarif D historical re-split COMPLETE
   ```

**Rollback resplit:**
The `total` stream is never modified. If results look wrong:
1. Go to **Developer Tools → Statistics**
2. Delete `Maison Low Price Hourly Consumption`
3. Delete `Maison High Price Hourly Consumption`
4. Fix the issue and call `hydroqc.resplit_tarif_d_history` again

### Step 3 — Add Low/High Price streams to energy dashboard

1. Go to **Settings → Energy**
2. Under **Home Consumption** click **Add consumption**
3. Search for your contract name (e.g. `maison`) — you will see:
   - **Maison Low Price Hourly Consumption**
   - **Maison High Price Hourly Consumption**
   - `Maison Total Hourly Consumption` (existing)
4. Add both **Low Price** and **High Price**
5. Optionally remove **Total** if you only want the two-color view
6. Click **Save**

---

## Logging configuration

To see detailed logs from the integration, add to `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.hydroqc: debug
    custom_components.hydroqc.config_flow.base: debug
    custom_components.hydroqc.coordinator.base: debug
```

---

## Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `TARIF_D_THRESHOLD_KWH_PER_DAY` | 40 | kWh per day at low price. Update if HQ changes the threshold. |
| `TARIF_D_HISTORY_PERIOD_DAYS` | 60 | Approximation for billing period length when actual history is unavailable. |
| `CONF_BILLING_DURATION_ENTITY` | `billing_duration_entity` | Options key for the billing duration sensor. |

---

## Files changed

| File | Changes |
|------|---------|
| `const.py` | New constants and three new sensor definitions |
| `coordinator/sensor_data.py` | Handler for `computed.tarif_d_*` data sources |
| `coordinator/consumption_sync.py` | Pass billing duration entity to StatisticsManager; `async_resplit_tarif_d_history()` |
| `statistics_manager.py` | Split logic; historical resplit; billing period detection; Low/High Price display names |
| `consumption_history.py` | Live split for new CSV imports |
| `config_flow/options.py` | Optional billing duration EntitySelector |
| `__init__.py` | Register `hydroqc.resplit_tarif_d_history` service |
| `services.yaml` | Service definition |
| `strings.json` + translations | Labels and entity translations |
