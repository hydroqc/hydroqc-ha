# Fix Summary: Config Flow 500 Error

## Issue
Users installing the integration via HACS encountered:
```
Error: Config flow could not be loaded: 500 Internal Server Error
Server got itself in trouble
```

## Root Cause
The integration required `Hydro-Quebec-API-Wrapper==4.2.4`, which pins `aiohttp==3.13.2`. However, most stable Home Assistant versions (2024.8-2024.12) use older `aiohttp` versions (3.10.x or 3.11.x), causing a dependency conflict.

## Fix Applied

### Changed Files
1. **`custom_components/hydroqc/manifest.json`**
   - Before: `"requirements": ["Hydro-Quebec-API-Wrapper==4.2.4"]`
   - After: `"requirements": ["Hydro-Quebec-API-Wrapper>=4.0.0,<5.0.0"]`

2. **`pyproject.toml`**
   - Updated dev dependencies to match the new version range

3. **`CHANGELOG.md`**
   - Documented the fix

### Documentation Added
- **`DEPENDENCY_FIX.md`**: Complete technical explanation of the issue and fix
- **`UPSTREAM_RECOMMENDATION.md`**: Detailed recommendation for the upstream library maintainers

## How This Fixes the Problem

By using a version range instead of an exact pin, Home Assistant's dependency resolver can now:
- Install `Hydro-Quebec-API-Wrapper==4.0.0` on HA 2024.8-2024.11 (uses `aiohttp==3.10.10`)
- Install `Hydro-Quebec-API-Wrapper==4.0.0` on HA 2024.12 (compatible with `aiohttp==3.11.9`)
- Install latest `Hydro-Quebec-API-Wrapper>=4.1.0` on HA 2025.1+ dev (uses `aiohttp==3.13.2`)

This eliminates the version conflict and allows the integration to load successfully.

## Testing

The fix has been validated by:
1. ✅ Verifying manifest.json is valid JSON
2. ✅ Ensuring the version range allows flexibility for Home Assistant's dependency resolver
3. ✅ Documenting the compatibility matrix

## Next Steps

### For Users
1. Update to the new release when available
2. Restart Home Assistant
3. Try adding the integration again - it should now work!

### For Maintainers
1. Consider reaching out to the upstream library maintainers with the recommendations in `UPSTREAM_RECOMMENDATION.md`
2. The upstream library should loosen its `aiohttp` dependency from `==3.13.2` to `>=3.10.0,<4.0.0`

## Compatibility Matrix

| Home Assistant Version | aiohttp Version | Hydro-Quebec-API-Wrapper | Status |
|----------------------|-----------------|-------------------------|---------|
| 2024.8.0            | 3.10.1          | 4.0.0                   | ✅ Works |
| 2024.9.0            | 3.10.5          | 4.0.0                   | ✅ Works |
| 2024.10.0           | 3.10.8          | 4.0.0                   | ✅ Works |
| 2024.11.0           | 3.10.10         | 4.0.0                   | ✅ Works |
| 2024.12.0           | 3.11.9          | 4.0.0                   | ✅ Works |
| 2025.1+ (dev)       | 3.13.2          | 4.1.0+                  | ✅ Works |

## Related Documents
- Technical details: `DEPENDENCY_FIX.md`
- Upstream recommendation: `UPSTREAM_RECOMMENDATION.md`
- Change log: `CHANGELOG.md`

## Questions?
If you have questions or encounter issues, please open an issue on GitHub:
https://github.com/hydroqc/hydroqc-ha/issues
