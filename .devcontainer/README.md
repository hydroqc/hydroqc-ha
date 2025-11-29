# Hydro-Québec Home Assistant Integration - Development Container

This project includes a fully configured development container with all required tools.

## Quick Start

### Prerequisites

- [Docker](https://www.docker.com/products/docker-desktop)
- [Visual Studio Code](https://code.visualstudio.com/)
- [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)

### Getting Started

1. **Open in Dev Container**
   - Open VS Code
   - Press `F1` and select "Dev Containers: Reopen in Container"
   - Wait for the container to build and start (first time takes 2-3 minutes)

2. **Start Development**
   ```bash
   # The container automatically sets up everything
   # Just run:
   just start    # Start Home Assistant
   just dev      # Run full dev workflow
   ```

## What's Included

### Tools & Utilities

- **Python 3.13** - Latest Python with uv package manager
- **uv** - Fast Python package installer and resolver
- **just** - Command runner for development tasks
- **ruff** - Lightning-fast Python linter and formatter
- **mypy** - Static type checker
- **pytest** - Testing framework
- **Docker-in-Docker** - Run Home Assistant containers
- **fish shell** - User-friendly shell (default)
- **GitHub CLI** - Manage pull requests and issues

### VS Code Extensions

- Python + Pylance (language support)
- Ruff (linting and formatting)
- Mypy Type Checker
- Docker support
- YAML/TOML support
- GitHub Copilot (if you have it)

### Pre-configured Settings

- **Auto-format on save** using ruff
- **Auto-organize imports** on save
- **Strict type checking** with mypy
- **Integrated terminal** uses fish shell
- **Port forwarding** for Home Assistant (8123)

## Development Workflow

### Code Quality

```bash
# Check linting and formatting
just check

# Auto-fix issues and format code
just fix

# Run type checking
just typecheck

# Run all quality checks
just qa
```

### Testing

```bash
# Run pytest tests
just test

# Run tests with coverage
just test-cov

# Full workflow: sync, qa, validate, test
just dev
```

### Home Assistant Testing

```bash
# Start Home Assistant container
just start

# View logs
just logs       # All logs
just ilogs      # Integration logs only

# Restart after code changes
just restart

# Stop Home Assistant
just stop
```

### Useful Commands

```bash
# Sync dependencies
just sync

# Validate JSON files
just validate

# Open Home Assistant in browser
just open

# View all available commands
just --list
```

## Container Features

### Automatic Setup

On first launch, the container automatically:
1. Installs uv and just
2. Syncs all Python dependencies
3. Configures fish shell
4. Sets up git configuration
5. Creates Home Assistant config directory

### Port Forwarding

- **8123** - Home Assistant web interface
  - Access at http://localhost:8123
  - Automatically forwarded from container

### Docker-in-Docker

The container has access to Docker on your host machine, allowing you to:
- Run Home Assistant in Docker
- Build Docker images
- Use docker-compose

### Persistent Storage

The following are mounted from your local machine:
- Project files (live sync)
- Docker socket (for Docker-in-Docker)
- Git configuration

## Customization

### Add VS Code Extensions

Edit `.devcontainer/devcontainer.json`:
```json
"customizations": {
  "vscode": {
    "extensions": [
      "your.extension-id"
    ]
  }
}
```

### Change Shell

The default shell is fish, but you can change it:
```json
"terminal.integrated.defaultProfile.linux": "bash"
```

### Install Additional Tools

Edit `.devcontainer/post-create.sh` to add setup commands.

## Troubleshooting

### Container won't start

1. Ensure Docker is running
2. Check Docker has enough resources (4GB+ RAM recommended)
3. Try "Dev Containers: Rebuild Container"

### Python packages not found

```bash
# Re-sync dependencies
just sync

# Or manually
uv sync
```

### Home Assistant not accessible

1. Check container is running: `docker ps`
2. Check port is forwarded: VS Code should show "Port 8123"
3. Try accessing directly: http://localhost:8123

### Permission issues

The container runs as `vscode` user with appropriate permissions.
If you encounter issues:
```bash
# Check file ownership
ls -la

# Reset if needed (from host)
sudo chown -R $USER:$USER .
```

## Tips & Best Practices

1. **Use just for everything** - All common tasks have just recipes
2. **Run `just qa` before committing** - Catches issues early
3. **Keep dependencies updated** - Run `uv sync` periodically
4. **Test in container** - Ensures consistent environment
5. **Use fish shell features** - Autocomplete, syntax highlighting, etc.

## GitHub Codespaces

This devcontainer also works with GitHub Codespaces:

1. Fork the repository
2. Click "Code" → "Create codespace on main"
3. Wait for automatic setup
4. Start coding!

All the same tools and workflows apply.
