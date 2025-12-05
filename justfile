# Home Assistant Test Environment for Hydro-Québec Integration
# https://github.com/casey/just

# Default recipe to display help
default:
    @just --list

# Start Home Assistant
start:
    #!/usr/bin/env fish
    echo ""
    echo "🏠 Starting Home Assistant..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    if not test -d .ha-test-config
        echo "ℹ️  Creating new config directory"
        mkdir -p .ha-test-config
    end
    docker compose up -d
    if test $status -eq 0
        echo "✅ Home Assistant started"
        echo "⏳ Waiting for Home Assistant to be ready (30-60 seconds)..."
        sleep 5
        echo ""
        echo "ℹ️  Home Assistant should be available at:"
        echo "   🌐 http://localhost:8123"
        echo ""
        echo "ℹ️  To add the Hydro-Québec integration:"
        echo "   Settings → Devices & Services → Add Integration → Hydro-Québec"
    else
        echo "❌ Failed to start Home Assistant"
        exit 1
    end

# Stop Home Assistant
stop:
    #!/usr/bin/env fish
    echo ""
    echo "🏠 Stopping Home Assistant..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    docker compose down
    if test $status -eq 0
        echo "✅ Home Assistant stopped"
    else
        echo "❌ Failed to stop Home Assistant"
        exit 1
    end

# Restart Home Assistant (after code changes)
restart:
    #!/usr/bin/env fish
    echo ""
    echo "🏠 Restarting Home Assistant..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    docker compose restart
    if test $status -eq 0
        echo "✅ Home Assistant restarted"
        echo "ℹ️  Changes to the integration should now be loaded"
    else
        echo "❌ Failed to restart Home Assistant"
        exit 1
    end

# Show all logs (Ctrl+C to exit)
logs:
    #!/usr/bin/env fish
    echo ""
    echo "🏠 Showing Home Assistant logs (Ctrl+C to exit)..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    docker compose logs -f

# Show integration logs only (Ctrl+C to exit)
ilogs:
    #!/usr/bin/env fish
    echo ""
    echo "🏠 Showing Hydro-Québec integration logs (Ctrl+C to exit)..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    docker compose logs -f | grep -i hydroqc

# Show container status
status:
    #!/usr/bin/env fish
    echo ""
    echo "🏠 Home Assistant Status"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    if docker compose ps | grep -q homeassistant
        echo "✅ Home Assistant is running"
        echo ""
        docker compose ps
        echo ""
        echo "ℹ️  Access at: http://localhost:8123"
    else
        echo "ℹ️  Home Assistant is not running"
        echo "ℹ️  Start it with: just start"
    end

# Delete all data and start fresh
reset:
    #!/usr/bin/env fish
    echo ""
    echo "🏠 Reset Home Assistant"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "❌ ⚠️  WARNING: This will delete ALL Home Assistant data!"
    echo ""
    read -P "Are you sure? Type 'yes' to continue: " confirm
    if test "$confirm" = "yes"
        echo "ℹ️  Stopping Home Assistant..."
        docker compose down
        echo "ℹ️  Removing configuration..."
        rm -rf .ha-test-config/
        echo "✅ Reset complete. Start fresh with: just start"
    else
        echo "ℹ️  Reset cancelled"
    end

# Pull latest Home Assistant image
update:
    #!/usr/bin/env fish
    echo ""
    echo "🏠 Updating Home Assistant..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    docker compose pull
    if test $status -eq 0
        echo "✅ Image updated. Restart to apply: just restart"
    else
        echo "❌ Failed to update image"
        exit 1
    end

# Open Home Assistant in browser
open:
    @echo "🌐 Opening http://localhost:8123 in browser..."
    @xdg-open http://localhost:8123 2>/dev/null || open http://localhost:8123 2>/dev/null || echo "Please open http://localhost:8123 manually"

# Run shell in Home Assistant container
shell:
    @echo "🐚 Opening shell in Home Assistant container..."
    @docker compose exec homeassistant /bin/bash

# Check code linting
check:
    #!/usr/bin/env fish
    echo ""
    echo "🔍 Linting..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    uv run ruff check custom_components/
    if test $status -eq 0
        echo "✅ Linting passed"
    else
        echo "❌ Linting failed"
        exit 1
    end

# Validate manifest.json
validate:
    #!/usr/bin/env fish
    echo ""
    echo "✓ Validating manifest.json"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    if test -f custom_components/hydroqc/manifest.json
        cat custom_components/hydroqc/manifest.json | python -m json.tool > /dev/null
        if test $status -eq 0
            echo "✅ manifest.json is valid JSON"
            echo ""
            cat custom_components/hydroqc/manifest.json | python -m json.tool
        else
            echo "❌ manifest.json has JSON errors"
            exit 1
        end
    else
        echo "❌ manifest.json not found"
        exit 1
    end

# Validate blueprints
validate-blueprints:
    #!/usr/bin/env fish
    python3 scripts/validate_blueprints.py
    if test $status -ne 0
        exit 1
    end

# Clean up docker resources
clean:
    #!/usr/bin/env fish
    echo ""
    echo "🧹 Cleaning Docker Resources"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    docker compose down -v
    echo "✅ Cleaned up containers and volumes"

# Full development cycle: restart, wait, and show logs
dev:
    @echo "🔄 Development mode: restart + logs"
    @just restart
    @sleep 3
    @just ilogs

# Sync dependencies with uv
sync:
    #!/usr/bin/env fish
    echo ""
    echo "📦 Syncing dependencies..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    if not command -v uv >/dev/null 2>&1
        echo "❌ Error: uv is not installed"
        echo "ℹ️  Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    end
    uv sync
    if test $status -eq 0
        echo "✅ Dependencies synced"
    else
        echo "❌ Failed to sync dependencies"
        exit 1
    end

# Check code formatting
format-check:
    #!/usr/bin/env fish
    echo ""
    echo "📝 Checking code formatting..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    uv run ruff format --check custom_components/
    if test $status -eq 0
        echo "✅ Formatting check passed"
    else
        echo "❌ Formatting check failed (run 'just fix')"
        exit 1
    end

# Auto-fix linting and formatting issues
fix:
    #!/usr/bin/env fish
    echo ""
    echo "🔧 Auto-fixing linting and formatting..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    uv run ruff check --fix custom_components/
    and uv run ruff format custom_components/
    if test $status -eq 0
        echo "✅ Code fixed"
    else
        echo "❌ Failed to fix code"
        exit 1
    end

# Run type checking
typecheck:
    #!/usr/bin/env fish
    echo ""
    echo "🔬 Running type checking..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    uv run mypy custom_components/hydroqc/
    if test $status -eq 0
        echo "✅ Type checking passed"
    else
        echo "❌ Type checking failed"
        exit 1
    end

# Run tests
test:
    #!/usr/bin/env fish
    echo ""
    echo "🧪 Running tests..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    uv run pytest
    if test $status -eq 0
        echo "✅ All tests passed"
    else
        echo "❌ Tests failed"
        exit 1
    end

# Run tests with coverage
test-cov:
    #!/usr/bin/env fish
    echo ""
    echo "🧪 Running tests with coverage..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    uv run pytest --cov=custom_components.hydroqc --cov-report=term --cov-report=html
    if test $status -eq 0
        echo "✅ All tests passed"
        echo ""
        echo "ℹ️  Coverage report: htmlcov/index.html"
    else
        echo "❌ Tests failed"
        exit 1
    end

# Run quality assurance checks (lint + format + typecheck)
qa:
    #!/usr/bin/env fish
    echo ""
    echo "🔍 Running QA checks..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    just check
    and just format-check
    and just typecheck
    if test $status -eq 0
        echo ""
        echo "✅ All QA checks passed"
    else
        echo ""
        echo "❌ QA checks failed"
        exit 1
    end

# Run all checks: sync + qa + validate + validate-blueprints + test
ci:
    #!/usr/bin/env fish
    echo ""
    echo "🧪 Hydro-Québec HA Test Suite"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    just sync
    and just qa
    and just validate
    and just validate-blueprints
    and just test-cov
    if test $status -eq 0
        echo ""
        echo "✅ All checks passed!"
    else
        echo ""
        echo "❌ Some checks failed"
        exit 1
    end
