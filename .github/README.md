# Hydro-Québec Home Assistant Integration

Development repository for the hydroqc-ha custom component.

See [README.md](README.md) for full documentation.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/hydroqc/hydroqc-ha.git
cd hydroqc-ha

# Symlink to Home Assistant custom_components
ln -s $(pwd)/custom_components/hydroqc ~/.homeassistant/custom_components/hydroqc

# Restart Home Assistant
```

## Contributing

Contributions welcome! Please open an issue first to discuss proposed changes.

## Testing

Run Home Assistant with the integration and verify:
1. Config flow works for both auth modes
2. Sensors appear and update
3. Rate-specific sensors filtered correctly
4. No errors in logs

## Release Process

1. Update version in `manifest.json`
2. Tag release: `git tag v0.1.0`
3. Push: `git push --tags`
4. GitHub Actions will create release
