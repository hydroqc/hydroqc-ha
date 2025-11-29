# Hydro-Québec Integration Tests

This directory contains the test suite for the Hydro-Québec Home Assistant custom component.

## Test Structure

```
tests/
├── conftest.py              # Pytest fixtures and test configuration
├── unit/                    # Unit tests (isolated component testing)
│   ├── test_coordinator.py # Tests for HydroQcDataCoordinator
│   ├── test_sensor.py       # Tests for sensor entities
│   └── test_consumption_history.py  # Tests for consumption sync
├── integration/             # Integration tests (component interaction)
│   ├── test_config_flow.py # Tests for configuration flow
│   └── test_services.py     # Tests for Home Assistant services
└── fixtures/                # Test data and sample responses
    ├── sample_csv.py        # Sample CSV data
    └── sample_api_data.py   # Sample API responses
```

## Running Tests

### Run All Tests

```bash
uv run pytest
```

### Run Specific Test Categories

```bash
# Unit tests only
uv run pytest tests/unit/

# Integration tests only
uv run pytest tests/integration/

# Specific test file
uv run pytest tests/unit/test_coordinator.py

# Specific test class
uv run pytest tests/unit/test_coordinator.py::TestHydroQcDataCoordinator

# Specific test method
uv run pytest tests/unit/test_coordinator.py::TestHydroQcDataCoordinator::test_coordinator_initialization
```

### Run Tests with Coverage

```bash
# Run tests with coverage report
uv run pytest --cov=custom_components.hydroqc --cov-report=html --cov-report=term

# View HTML coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### Run Tests with Verbose Output

```bash
# Verbose output (-v)
uv run pytest -v

# Very verbose output (-vv) - shows test parameters
uv run pytest -vv

# Show print statements and logging
uv run pytest -s
```

### Run Tests by Keyword

```bash
# Run tests matching keyword
uv run pytest -k "coordinator"

# Run tests NOT matching keyword
uv run pytest -k "not integration"
```

## Code Quality Checks

### Linting

```bash
# Check code style with ruff
uv run ruff check custom_components/

# Auto-fix linting issues
uv run ruff check --fix custom_components/

# Format code with ruff
uv run ruff format custom_components/
```

### Type Checking

```bash
# Run mypy type checker (strict mode)
uv run mypy custom_components/hydroqc/
```

### Run All Quality Checks

```bash
# Lint, format, and type check
uv run ruff check custom_components/ && \
uv run ruff format --check custom_components/ && \
uv run mypy custom_components/hydroqc/
```

## Test Fixtures

Common fixtures available in `conftest.py`:

- `mock_config_entry`: Mock Home Assistant config entry
- `mock_webuser`: Mock Hydro-Québec WebUser (authenticated API client)
- `mock_contract`: Mock Rate D contract
- `mock_contract_dpc`: Mock Flex-D (DPC) contract with peak handler
- `mock_contract_dcpc`: Mock D+CPC contract with winter credits
- `sample_statistics`: Sample consumption statistics data
- `sample_csv_data`: Sample CSV consumption data
- `sample_hourly_json`: Sample hourly consumption JSON response
- `mock_recorder_instance`: Mock Home Assistant recorder
- `mock_statistics_api`: Mock recorder statistics API
- `statistics_metadata`: Sample statistics metadata

## Test Coverage Goals

The test suite aims to cover:

1. **Coordinator Logic**
   - Authentication and session management
   - Data fetching and updates
   - Error handling and retry logic
   - Sensor value extraction (dot notation paths)
   - Seasonal sensor handling

2. **Consumption History Sync**
   - CSV import and parsing
   - Hourly consumption fetching
   - DST transition handling (spring forward, fall back)
   - French decimal format handling
   - Cumulative sum calculations
   - Statistics metadata (HA 2025.11+ compatibility)

3. **Sensor Entities**
   - Rate-specific sensor creation (D, DT, DPC, D+CPC)
   - State value extraction
   - Attribute handling (last_update, data_source)
   - Device info and unique IDs
   - Availability based on data presence

4. **Configuration Flow**
   - Portal mode authentication
   - OpenData mode setup
   - Account/contract selection
   - Duplicate entry prevention
   - Error handling

5. **Services**
   - `clear_consumption_history` service
   - `refresh_data` service
   - `fetch_hourly_consumption` service

## Writing New Tests

### Unit Test Example

```python
import pytest
from homeassistant.core import HomeAssistant
from unittest.mock import MagicMock, patch

@pytest.mark.asyncio
async def test_my_feature(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_webuser: MagicMock,
) -> None:
    """Test my feature."""
    # Arrange
    mock_config_entry.add_to_hass(hass)
    
    # Act
    with patch("custom_components.hydroqc.coordinator.WebUser", return_value=mock_webuser):
        coordinator = HydroQcDataCoordinator(hass, mock_config_entry)
        await coordinator.async_config_entry_first_refresh()
    
    # Assert
    assert coordinator.last_update_success
```

### Integration Test Example

```python
import pytest
from homeassistant.core import HomeAssistant

@pytest.mark.asyncio
async def test_my_service(hass: HomeAssistant, mock_config_entry: MockConfigEntry) -> None:
    """Test my service."""
    # Set up integration
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    
    # Call service
    await hass.services.async_call(
        "hydroqc",
        "my_service",
        {},
        blocking=True,
    )
    
    # Assert service executed correctly
    # ...
```

## Continuous Integration

Tests run automatically in CI on:
- Pull requests
- Pushes to main branch
- Manual workflow dispatch

CI runs:
1. Linting (ruff)
2. Type checking (mypy)
3. Unit tests
4. Integration tests
5. Coverage reporting

## Troubleshooting

### Import Errors

If you see import errors:
```bash
# Install dependencies with uv
uv sync
```

### Async Test Warnings

If you see warnings about asyncio loop:
```bash
# Make sure pytest-asyncio is installed
uv add --dev pytest-asyncio
```

### Fixture Not Found

Make sure your test file imports from the correct module and that fixtures are defined in `conftest.py`.

### Mock Not Working

Ensure you're patching the correct import path where the object is used, not where it's defined:
```python
# Correct: patch where WebUser is imported in coordinator
with patch("custom_components.hydroqc.coordinator.WebUser"):
    ...

# Wrong: patch where WebUser is defined
with patch("hydroqc.webuser.WebUser"):
    ...
```

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component)
- [Home Assistant testing documentation](https://developers.home-assistant.io/docs/development_testing)
- [freezegun for time mocking](https://github.com/spulec/freezegun)
