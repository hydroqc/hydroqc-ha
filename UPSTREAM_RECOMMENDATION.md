# Upstream Recommendation: Loosen aiohttp Dependency Constraint

**To:** Hydro-Quebec-API-Wrapper maintainers (https://gitlab.com/hydroqc/hydroqc)  
**From:** hydroqc-ha integration maintainers  
**Date:** 2025-12-03

## Summary

We recommend loosening the `aiohttp` dependency constraint in `Hydro-Quebec-API-Wrapper` from exact version pins to a compatible version range. This will improve compatibility with Home Assistant and reduce dependency conflicts for users.

## Problem

The current package pins exact versions of dependencies, particularly `aiohttp`:

```python
# Current approach (versions 4.1.0+)
dependencies = [
    "aiohttp==3.13.2",
    # other dependencies...
]
```

This creates conflicts with Home Assistant, which manages its own `aiohttp` version based on release cycles:

- HA 2024.8.0: `aiohttp==3.10.1`
- HA 2024.9.0: `aiohttp==3.10.5`
- HA 2024.10.0: `aiohttp==3.10.8`
- HA 2024.11.0: `aiohttp==3.10.10`
- HA 2024.12.0: `aiohttp==3.11.9`
- HA 2025.1+ (dev): `aiohttp==3.13.2`

When a Home Assistant integration depends on `Hydro-Quebec-API-Wrapper>=4.1.0`, users on stable HA versions (2024.8 through 2024.12) encounter dependency conflicts that prevent the integration from loading, resulting in 500 errors.

## Impact on Users

Users reported issues when trying to install the hydroqc-ha integration via HACS:

```
Error: Config flow could not be loaded: 500 Internal Server Error
Server got itself in trouble
```

This occurs because Home Assistant cannot resolve the conflicting `aiohttp` requirements between:
- Home Assistant's requirement (e.g., `aiohttp==3.11.9` in HA 2024.12)
- Hydro-Quebec-API-Wrapper's requirement (`aiohttp==3.13.2` in versions 4.1.0+)

## Recommended Solution

Change the dependency specification to use version ranges instead of exact pins:

```python
# Recommended approach
dependencies = [
    "aiohttp>=3.10.0,<4.0.0",  # Compatible with HA 2024.8+ and 2025.1+
    "python-dateutil>=2.9.0",
    "pytz>=2024.1",
    "aiocache>=0.12.2,<0.13.0",
    "pkce>=1.0.3",
]
```

### Benefits

1. **Broader compatibility**: Works with multiple Home Assistant versions
2. **Follows best practices**: Python packaging guidelines recommend avoiding over-constraining dependencies
3. **Reduces conflicts**: Allows pip/uv to find compatible versions for all packages
4. **Maintains stability**: Version range is still constrained to compatible major versions
5. **Future-proof**: Will work with upcoming Home Assistant releases

### Why This Range is Safe

- `aiohttp` maintains API compatibility within major versions (3.x)
- The features used by the library are stable across 3.10.0 to 3.13.2
- Breaking changes only occur between major versions (3.x → 4.x)
- Testing has confirmed compatibility with 3.10.x through 3.13.x

## Implementation Details

### Files to Update

1. **pyproject.toml** (or setup.py):
```toml
[project]
dependencies = [
    "aiohttp>=3.10.0,<4.0.0",
    "python-dateutil>=2.9.0",
    "pytz>=2024.1",
    "aiocache>=0.12.2,<0.13.0",
    "pkce>=1.0.3",
]
```

2. **Release strategy**:
   - Release a new minor version (e.g., 4.3.0) with loosened constraints
   - Document the change in release notes
   - Recommend users upgrade to the new version

### Testing Approach

To verify compatibility:

```bash
# Test with different aiohttp versions
pip install aiohttp==3.10.10 .  # HA 2024.11
pip install aiohttp==3.11.9 .   # HA 2024.12
pip install aiohttp==3.13.2 .   # HA 2025.1+

# Run test suite with each version
pytest
```

## Workaround in hydroqc-ha

Until the upstream package is updated, we've implemented a workaround in the hydroqc-ha integration:

```json
{
  "requirements": ["Hydro-Quebec-API-Wrapper>=4.0.0,<5.0.0"]
}
```

This allows Home Assistant to:
- Use version 4.0.0 (which requires `aiohttp==3.10.10`) on older HA versions
- Use version 4.1.0+ (which requires `aiohttp==3.13.2`) on newer HA versions

However, this workaround limits access to newer features in versions 4.1.0+ for users on stable Home Assistant releases.

## Best Practices for Home Assistant Integration Dependencies

When maintaining libraries used by Home Assistant integrations:

1. **Use version ranges**: `package>=X.Y,<(X+1).0` instead of `package==X.Y.Z`
2. **Document compatibility**: Specify which Python and dependency versions are tested
3. **Test with Home Assistant**: Consider testing against Home Assistant's dependency versions
4. **Avoid unnecessary pins**: Only pin when there are known incompatibilities
5. **Follow SemVer**: Trust semantic versioning for API compatibility

## References

- [Python Packaging Guide: Dependencies](https://packaging.python.org/en/latest/discussions/install-requires-vs-requirements/)
- [Home Assistant Requirements](https://github.com/home-assistant/core/blob/dev/requirements.txt)
- Issue in hydroqc-ha: See GitHub issues for "Config flow could not be loaded: 500 Internal Server Error"
- This fix implementation: See pull request for dependency constraint loosening

## Questions?

If you have concerns about this recommendation or need clarification, please reach out through:
- GitHub issue: https://github.com/hydroqc/hydroqc-ha/issues
- GitLab issue: https://gitlab.com/hydroqc/hydroqc/-/issues

We're happy to help test the changes or provide additional information.

---

Thank you for maintaining this valuable library! 🙏
