#!/bin/bash
set -e

echo "🚀 Setting up Hydro-Québec HA development environment..."
echo ""

# Install uv (fast Python package manager)
echo "📦 Installing uv..."
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

# Install just (command runner)
echo "⚡ Installing just..."
curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to ~/.local/bin

# Add tools to PATH permanently
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
echo 'fish_add_path $HOME/.local/bin' >> ~/.config/fish/config.fish 2>/dev/null || true

# Configure fish shell
mkdir -p ~/.config/fish
if [ ! -f ~/.config/fish/config.fish ]; then
    echo "# Fish shell configuration" > ~/.config/fish/config.fish
fi

# Set fish as default shell for vscode user
echo "🐚 Configuring fish shell..."
if ! grep -q "fish" ~/.bashrc; then
    echo 'if command -v fish &> /dev/null && [ -z "$FISH_VERSION" ]; then exec fish; fi' >> ~/.bashrc
fi

# Sync Python dependencies
echo "🔄 Syncing Python dependencies..."
~/.local/bin/uv sync

# Install pre-commit hooks (if we add them later)
if [ -f .pre-commit-config.yaml ]; then
    echo "🪝 Installing pre-commit hooks..."
    ~/.local/bin/uv run pre-commit install
fi

# Create initial config directory for Home Assistant testing
echo "📁 Creating Home Assistant config directory..."
mkdir -p config

# Set up git configuration helpers
echo "📝 Configuring git..."
git config --global --add safe.directory /workspaces/hydroqc-ha

echo ""
echo "✅ Development environment setup complete!"
echo ""
echo "Available commands:"
echo "  just start      - Start Home Assistant"
echo "  just dev        - Full dev workflow (sync, qa, validate, test)"
echo "  just check      - Run linting and format check"
echo "  just fix        - Auto-fix linting issues"
echo "  just test       - Run tests"
echo ""
echo "🎉 Happy coding!"
