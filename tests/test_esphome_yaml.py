"""Validate ESPHome YAML configuration catches common issues.

These tests parse tubtron.yaml and check for known-bad patterns
so we catch config errors before attempting a slow ESPHome compile.
"""

from pathlib import Path

import yaml

YAML_FILE = Path(__file__).parent.parent / "esphome" / "tubtron.yaml"


def load_yaml() -> dict:
    """Load tubtron.yaml, handling ESPHome !secret tags."""

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
        """Config must have wifi, api, ota, logger, uart."""
        config = load_yaml()
        for section in ["wifi", "api", "ota", "logger", "uart"]:
            assert section in config, f"Missing required section: {section}"

    def test_uart_has_two_buses(self):
        """Need two UART buses for Pin 5 and Pin 6."""
        config = load_yaml()
        uart = config.get("uart", [])
        assert isinstance(uart, list), "uart: must be a list of bus configs"
        assert len(uart) == 2, f"Expected 2 UART buses, got {len(uart)}"

    def test_uart_baud_rates(self):
        """Both UARTs must be 115200 baud."""
        config = load_yaml()
        for bus in config["uart"]:
            assert bus.get("baud_rate") == 115200, (
                f"UART {bus.get('id', '?')} baud_rate must be 115200, "
                f"got {bus.get('baud_rate')}"
            )

    def test_external_components_local(self):
        """External components must use local source type."""
        config = load_yaml()
        ext = config.get("external_components", [])
        assert len(ext) >= 1, "Missing external_components"
        source = ext[0].get("source", {})
        assert source.get("type") == "local", "external_components source must be local"

    def test_tubtron_display_references_uarts(self):
        """tubtron_display must reference both UART IDs."""
        config = load_yaml()
        td = config.get("tubtron_display", {})
        assert "uart_pin5" in td, "tubtron_display missing uart_pin5 reference"
        assert "uart_pin6" in td, "tubtron_display missing uart_pin6 reference"

    def test_climate_entity_exists(self):
        """Must have a climate entity using tubtron_display platform."""
        config = load_yaml()
        climate = config.get("climate", [])
        assert len(climate) >= 1, "Missing climate entity"
        assert climate[0].get("platform") == "tubtron_display"

    def test_top_level_keys_not_nested(self):
        """Critical ESPHome keys must be at the top level, not nested under other keys.

        Catches the pattern where a leading space on a key (e.g., ' ota:') makes
        it a child of the preceding key in YAML. This is valid YAML but breaks
        ESPHome configuration.
        """
        config = load_yaml()

        # All keys that MUST be top-level in an ESPHome config
        expected_top_level = {
            "esphome",
            "esp32",
            "wifi",
            "api",
            "ota",
            "logger",
            "uart",
            "external_components",
            "climate",
            "sensor",
            "text_sensor",
        }

        # Verify each expected key IS at the top level
        for key in expected_top_level:
            assert key in config, (
                f"Expected top-level key '{key}' not found at root level. "
                f"It may be accidentally nested under another key."
            )

        # Recursively check that none of these keys appear nested inside
        # any top-level value (which would indicate accidental indentation)
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
        """Top-level keys must start at column 0 in the raw YAML file.

        Reads the file line by line and checks that known top-level keys
        appear without leading whitespace. This catches indentation issues
        at the text level before YAML parsing silently nests them.
        """
        known_top_level_keys = [
            "esphome",
            "esp32",
            "wifi",
            "api",
            "ota",
            "logger",
            "uart",
            "external_components",
            "climate",
            "sensor",
            "text_sensor",
            "captive_portal",
            "tubtron_display",
        ]

        raw_text = YAML_FILE.read_text()
        errors = []

        for line_num, line in enumerate(raw_text.splitlines(), start=1):
            stripped = line.lstrip()
            for key in known_top_level_keys:
                # Match "keyname:" at the start of the stripped line
                if stripped.startswith(f"{key}:"):
                    # The key definition must be at column 0 (no leading whitespace)
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
