# Dependency Conflict Fix

## Issue

Users installing the integration via HACS encountered a 500 Internal Server Error when trying to add the integration. The error message was:

```
Config flow could not be loaded: 500 Internal Server Error Server got itself in trouble
```

## Root Cause

The integration required `Hydro-Quebec-API-Wrapper==4.2.4`, which pins `aiohttp==3.13.2`. However, most Home Assistant stable versions use older versions of `aiohttp`:

- Home Assistant 2024.8.0: `aiohttp==3.10.1`
- Home Assistant 2024.9.0: `aiohttp==3.10.5`
- Home Assistant 2024.10.0: `aiohttp==3.10.8`
- Home Assistant 2024.11.0: `aiohttp==3.10.10`
- Home Assistant 2024.12.0: `aiohttp==3.11.9`
- Home Assistant dev (2025.1+): `aiohttp==3.13.2`

This version conflict prevented Home Assistant from loading the integration's dependencies, resulting in the 500 error.

## Solution

Changed the requirement in `manifest.json` from a pinned version to a range:

**Before:**
```json
"requirements": ["Hydro-Quebec-API-Wrapper==4.2.4"]
```

**After:**
```json
"requirements": ["Hydro-Quebec-API-Wrapper>=4.0.0,<5.0.0"]
```

This allows Home Assistant's dependency resolver to select a compatible version:
- For HA 2024.11.0 and earlier: Uses `Hydro-Quebec-API-Wrapper==4.0.0` (requires `aiohttp==3.10.10`)
- For HA dev/2025.1+: Can use `Hydro-Quebec-API-Wrapper>=4.1.0` (requires `aiohttp==3.13.2`)

## Version Compatibility

### Hydro-Quebec-API-Wrapper Versions

| Version | aiohttp Version | Compatible with HA |
|---------|----------------|-------------------|
| 4.2.4   | 3.13.2        | 2025.1+ (dev)     |
| 4.2.3   | 3.13.2        | 2025.1+ (dev)     |
| 4.2.2   | 3.13.2        | 2025.1+ (dev)     |
| 4.2.1   | 3.13.2        | 2025.1+ (dev)     |
| 4.2.0   | 3.13.2        | 2025.1+ (dev)     |
| 4.1.0   | 3.13.2        | 2025.1+ (dev)     |
| 4.0.0   | 3.10.10       | 2024.8 - 2024.11  |
| 3.2.0   | 3.9.5         | Older versions    |

### Why 4.0.0 is the minimum

Version 4.0.0 is the minimum supported version because:
1. It provides all the features needed by the integration
2. It uses `aiohttp==3.10.10`, compatible with HA 2024.11.0
3. Earlier versions (3.x) are too old and may have API differences

## Recommendation for Upstream

The `Hydro-Quebec-API-Wrapper` package should loosen its `aiohttp` dependency constraint to improve compatibility with Home Assistant's ecosystem. 

**Current approach (problematic):**
```python
dependencies = [
    "aiohttp==3.13.2",  # Exact pin
    # ...
]
```

**Recommended approach:**
```python
dependencies = [
    "aiohttp>=3.10.0,<4.0.0",  # Range that covers HA versions
    # ...
]
```

This change would:
- Allow the package to work with multiple Home Assistant versions
- Reduce dependency conflicts
- Follow Python packaging best practices (avoid over-constraining)
- Still maintain compatibility (3.10.x to 3.13.x are compatible)

### Why This Matters

Home Assistant has a large dependency tree and carefully manages its dependencies to ensure stability. When custom integrations require exact versions of shared dependencies (like `aiohttp`), it creates conflicts that prevent the integration from loading.

By using version ranges instead of exact pins, the package allows Home Assistant's dependency resolver to find compatible versions that satisfy all requirements.

## Testing

The fix has been tested to ensure:
1. The manifest.json is valid
2. The version range allows installation on multiple HA versions
3. The integration's functionality remains unchanged

## References

- Issue: [Config flow could not be loaded: 500 Internal Server Error](https://github.com/hydroqc/hydroqc-ha/issues/XXX)
- Upstream library: https://gitlab.com/hydroqc/hydroqc
- PyPI package: https://pypi.org/project/Hydro-Quebec-API-Wrapper/
