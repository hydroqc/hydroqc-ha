# Contributing to Hydro-Québec Home Assistant Integration

Thank you for considering contributing! This document provides guidelines and instructions for contributing.

## Development Setup

### Prerequisites
- Python 3.13+
- [uv](https://github.com/astral-sh/uv) - Fast Python package manager
- Docker and Docker Compose (for testing)
- [just](https://github.com/casey/just) - Command runner (optional but recommended)

### Getting Started with Dev Container (Recommended)

The easiest way to get started is using the VS Code Dev Container:

1. **Prerequisites**
   - Install [VS Code](https://code.visualstudio.com/)
   - Install [Docker](https://www.docker.com/)
   - Install [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)

2. **Setup**
   - Open this repository in VS Code
   - Press `F1` → "Dev Containers: Reopen in Container"
   - Wait for setup to complete (2-3 minutes first time)
   - Run `just start` to launch Home Assistant

The dev container includes all required tools: Python 3.13, uv, ruff, mypy, pytest, docker-in-docker, and fish shell.

### Manual Setup

If you prefer not to use the dev container:

1. **Fork and clone the repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/hydroqc-ha.git
   cd hydroqc-ha
   ```

2. **Install dependencies**
   ```bash
   uv sync
   ```

3. **Start Home Assistant for testing**
   ```bash
   just start
   # or
   docker compose up -d
   ```

## Development Workflow

### Code Quality Checks

We use several tools to maintain code quality:

```bash
# Check linting and formatting
just check

# Auto-fix linting issues and format code
just fix

# Run type checking
just typecheck

# Run all quality checks
just qa
```

### Testing

The project includes a comprehensive test suite covering unit and integration tests.

#### Quick Test Commands

```bash
# Run all tests
uv run pytest

# Run with coverage
just test-cov

# Run complete test suite (lint + format + type check + tests)
just ci
```

#### Common Test Commands

```bash
# Unit tests only
uv run pytest tests/unit/

# Integration tests only
uv run pytest tests/integration/

# Specific test file
uv run pytest tests/unit/test_coordinator.py

# Verbose output
uv run pytest -v

# Show print statements
uv run pytest -s

# Full development workflow (sync, qa, validate, test)
just dev
```

#### Code Quality

```bash
# Linting
uv run ruff check custom_components/

# Auto-fix linting issues
uv run ruff check --fix custom_components/

# Code formatting
uv run ruff format custom_components/

# Type checking (strict mode)
uv run mypy custom_components/hydroqc/
```

See [tests/README.md](tests/README.md) for detailed testing documentation.

### Manual Testing

1. Start Home Assistant: `just start`
2. Open http://localhost:8123
3. Add the integration via Settings → Devices & Services → Add Integration
4. View logs: `just ilogs`

## Code Standards

### Style Guide

- **Line length**: 100 characters max
- **Formatting**: Handled by `ruff format`
- **Linting**: Enforced by `ruff check`
- **Type hints**: Required for all functions (checked by mypy)
- **Docstrings**: Required for all public functions and classes

### Python Version

- Target: Python 3.13+
- Use modern typing features (PEP 604, 613, etc.)

### Import Organization

Imports are automatically organized by ruff in this order:
1. Standard library
2. Third-party packages
3. Home Assistant imports
4. Local imports

## Commit Guidelines

### Commit Message Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Test additions or changes
- `chore`: Build process or auxiliary tool changes

**Examples:**
```
feat(sensor): add peak power demand sensor

Add new sensor to track peak power demand during billing period.
Closes #42

fix(config_flow): handle missing contract data gracefully

Prevent crash when Hydro-Québec API returns incomplete contract info.
Fixes #55
```

## Pull Request Process

1. **Create a feature branch**
   ```bash
   git checkout -b feat/your-feature-name
   ```

2. **Make your changes**
   - Write code following the style guide
   - Add/update tests as needed
   - Update documentation if required

3. **Run quality checks**
   ```bash
   just qa
   ```

4. **Commit your changes**
   ```bash
   git add .
   git commit -m "feat(scope): description"
   ```

5. **Push and create PR**
   ```bash
   git push origin feat/your-feature-name
   ```

6. **PR Requirements**
   - All CI checks must pass
   - Code review approval required
   - Update CHANGELOG.md if applicable
   - Add tests for new features

## Testing Guidelines

### Unit Tests

- Place tests in `tests/` directory
- Use pytest fixtures for reusable test components
- Mock external API calls (use `aioresponses`)
- Test both success and error cases

### Integration Tests

- Mark with `@pytest.mark.integration`
- Test against real Home Assistant container
- Verify sensor creation and data updates

### Test Coverage

- Aim for >80% code coverage
- All new features must include tests
- Coverage reports generated with `just test-cov`

## CI/CD Pipeline

All PRs automatically run:
1. **Lint & Format Check** - ruff linting and formatting
2. **Type Check** - mypy type checking
3. **Validation** - JSON files and structure
4. **Tests** - pytest against HA stable, beta, and specific versions
5. **Coverage** - Code coverage report
6. **HACS Validation** - HACS compatibility check
7. **Hassfest** - Home Assistant integration validation

## Rate-Specific Features

When adding or modifying rate-specific code:

### Supported Rates (Residential Only)
- **D**: Standard residential rate
- **D+CPC**: Rate D with Winter Credits
- **DT**: Dual tariff rate
- **DPC**: Flex-D dynamic pricing

**Note**: Commercial/industrial rates (M, M-GDP, etc.) are no longer supported in the integration. Focus is on residential Home Assistant users.

### Adding New Sensors

1. Add definition to `const.py::SENSORS` or `BINARY_SENSORS`
2. Specify `data_source` path (e.g., `"contract.balance"`)
3. Set `rates` list (e.g., `["ALL"]` or `["DPC", "DCPC"]`)
4. Add translations to `strings.json` and translation files
5. Test with appropriate rate configuration

### Data Source Paths

Use dot notation to access nested attributes:
- `"contract.current_period.total_consumption"`
- `"account.balance"`
- `"contract.peak_handler.cumulated_credit"`

## Documentation

### Update When Adding Features

- `README.md` - User-facing documentation
- `info.md` - HACS info page
- `CHANGELOG.md` - Version history
- Docstrings - In-code documentation
- Translation files - UI strings

### Documentation Style

- Clear and concise language
- Include examples where helpful
- Keep bilingual support (English/French)

## Questions?

- Open a [Discussion](https://github.com/hydroqc/hydroqc-ha/discussions)
- Report bugs via [Issues](https://github.com/hydroqc/hydroqc-ha/issues)
- Check existing documentation

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.
