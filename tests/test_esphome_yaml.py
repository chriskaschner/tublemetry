"""Validate ESPHome YAML configuration catches common issues.

These tests parse tublemetry.yaml and check for known-bad patterns
so we catch config errors before attempting a slow ESPHome compile.
"""

from pathlib import Path

import yaml

YAML_FILE = Path(__file__).parent.parent / "esphome" / "tublemetry.yaml"


def load_yaml() -> dict:
    """Load tublemetry.yaml, handling ESPHome !secret tags."""

    class SecretLoader(yaml.SafeLoader):
        pass

    SecretLoader.add_constructor(
        "!secret", lambda loader, node: f"SECRET({loader.construct_scalar(node)})"
    )
    return yaml.load(YAML_FILE.read_text(), Loader=SecretLoader)


class TestEsphomeYaml:
    """Validate ESPHome YAML structure."""

    def test_yaml_file_exists(self):
        assert YAML_FILE.exists(), f"ESPHome YAML not found: {YAML_FILE}"

    def test_yaml_parses(self):
        config = load_yaml()
        assert isinstance(config, dict)

    def test_no_deprecated_platform_in_esphome_block(self):
        """platform/board must NOT be inside esphome: block (removed in 2024.x)."""
        config = load_yaml()
        esphome_block = config.get("esphome", {})
        assert "platform" not in esphome_block, (
            "Deprecated: 'platform' inside esphome: block. "
            "Use a top-level 'esp32:' block instead."
        )
        assert "board" not in esphome_block, (
            "Deprecated: 'board' inside esphome: block. "
            "Use a top-level 'esp32:' block instead."
        )

    def test_esp32_block_exists(self):
        """Top-level esp32: block must exist with board defined."""
        config = load_yaml()
        assert "esp32" in config, "Missing top-level 'esp32:' block"
        esp32 = config["esp32"]
        assert "board" in esp32, "esp32: block must specify 'board'"

    def test_has_required_sections(self):
        """Config must have wifi, api, ota, logger, tublemetry_display."""
        config = load_yaml()
        for section in ["wifi", "api", "ota", "logger", "tublemetry_display"]:
            assert section in config, f"Missing required section: {section}"

    def test_tublemetry_display_has_gpio_pins(self):
        """tublemetry_display must reference clock and data GPIO pins."""
        config = load_yaml()
        td = config.get("tublemetry_display", {})
        assert "clock_pin" in td, "tublemetry_display missing clock_pin"
        assert "data_pin" in td, "tublemetry_display missing data_pin"

    def test_external_components_local(self):
        """External components must use local source type."""
        config = load_yaml()
        ext = config.get("external_components", [])
        assert len(ext) >= 1, "Missing external_components"
        source = ext[0].get("source", {})
        assert source.get("type") == "local", "external_components source must be local"

    def test_climate_entity_exists(self):
        """Must have a climate entity using tublemetry_display platform."""
        config = load_yaml()
        climate = config.get("climate", [])
        assert len(climate) >= 1, "Missing climate entity"
        assert climate[0].get("platform") == "tublemetry_display"

    def test_top_level_keys_not_nested(self):
        """Critical ESPHome keys must be at the top level, not nested under other keys."""
        config = load_yaml()

        expected_top_level = {
            "esphome",
            "esp32",
            "wifi",
            "api",
            "ota",
            "logger",
            "external_components",
            "tublemetry_display",
            "climate",
            "sensor",
            "text_sensor",
        }

        for key in expected_top_level:
            assert key in config, (
                f"Expected top-level key '{key}' not found at root level. "
                f"It may be accidentally nested under another key."
            )

        def check_no_nesting(parent_key: str, value: object) -> None:
            if isinstance(value, dict):
                for nested_key in value:
                    if nested_key in expected_top_level:
                        raise AssertionError(
                            f"Top-level key '{nested_key}' is incorrectly nested "
                            f"under '{parent_key}'. Check YAML indentation."
                        )
                    check_no_nesting(f"{parent_key}.{nested_key}", value[nested_key])
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    check_no_nesting(f"{parent_key}[{i}]", item)

        for key in config:
            check_no_nesting(key, config[key])

    def test_no_unexpected_indentation_in_raw_yaml(self):
        """Top-level keys must start at column 0 in the raw YAML file."""
        known_top_level_keys = [
            "esphome",
            "esp32",
            "wifi",
            "api",
            "ota",
            "logger",
            "external_components",
            "climate",
            "sensor",
            "text_sensor",
            "captive_portal",
            "tublemetry_display",
        ]

        raw_text = YAML_FILE.read_text()
        errors = []

        for line_num, line in enumerate(raw_text.splitlines(), start=1):
            stripped = line.lstrip()
            for key in known_top_level_keys:
                if stripped.startswith(f"{key}:"):
                    if line != stripped:
                        leading = len(line) - len(stripped)
                        errors.append(
                            f"Line {line_num}: '{key}:' has {leading} leading "
                            f"space(s) -- should start at column 0"
                        )

        assert not errors, (
            "Top-level keys found with unexpected indentation:\n"
            + "\n".join(errors)
        )
