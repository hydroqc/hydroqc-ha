# Hydro-Québec Home Assistant Integration - AI Coding Agent Guide

## Project Overview

This is a **Home Assistant custom component** for monitoring Hydro-Québec electricity accounts. It provides real-time consumption data, billing info, peak period alerts, winter credits tracking, and hourly consumption history import. The integration supports two connection modes:

- **Portal Mode** (`AUTH_MODE_PORTAL`): Full authentication with Hydro-Québec account - provides complete billing, consumption, winter credit data, and hourly consumption history
- **OpenData Mode** (`AUTH_MODE_OPENDATA`): No credentials required - fetches publicly available peak event data from HQ's open data API

**Tech Stack**: Python 3.13, Home Assistant 2024.1+, async/await, hydroqc API wrapper library, **uv** package manager

## Architecture

### Core Components

1. **`coordinator.py`** - `HydroQcDataCoordinator`: Central data fetcher using HA's `DataUpdateCoordinator`
   - Manages both Portal mode (`WebUser`/`Customer`/`Account`/`Contract` hierarchy) and OpenData mode (`PublicClient`) 
   - Updates every 60 seconds (configurable via `CONF_UPDATE_INTERVAL`)
   - Uses dot-notation paths (`get_sensor_value()`) to extract nested data: e.g., `"contract.cp_current_bill"` → `coordinator.data["contract"].cp_current_bill`
   - `is_sensor_seasonal()`: Portal mode sensors with `peak_handler` are seasonal (Dec 1 - Mar 31), OpenData sensors are always available
   - **Task management**: Separate `_csv_import_task` and `_regular_sync_task` per coordinator instance (per contract)
   - `is_consumption_history_syncing`: Only checks `_csv_import_task` status (not regular sync)
   - **Logging prefixes**: Portal mode logs use `[Portal]` prefix, public API logs use `[OpenData]` prefix

2. **`config_flow.py`** - Multi-step config flow:
   - Step 1: Choose `AUTH_MODE_PORTAL` or `AUTH_MODE_OPENDATA`
   - Step 2a (Portal mode): Login → fetch customers → select account → select contract → import history (0-800 days) → create entry
   - Step 2b (OpenData mode): Select sector (Residentiel/Affaires) → select rate and option (with preheat field) → create entry
   - **History import** (Portal mode only): `NumberSelector` for 0-800 days of consumption history
     - 0-30 days: Regular sync only (efficient for recent data)
     - >30 days: CSV import triggered automatically on integration setup
   - **Preheat configuration**: Only shown for rates with peak events (DPC, DCPC in Portal mode; all peak rates in OpenData mode)
   - Uses `NumberSelector` for preheat duration input (0-240 minutes, default 120)

3. **`sensor.py` / `binary_sensor.py`** - Entity implementations
   - Auto-generated from `SENSORS` and `BINARY_SENSORS` dicts in `const.py`
   - Filtered by rate: sensors specify `rates` list (`["ALL"]`, `["DPC"]`, `["DCPC"]`, etc.)
   - Rate-specific: Use `coordinator.rate_with_option` (e.g., `"DCPC"` = D+CPC, `"DPC"` = Flex-D)

4. **`const.py`** - Single source of truth for sensor definitions
   - Each sensor: `data_source`, `device_class`, `state_class`, `icon`, `unit`, `rates`, optional `attributes`
   - Data sources use dot notation: `"contract.peak_handler.cumulated_credit"`, `"public_client.peak_handler.current_state"`

5. **`public_data_client.py`** - Public API peak data handler
   - **API endpoint**: `https://donnees.hydroquebec.com/api/explore/v2.1`
   - **Dataset**: `evenements-pointe` (production dataset for peak events)
   - **Query syntax**: Uses `refine` parameter (e.g., `refine=offre:"TPC-DPC"`), not `where` clauses
   - **Time window**: Fetches 7 days ahead (not 60)
   - `PeakEvent`: Parses API dates (handles both simple `"YYYY-MM-DD HH:MM"` and ISO formats)
   - **Critical timezone requirement**: All datetimes MUST be `America/Toronto` timezone-aware
   - API returns lowercase field names: `datedebut`, `datefin`, `plagehoraire`, `secteurclient`
   - Preheat duration: Configurable per integration (0-240 minutes, default 120)
   - **Logging prefix**: All logs use `[OpenData]` prefix for easy troubleshooting

### OpenData API Offer Code Mapping

**CRITICAL**: The OpenData API returns peak event data with specific "offre" codes. The mapping is:

| OpenData "offre" | Portal Rate | Portal Rate Option | Internal Rate Code | Common Names |
|------------------|-------------|--------------------|--------------------|------------------------------------------|
| TPC-DPC          | DPC         | None/Empty         | DPC                | Flex-D, DPC                              |
| CPC-D            | D           | CPC                | DCPC               | Winter Credits, Crédits hivernaux, D+CPC |

**Understanding OpenData API and Peak Generation:**

- **OpenData API ONLY announces CRITICAL peaks** - it does NOT publish the full schedule
- **The integration must generate the complete peak schedule** and mark which ones are critical based on API data

**For CPC-D (Winter Credits) - DCPC Rate:**
- **Base Schedule (every day during winter season Dec 1 - Mar 31)**:
  - Morning Peak: 6:00-10:00 (4 hours) - **changed from 9:00 for winter 2025**
  - Evening Peak: 16:00-20:00 (4 hours)
- **Anchor periods** (reference baseline before each peak):
  - Morning Anchor: 1:00-4:00 (5 hours before peak, 3 hours duration)
  - Evening Anchor: 12:00-14:00 (4 hours before peak, 2 hours duration)
- **Critical vs Non-Critical**:
  - When OpenData API returns a CPC-D event for a specific date/time → that peak is **critical** (`is_critical=True`)
  - The anchor before a critical peak is also **critical**
  - All other peaks in the winter schedule (no API announcement) → **non-critical** (`is_critical=False`)
  - All other anchors (before non-critical peaks) → **non-critical**
- **API announces critical peaks around noon the day before** - gives enough time to prepare
- **Schedule generation**: Generate peaks for **today and tomorrow only** (2 days ahead)
- **Outside winter season**: No schedule generation, binary sensors return `False` (not `Unknown`)

**For TPC-DPC (Flex-D) - DPC Rate:**
- OpenData API returns TPC-DPC events
- All announced peaks are critical by definition (`is_critical=True`)
- No regular schedule to generate - only API-announced events
- Preheat periods are derived from API events (configurable duration before peak start)
- Binary sensors check `is_critical` to show alert state


### Rate Plans & Sensors

- **D**: Standard residential → balance, consumption, billing period sensors (no peak events)
- **D+CPC (DCPC)**: D with Winter Credits → adds `wc_*` sensors (cumulated credits, yesterday's peak performance, critical peak alerts)
  - Fixed schedule: peaks at 6-10 AM and 4-8 PM every winter day
  - Critical peaks announced via CPC-D offer code from OpenData API
  - Non-critical peaks are all other scheduled peaks (not announced by API)
  - Anchors exist for both critical and non-critical peaks
- **DT**: Bi-energy → adds higher/lower price consumption, net savings vs Rate D (no peak events)
- **DPC**: Flex-D dynamic pricing → adds `dpc_*` sensors (peak states, pre-heat alerts, critical hours count)
  - Uses TPC-DPC offer code from OpenData API
  - All peaks are critical (no regular schedule, only API announcements)
  - Preheat periods configurable (0-240 minutes before peak)
- **M/M-GDP**: Commercial rates → standard consumption tracking

**Key Pattern**: Sensor availability is controlled by `rates` list in `const.py`. Winter credit sensors (`wc_*`) only appear for rate `"DCPC"`, FlexD sensors (`dpc_*`) only for rate `"DPC"`.
### Setup (use devcontainer for consistency)

**This project uses `uv` for all Python package management** - do NOT use pip, poetry, or other tools.

```bash
# Install dependencies with uv
uv sync

# Add a new dependency
uv add package-name

# Add a dev dependency
uv add --dev package-name
```

### Testing & Quality

**All commands run through `uv`** to ensure consistent environments:

```bash
just dev    # Full workflow: uv sync, qa checks, validate, test
just qa     # Linting (uv run ruff check), formatting, type checking

# Individual checks (all use 'uv run')
just check      # uv run ruff check
just fix        # uv run ruff check --fix && uv run ruff format
just typecheck  # uv run mypy --strict
just test       # uv run pytest

# Direct uv commands
uv run ruff check custom_components/
uv run mypy custom_components/hydroqc/
uv run pytest -v
```

### Logs & Debugging
```bash
just logs   # All HA logs (follow mode)
just ilogs  # Filter for hydroqc integration logs only
just status # Check container status

# After code changes
just restart  # Restart HA container to reload integration
```

### Key Files to Check First
- **README.md**: User-facing features, supported rates, installation
- **CONTRIBUTING.md**: Commit conventions, PR requirements, rate-specific feature guidelines

- **pyproject.toml**: Python 3.13, uv config, ruff rules (line-length 100, select E/W/F/I/UP/B/C4/SIM/RET/ARG/PTH/PL/RUF)
- **uv.lock**: Lock file for reproducible builds (commit this file)
- **justfile**: All dev commands (start, stop, restart, logs, qa, test)
- **custom_components/hydroqc/const.py**: Sensor definitions, rate mappings
- **pyproject.toml**: Python 3.13, ruff rules (line-length 100, select E/W/F/I/UP/B/C4/SIM/RET/ARG/PTH/PL/RUF)

## Code Conventions

### GitHub Issue Management

**CRITICAL**: When working with GitHub issues, pull requests, or repository operations:
- **ALWAYS ask user permission before creating, updating, or commenting on issues/PRs**
- **ALWAYS use MCP GitHub tools** (activate with `activate_*` tools), NOT `gh` CLI commands
- **Exception**: Read-only operations (listing, viewing) can be done without asking
- **Examples requiring permission**:
  - Creating new issues
  - Adding comments to existing issues
  - Updating issue status or labels
  - Creating or updating pull requests

**Available GitHub MCP Tools** (activate via `activate_*` functions):
- `activate_pull_request_management_tools`: For PR operations
- `activate_github_search_tools`: For searching issues/PRs
- `activate_repository_management_tools`: For repo/branch/PR creation
- `activate_pull_request_review_tools`: For adding review comments
- `activate_issue_and_commit_management_tools`: For issue operations

### Type Hints & Style
- **Strict mypy**: All functions need type hints (`-> None`, `-> bool`, etc.)
- **Imports**: Auto-organized by ruff (stdlib → third-party → HA → local)
- **Line length**: 100 chars max
- **Logging**: Use `_LOGGER.debug/info/warning/error` with context (avoid print statements)

### Home Assistant Patterns
- **Async first**: Use `async def` for I/O operations (API calls, coordinator updates)
- **Coordinator pattern**: Entities read from `self.coordinator.data`, don't fetch directly
- **Entity naming**: `{device_name}_{sensor_name}` → e.g., `home_balance`, `cottage_wc_cumulated_credit`
- **Device registry**: One device per contract (all sensors grouped under it)

### Sensor Availability & Attributes

**Sensors are always available** - they never become "unavailable" in Home Assistant, instead showing the last known value. This ensures historical data is preserved even during temporary outages.

**All sensors include these attributes:**
- `last_update`: ISO 8601 timestamp of last successful data fetch
- `data_source`: One of `"portal"` (authenticated), `"open_data"` (public API), or `"unknown"`

**Sensor-specific attributes** are defined in the `attributes` dict in `const.py` and extracted via dot notation paths.

### Adding New Sensors
1. Add entry to `SENSORS` or `BINARY_SENSORS` in `const.py`:
   ```python
   "new_sensor_key": {
       "name": "Human Readable Name",
       "data_source": "contract.some_attribute.nested_value",  # Dot notation path
       "device_class": "energy",  # Or None
       "state_class": "total",    # Optional
       "icon": "mdi:flash",
       "unit": "kWh",
       "rates": ["DPC", "DCPC"],  # Or ["ALL"]
       "attributes": {  # Optional extra attributes
           "max": "contract.max_value",
       },
   }
   ```
2. Add translations to `strings.json`, `translations/en.json`, `translations/fr.json`
3. Test with appropriate rate configuration (use peak-only mode or authenticated mode)

### Rate-Specific Code Patterns
```python
# Check rate in coordinator
if coordinator.rate == "DPC":
    # Flex-D specific logic
elif coordinator.rate_with_option == "DCPC":  # D+CPC
    # Winter credits specific logic

# Rate filtering in sensor creation (auto-handled by sensor.py)
if "ALL" in sensor_config["rates"] or coordinator.rate_with_option in sensor_config["rates"]:
    # Create sensor
```

## Testing Strategy

### Test Suite Requirements

**Use `freezegun` for timezone/DST testing**:
```python
from freezegun import freeze_time

@freeze_time("2025-03-09 01:30:00", tz_offset=-5)  # Before DST
def test_consumption_before_dst():
    # Test consumption sync behavior before spring DST transition
    pass

@freeze_time("2025-03-09 03:30:00", tz_offset=-4)  # After DST
def test_consumption_after_dst():
    # Test consumption sync behavior after spring DST transition
    pass

@freeze_time("2025-11-02 01:30:00", tz_offset=-4)  # Before fall DST
def test_consumption_fall_dst():
    # Test consumption sync during fall DST transition (repeated hour)
    pass
```

**Critical DST test cases**:
- Hourly consumption statistics during spring forward (2 AM → 3 AM skip)
- Hourly consumption statistics during fall back (2 AM hour repeated)
- Peak period calculations across DST boundaries
- Winter credit anchor/peak times during DST transitions
- Timezone-aware datetime handling in recorder statistics

**Test of new features**
We should aim for a 100% test coverage. When adding new features adding tests should be part of the process by default.

## Consumption History Import (Energy Dashboard Integration)

### User-Facing Feature

During Portal mode setup, users can choose how many days of consumption history to import (0-800 days). This provides immediate historical data in the Energy dashboard:

- **0-30 days**: Regular sync only - efficient for recent contracts or users who don't need history
- **31-800 days**: CSV import triggered - for users wanting complete historical data

**Implementation location**: `__init__.py` checks `entry.data.get("history_days", 0)` after integration setup and triggers appropriate sync method.

### Technical Implementation

**Pattern**: Use Home Assistant's native `recorder` Python API for importing external statistics.

### Statistics Metadata Requirements (HA 2025.11+)

**CRITICAL**: Home Assistant 2025.11.2+ requires `mean_type` field in statistics metadata:

```python
from homeassistant.components.recorder import get_instance, statistics
from homeassistant.components.recorder.models import StatisticMeanType

metadata = {
    "source": "hydroqc",
    "statistic_id": "hydroqc:home_total_hourly_consumption",
    "unit_of_measurement": "kWh",
    "has_mean": False,  # Deprecated but kept for backward compatibility
    "has_sum": True,
    "mean_type": StatisticMeanType.NONE,  # REQUIRED - use enum, not string
    "name": "Total Hourly Consumption",
    "unit_class": "energy",
}
```

**Important**:
- `mean_type` uses `StatisticMeanType` enum from `homeassistant.components.recorder.models`
- Values: `NONE` (for sum-only), `ARITHMETIC`, `CIRCULAR`
- NOT specifying `mean_type` is deprecated and will fail in HA 2026.11
- `has_mean` is deprecated (removed in HA 2026.4) but keep for backward compatibility

### Consumption Import Flow

```python
from homeassistant.components.recorder import statistics

# Fetch hourly data from hydroqc library
hourly_data = await contract.get_hourly_consumption(date)

# Build statistics in HA format
stats = []
for hour in hourly_data["results"]["listeDonneesConsoEnergieHoraire"]:
    stats.append({
        "start": datetime_obj,  # Timezone-aware datetime (America/Toronto)
        "state": consumption_kwh,  # kWh for this hour
        "sum": cumulative_sum,  # Running total since first import
    })

# Import using recorder API
await get_instance(hass).async_add_executor_job(
    statistics.async_add_external_statistics,
    hass,
    metadata,  # See metadata structure above
    stats,
)
## Integration Setup & Initialization

### Setup Flow (`__init__.py`)

1. **Coordinator creation**: One `HydroQcDataCoordinator` per config entry (per contract)
2. **Platform setup**: Forward to sensor, binary_sensor platforms
3. **Service registration**: Register integration services (once, on first entry)
4. **History import** (Portal mode only):
   ```python
   history_days = entry.data.get("history_days", 0)
   if history_days > 30:
       # CSV import for bulk historical data
       coordinator.async_sync_consumption_history(days_back=history_days)
   else:
       # Regular sync for recent data (0-30 days)
       hass.async_create_task(coordinator._async_regular_consumption_sync())
   ```

**Key points**:
- History import runs after HA setup completes (doesn't block startup)
- Tasks are per-coordinator (per contract)
- No WebSocket connection needed (direct Python API call)
- Runs within HA's event loop (more reliable)
- Automatic integration with HA's energy dashboard
- Handle rate-specific consumption types (total/reg/haut for DT/DPC rates)

## External Dependencies

- **Hydro-Quebec-API-Wrapper**: Available from PyPI (standard public package registry)
  ```toml
  [dependency-groups]
  dev = [
      "Hydro-Quebec-API-Wrapper==4.2.4",
      ...
  ]
  ```
  - Main classes: `WebUser`, `Customer`, `Account`, `Contract`, `PublicClient`
  - Contract types: `ContractDCPC`, `ContractDPC`, `ContractDT` (subclasses of `Contract`)
  - Install/update: `uv sync` or `uv add Hydro-Quebec-API-Wrapper@latest`
- **Home Assistant 2024.1.0+**: Uses `DataUpdateCoordinator`, `ConfigFlow`, `CoordinatorEntity`

**Important**: Always use `uv` for dependency management - it installs from PyPI automatically.

### Timestamp Handling in Statistics

**Home Assistant returns timestamps as Unix epoch seconds** (not milliseconds):

```python
# CORRECT - timestamps are in seconds
last_date = datetime.datetime.fromtimestamp(
    last_stat_time, tz=datetime.timezone.utc
).date()

# WRONG - do NOT divide by 1000 (that's for JavaScript milliseconds)
last_date = datetime.datetime.fromtimestamp(
    last_stat_time / 1000, tz=datetime.timezone.utc
).date()  # Results in dates around 1970!
```
   
### CSV Import vs Hourly Fetch

Two methods for importing consumption history:

1. **CSV Import** (`async_sync_consumption_history`): Bulk historical data (up to 731 days)
   - Used when no statistics found or significant gaps (>30 days)
   - Downloads CSV from HQ API, parses all hourly data
   - Handles DST transitions by skipping ambiguous times
   - Triggered automatically during setup if user requests >30 days
   - Runs in background task (`_csv_import_task`)
   
2. **Hourly Fetch** (`async_fetch_hourly_consumption`): Recent data (last few days)
   - Used for daily updates and filling small gaps (≤30 days)
   - Fetches JSON data day-by-day from HQ API
## Common Gotchas

- **Seasonal sensors**: Portal mode winter credit sensors only show in-season (Dec 1 - Mar 31). OpenData mode sensors are ALWAYS available (not seasonal).
- **Timezone handling**: ALL datetime comparisons MUST use `America/Toronto` timezone (not UTC). Peak event dates from API are timezone-aware.
  - PeakEvent dates: Always ensure timezone-aware when parsing (handle both ISO and simple formats)
  - Datetime comparisons: Use `datetime.datetime.now(zoneinfo.ZoneInfo("America/Toronto"))` 
  - Never mix timezone-naive and timezone-aware datetimes - causes `TypeError` in comparisons
- **Off-season handling**: 
  - OpenData binary sensors return `False` (not `None`/unknown) when no peak data available
  - `current_state` shows "Off Season (Dec 1 - Mar 31)" when no events
  - DCPC schedule generation only runs during winter season (Dec 1 - Mar 31)
- **is_critical property**: 
  - Correct behavior: All events from OpenData API are critical announcements (regardless of offer code)
  - Use `force_critical` parameter in PeakEvent to explicitly mark API events as critical
  - Generated schedule peaks (DCPC only) are non-critical unless matched with API event
- **Dot notation paths**: Must match actual object attributes from `hydroqc` library (inspect library source if unsure)
  - `get_sensor_value()` safely handles `None` in path traversal, returning `None` if any part is missing
- **Rate vs rate_option**: Rate is base (D/DT/DPC/M), rate_option is modifier (CPC for winter credits). Combined: `rate_with_option`
- **Session expiration**: `coordinator._webuser.session_expired` triggers re-login automatically
- **Public client**: Always fetches peak data from HQ public API for critical peak alerts (used in both Portal and OpenData modes)
- **Statistics timestamps**: Must use aware datetime objects (with timezone), preferably `America/Toronto` (EST)
- **Cumulative sum**: Statistics require running total from first import, not just hourly state
- **Timestamp format**: HA returns Unix epoch **seconds** not milliseconds - don't divide by 1000!
- **Database corruption**: Old statistics with dates before 2020 indicate corrupted data - add sanity checks
- **Task separation**: CSV import uses `_csv_import_task`, regular sync uses `_regular_sync_task` - never confuse them
- **History import threshold**: Only trigger CSV import for >30 days (regular sync covers ≤30 days efficiently)
- **Statistics naming**: Display names include contract name prefix (e.g., "Home Total Hourly Consumption")
  - Main classes: `WebUser`, `Customer`, `Account`, `Contract`, `PublicClient`
  - Contract types: `ContractDCPC`, `ContractDPC`, `ContractDT` (subclasses of `Contract`)
- **Home Assistant 2024.1.0+**: Uses `DataUpdateCoordinator`, `ConfigFlow`, `CoordinatorEntity`

## Processus de Release

### Schéma de Versionnage Beta

**Statut actuel**: Projet en phase beta  
**Format de version**: `v0.X.Y-beta.Z` (ex: `v0.1.3-beta.1`)

**Composantes**:
- **Majeure (0)**: Reste à 0 durant la beta
- **Mineure (X)**: Incrémentée pour les releases de fonctionnalités
- **Correctif (Y)**: Incrémentée pour les releases de corrections  
- **Beta (beta.Z)**: Itération beta (généralement `.1` pour chaque version)

**Exemples**:
- Corrections/améliorations types: `v0.1.2-beta.1` → `v0.1.3-beta.1`
- Nouvelles fonctionnalités/capteurs: `v0.1.3-beta.1` → `v0.2.0-beta.1`
- Changements incompatibles: `v0.2.0-beta.1` → `v0.3.0-beta.1`

**Sortie de la Beta**:
Quand prêt pour release stable, retirer le suffixe `-beta.1`:
- `v0.1.3-beta.1` → `v1.0.0` (première version stable)

### Fichiers Nécessitant une Mise à Jour de Version

1. **`custom_components/hydroqc/manifest.json`** - Champ `version` (ex: `"0.1.3-beta.1"`)
2. **`CHANGELOG.md`** - Déplacer les changements de `[Unreleased]` vers la nouvelle section de version

**Note**: La version dans `pyproject.toml` reste à `0.1.0` (non distribué comme package Python)

### Étapes de Release

**1. Mettre à jour CHANGELOG.md**

Déplacer les changements de la section `[Unreleased]` vers une nouvelle section avec suffixe beta:

```markdown
## [Non publié]

### Ajouté
### Modifié  
### Corrigé
### Retiré

---

## [0.1.3-beta.1] - 2025-12-02

### Corrigé
- Résolution de 65 erreurs de typage mypy strict pour améliorer la qualité du code (#11)
- Correction du placement des annotations type ignore pour compatibilité avec la librairie hydroqc

### Retiré
- Retrait de 10 tests ignorés qui n'allaient pas être implémentés
```

**Catégories de changements**:
- **Ajouté**: Nouvelles fonctionnalités, capteurs, support de tarifs
- **Modifié**: Modifications aux fonctionnalités existantes  
- **Corrigé**: Corrections de bugs, erreurs de typage, gestion d'erreurs
- **Retiré**: Fonctionnalités dépréciées, code inutilisé
- **Sécurité**: Corrections de vulnérabilités de sécurité

**2. Mettre à jour la version dans manifest.json**

Inclure le suffixe `-beta.1`:

```json
{
  "version": "0.1.3-beta.1"
}
```

**3. Créer une branche de release**

**IMPORTANT**: La branche `main` est protégée - vous ne pouvez pas pousser directement dessus. Toutes les modifications doivent passer par une Pull Request.

```bash
# Créer une nouvelle branche pour la release
git checkout -b release/v0.1.3-beta.1

# Commit du bump de version
git add custom_components/hydroqc/manifest.json CHANGELOG.md
git commit -m "chore(release): bump version to 0.1.3-beta.1"
git push origin release/v0.1.3-beta.1
```

**4. Fusionner vers main via Pull Request**

Créer une Pull Request depuis la branche `release/v0.1.3-beta.1` vers `main`, puis fusionner après validation des CI checks.

**5. Créer et pousser le tag git**

Format du tag inclut le préfixe `v` et le suffixe `-beta.1`:

```bash
git checkout main
git pull origin main
git tag -a v0.1.3-beta.1 -m "Release v0.1.3-beta.1"
git push origin v0.1.3-beta.1
```

**6. Automatisation GitHub Actions**

Le workflow de release (`.github/workflows/release.yml`) automatiquement:
- Extrait la version du tag (`v0.1.3-beta.1` → `0.1.3-beta.1`)
- Met à jour la version dans manifest.json (redondant si déjà fait)
- Crée l'archive `hydroqc.zip` pour la release
- Extrait le changelog pour cette version
- Crée la Release GitHub avec:
  - Notes de release depuis CHANGELOG.md
  - Notes de release auto-générées depuis les commits
  - Asset `hydroqc.zip` attaché
  - **Marquée comme pre-release** (auto-détecté depuis `-beta` dans la version)

### Caractéristiques des Releases Beta

GitHub marque automatiquement les releases comme "pre-release" quand la version contient:
- `alpha`
- `beta`  
- `rc` (release candidate)

**Indicateurs de pre-release**:
- ⚠️ Badge affiché sur la page de release
- Non affiché comme release "Latest" par défaut
- HACS traite comme version beta/test

### Release Manuelle (si nécessaire)

Si GitHub Actions échoue:

```bash
# Créer l'archive zip
cd custom_components/hydroqc
zip -r ../../hydroqc.zip .
cd ../..

# Créer la release manuellement sur GitHub
# Aller à: https://github.com/hydroqc/hydroqc-ha/releases/new
# - Tag: v0.1.3-beta.1
# - Titre: Release v0.1.3-beta.1
# - Corps: Copier depuis CHANGELOG.md
# - Cocher "This is a pre-release"
# - Téléverser: hydroqc.zip
```

### Liste de Vérification Post-Release

- ✅ Vérifier que la release est marquée "Pre-release" sur GitHub
- ✅ Vérifier que `hydroqc.zip` est attaché et téléchargeable
- ✅ Vérifier que HACS détecte la nouvelle version beta (peut prendre des heures)
- ✅ Tester l'installation depuis HACS avec la nouvelle version
- ✅ Surveiller les retours/problèmes des utilisateurs beta

### Décider de l'Incrément de Version

**Incrément correctif (0.1.X → 0.1.Y)**:
- Corrections de bugs uniquement
- Corrections d'erreurs de typage
- Améliorations des tests
- Mises à jour de documentation
- Aucune nouvelle fonctionnalité

**Incrément mineur (0.X.0 → 0.Y.0)**:
- Nouveaux capteurs ou fonctionnalités
- Support de nouveaux tarifs
- Améliorations significatives
- Changements rétrocompatibles

**Itération beta (beta.1 → beta.2)**:
- Même version avec corrections additionnelles
- Rarement utilisé (préférer nouvelle version correctif)
- Exemple: `v0.1.3-beta.1` → `v0.1.3-beta.2`

### Support Beta dans HACS

HACS supporte pleinement les releases beta:
- Les utilisateurs peuvent installer les versions beta depuis HACS
- Les versions beta sont affichées séparément dans la liste des versions
- Badge pre-release visible dans l'interface HACS
- Les mises à jour automatiques fonctionnent pour les versions beta

**Configuration** (`hacs.json`):
```json
{
  "name": "Hydro-Québec",
  "zip_release": true,
  "filename": "hydroqc.zip"
}
```

### Transition vers Stable

Quand prêt à sortir de beta (typiquement après validation de la saison hivernale):

1. **Retirer le suffixe beta** de la version:
   - `v0.1.3-beta.1` → `v1.0.0`
2. **Mettre à jour CHANGELOG.md**:
   - Ajouter section `[1.0.0]`
   - Marquer comme release stable
3. **Mettre à jour manifest.json**: `"version": "1.0.0"`
4. **Tag sans beta**: `git tag -a v1.0.0 -m "Release stable v1.0.0"`
5. **Release GitHub** automatiquement marquée comme Latest (pas pre-release)

### Processus de Hotfix (Beta)

Pour corrections urgentes à la version beta actuelle:

```bash
# Option 1: Nouvelle beta correctif
v0.1.3-beta.1 → v0.1.4-beta.1

# Option 2: Même version, nouvelle itération beta (rare)
v0.1.3-beta.1 → v0.1.3-beta.2
```

Préférer Option 1 (nouveau correctif) sauf si multiples itérations rapides nécessaires.

### Dépannage

**Release non marquée comme pre-release:**
- Vérifier que le tag contient `beta`, `alpha`, ou `rc`
- Vérifier que le workflow de release détecte correctement le flag prerelease
- Éditer manuellement la release et cocher "This is a pre-release"

**HACS affiche beta comme latest:**
- C'est normal - HACS affiche toutes les releases
- Les utilisateurs doivent explicitement choisir les versions beta
- Les releases stables remplaceront les beta lors de la publication

**Erreurs de format de version:**
- Format du tag: `vX.Y.Z-beta.N` (beta en minuscule, séparateur tiret)
- manifest.json: `X.Y.Z-beta.N` (pas de préfixe `v`)
- CHANGELOG.md: `[X.Y.Z-beta.N]` (crochets, pas de préfixe `v`)

---

## Commit & PR Guidelines

### Commit Message Format (Conventional Commits)

**ALWAYS use Conventional Commits format** when generating commit messages:

```
<type>(<scope>): <subject>

[optional body]

[optional footer]
```

**Types** (required):
- `feat`: New feature for the user
- `fix`: Bug fix
- `docs`: Documentation only changes
- `style`: Code style changes (formatting, missing semi-colons, etc.)
- `refactor`: Code refactoring (neither fixes a bug nor adds a feature)
- `test`: Adding or updating tests
- `chore`: Changes to build process, dependencies, or auxiliary tools
- `perf`: Performance improvements
- `ci`: CI/CD configuration changes

**Scope** (optional but recommended):
- `sensor`: Sensor-related changes
- `coordinator`: Coordinator logic
- `config_flow`: Configuration flow
- `api`: API client changes
- `tests`: Test infrastructure
- `docs`: Documentation files

**Subject** (required):
- Use imperative mood ("add" not "added" or "adds")
- Don't capitalize first letter
- No period at the end
- Keep under 72 characters

**Examples**:
```
feat(sensor): add peak demand tracking sensor
fix(coordinator): handle missing contract data gracefully
docs(readme): update installation instructions
test(coordinator): add DST transition test cases
chore(deps): update Hydro-Quebec-API-Wrapper to 4.2.3
refactor(config_flow): simplify rate selection logic
```

**Multi-line commits**:
```
feat(consumption): add hourly consumption history import

Users can now import 0-800 days of consumption history during setup.
CSV import is used for >30 days, regular sync for ≤30 days.

Closes #123
```

### PR Requirements

- All CI checks pass (lint, type, test, validate, hacs, hassfest)
- Update CHANGELOG.md for user-facing changes
- Add tests for new features
- Bilingual translations (en + fr)
- Update `.github/copilot-instructions.md` if introducing new patterns, workflows, or architectural changes

**Note for AI agents**: 
- When generating commit messages, ALWAYS follow Conventional Commits format
- When implementing features that introduce new conventions, patterns, or workflows not covered in these instructions, update this file to document them for future reference

## Test Suite

**Location**: `tests/` directory with comprehensive unit and integration tests.

### Test Structure
```
tests/
├── conftest.py              # Pytest fixtures (mock objects, sample data)
├── README.md                # Detailed testing documentation
├── unit/                    # Unit tests (isolated component testing)
│   ├── test_coordinator.py          # Coordinator logic tests
│   ├── test_sensor.py                # Sensor entity tests
│   └── test_consumption_history.py  # Consumption sync & DST tests
├── integration/             # Integration tests (component interaction)
│   ├── test_config_flow.py          # Configuration flow tests
│   └── test_services.py              # Service tests
└── fixtures/                # Test data
    ├── sample_csv.py                 # Sample CSV data
    └── sample_api_data.py            # Sample API responses
```

### Running Tests

**Quick commands**:
```bash
# Run all tests
just test

# Run with coverage
just test-cov

# Run complete test suite (lint + format + type check + tests)
just ci

# Specific test categories
uv run pytest tests/unit/           # Unit tests only
uv run pytest tests/integration/    # Integration tests only

# Specific test file or function
uv run pytest tests/unit/test_coordinator.py
uv run pytest tests/unit/test_coordinator.py::TestHydroQcDataCoordinator::test_coordinator_initialization -vv
```

### Test Dependencies

All test dependencies are in `pyproject.toml` under `[dependency-groups] dev`:
- `pytest>=8.3.0` - Testing framework
- `pytest-asyncio>=0.24.0` - Async test support
- `pytest-homeassistant-custom-component>=0.13.0` - HA mocking
- `pytest-cov>=6.0.0` - Coverage reporting
- `freezegun>=1.5.0` - Time mocking for DST tests

**Important**: The project uses `[dependency-groups]` (new uv format), not `[tool.uv.dev-dependencies]` (deprecated).

### Key Test Fixtures (in `conftest.py`)

- `mock_config_entry`: MockConfigEntry for testing
- `mock_webuser`: Mock WebUser with customers/accounts/contracts
- `mock_contract`: Mock Rate D contract
- `mock_contract_dpc`: Mock Flex-D contract with peak handler
- `mock_contract_dcpc`: Mock D+CPC contract with winter credits
- `sample_statistics`: Sample consumption statistics
- `sample_hourly_json`: Sample API response
- `mock_recorder_instance`: Mock HA recorder
- `mock_statistics_api`: Mock statistics API

### Test Coverage Focus

Tests cover critical bugs that were fixed:
1. **DST transitions**: Spring forward, fall back, repeated hour handling (`freezegun` for time mocking)
2. **Timezone comparisons**: All datetimes must be `America/Toronto` aware (fixes `TypeError: can't compare offset-naive and offset-aware datetimes`)
3. **French decimals**: CSV parsing with comma decimal separators
4. **Statistics metadata**: HA 2025.11+ requires `mean_type` field
5. **Timestamp handling**: HA returns Unix seconds, not milliseconds
6. **Corrupted data**: Sanity checks for dates before 2020

### CI/CD Integration

Tests run automatically in `.github/workflows/ci.yml`:
- Linting (ruff)
- Type checking (mypy strict)
- Tests against multiple HA versions (2024.1.0, stable, beta)
- Coverage reporting (codecov)
- HACS validation
- Hassfest validation

### System Requirements for Testing

If you encounter build errors with `lru-dict` or other compiled dependencies:
```bash
sudo apt-get update && sudo apt-get install -y gcc python3-dev
```

Then run:
```bash
uv sync
```

### Testing Best Practices

1. **Use existing fixtures** from `conftest.py` - don't recreate mock objects
2. **Follow AAA pattern**: Arrange, Act, Assert
3. **Mock external dependencies**: Use `@patch` decorator
4. **Test edge cases**: DST, missing data, errors, timezone issues
5. **Use freezegun for time-based tests**: `@freeze_time("2024-12-15 10:00:00")`
6. **Always make datetimes timezone-aware**: `datetime(..., tzinfo=ZoneInfo("America/Toronto"))`

**Note for AI agents**: When switching to devcontainer or new environment, this context is preserved. The most critical issues to watch for:
1. **Timezone-aware datetime comparisons**: Any comparison with peak event dates MUST use `datetime.now(EST_TIMEZONE)`, not `datetime.now()`
2. **Task separation**: CSV import (`_csv_import_task`) and regular sync (`_regular_sync_task`) are tracked separately per coordinator instance
