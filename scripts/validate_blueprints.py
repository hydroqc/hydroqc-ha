#!/usr/bin/env python3
"""Validate Home Assistant blueprints for syntax and structure."""

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ PyYAML not installed. Run: pip install pyyaml")
    sys.exit(1)


# Custom YAML loader that handles Home Assistant tags
class HomeAssistantLoader(yaml.SafeLoader):
    """YAML loader that supports Home Assistant specific tags."""

    pass


# Add constructors for Home Assistant tags
def ha_tag_constructor(loader, tag_suffix, node):
    """Constructor for HA tags like !input, !include, etc."""
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return None


# Register Home Assistant tags
HomeAssistantLoader.add_multi_constructor("!", ha_tag_constructor)


def validate_blueprint(blueprint_path: Path) -> bool:
    """Validate a single blueprint file.

    Args:
        blueprint_path: Path to the blueprint YAML file

    Returns:
        True if valid, False otherwise
    """
    print(f"Validating: {blueprint_path.name}")

    try:
        with open(blueprint_path) as f:
            content = f.read()

        # Parse YAML with Home Assistant loader (will raise exception if invalid)
        data = yaml.load(content, Loader=HomeAssistantLoader)

        # Check for required blueprint structure
        if "blueprint" not in data:
            print("  ❌ Missing 'blueprint' key")
            return False

        blueprint = data["blueprint"]

        # Check required blueprint fields
        required_fields = ["name", "description", "domain", "input"]
        for field in required_fields:
            if field not in blueprint:
                print(f"  ❌ Missing required field: {field}")
                return False

        # Validate inputs are referenced in triggers/actions
        inputs = blueprint.get("input", {})

        # Look for !input references in the YAML content
        for input_name, input_config in inputs.items():
            # Skip group inputs (they have nested 'input' key)
            if isinstance(input_config, dict) and "input" in input_config:
                continue

            if f"!input {input_name}" not in content:
                print(f"  ⚠️  Warning: Input '{input_name}' defined but not used")

        print("  ✅ Valid blueprint")
        return True

    except yaml.YAMLError as e:
        print(f"  ❌ YAML syntax error: {e}")
        return False
    except FileNotFoundError:
        print(f"  ❌ File not found: {blueprint_path}")
        return False
    except Exception as e:
        print(f"  ❌ Validation error: {e}")
        return False


def main():
    """Validate all blueprints in the blueprints directory."""
    print("")
    print("📋 Validating Home Assistant Blueprints")
    print("━" * 60)
    print("")

    blueprints_dir = Path(__file__).parent.parent / "blueprints"

    if not blueprints_dir.exists():
        print(f"❌ Blueprints directory not found: {blueprints_dir}")
        sys.exit(1)

    blueprint_files = list(blueprints_dir.glob("*.yaml")) + list(blueprints_dir.glob("*.yml"))

    if not blueprint_files:
        print(f"⚠️  No blueprint files found in {blueprints_dir}")
        sys.exit(0)

    print(f"Found {len(blueprint_files)} blueprint(s)\n")

    all_valid = True
    for blueprint_file in sorted(blueprint_files):
        if not validate_blueprint(blueprint_file):
            all_valid = False
        print("")

    if all_valid:
        print("✅ All blueprints are valid")
        sys.exit(0)
    else:
        print("❌ Some blueprints have validation errors")
        sys.exit(1)


if __name__ == "__main__":
    main()
