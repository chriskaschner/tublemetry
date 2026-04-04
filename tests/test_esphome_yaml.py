"""Validate ESPHome YAML configuration catches common issues.

These tests parse tublemetry.yaml and check for known-bad patterns
so we catch config errors before attempting a slow ESPHome compile.
"""

from pathlib import Path

import pytest
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

    def test_no_climate_entity(self):
        """Architecture uses number entity, not climate entity.

        Climate entity was removed in plan 02-01 and replaced with
        number.tublemetry_hot_tub_setpoint for direct setpoint control.
        """
        config = load_yaml()
        climate = config.get("climate", [])
        assert len(climate) == 0, (
            "climate entity must not be present — architecture uses number entity instead. "
            "Use number.tublemetry_hot_tub_setpoint for setpoint control."
        )

    def test_top_level_keys_not_nested(self):
        """Critical ESPHome keys must be at the top level, not nested under other keys.

        Note: "number" and "switch" are checked for presence but excluded from the
        nesting collision check because "number" is also a legitimate ESPHome pin
        config sub-key (clock_pin.number: GPIO16) and "switch" could appear in
        toggle-action syntax. The presence check confirms they exist at the root.
        """
        config = load_yaml()

        # Keys that must exist at top level — all verified by presence check.
        required_top_level = {
            "esphome",
            "esp32",
            "wifi",
            "api",
            "ota",
            "logger",
            "external_components",
            "sensor",
            "number",
            "switch",
            "text_sensor",
            "safe_mode",
            "button",
            "binary_sensor",
            "captive_portal",
            "tublemetry_display",
        }

        for key in required_top_level:
            assert key in config, (
                f"Expected top-level key '{key}' not found at root level. "
                f"It may be accidentally nested under another key."
            )

        # Keys to check for accidental nesting — exclude "number" and "switch"
        # because they are also valid nested sub-key names in ESPHome pin configs.
        nesting_check_keys = required_top_level - {"number", "switch"}

        def check_no_nesting(parent_key: str, value: object) -> None:
            if isinstance(value, dict):
                for nested_key in value:
                    if nested_key in nesting_check_keys:
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

        Note: "number" is intentionally excluded from this raw-text check because
        the word "number" also appears as an ESPHome pin config sub-key
        (e.g., clock_pin.number: GPIO16). The structural check in
        test_top_level_keys_not_nested handles this correctly via YAML parsing.
        """
        known_top_level_keys = [
            "esphome",
            "esp32",
            "wifi",
            "api",
            "ota",
            "logger",
            "external_components",
            "sensor",
            "switch",
            "text_sensor",
            "captive_portal",
            "tublemetry_display",
            "safe_mode",
            "button",
            "binary_sensor",
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

    def test_tublemetry_binary_sensors_present(self):
        """binary_sensor section must contain a tublemetry_display platform entry
        with heater, pump, and light keys (added in S03/T01).
        """
        config = load_yaml()
        sensors = config.get("binary_sensor", [])
        tublemetry_entry = next(
            (s for s in sensors if s.get("platform") == "tublemetry_display"),
            None,
        )
        assert tublemetry_entry is not None, (
            "No tublemetry_display binary_sensor platform entry found. "
            "Expected an entry from binary_sensor.py (S03)."
        )
        for key in ("heater", "pump", "light"):
            assert key in tublemetry_entry, (
                f"tublemetry_display binary_sensor entry missing '{key}' key"
            )


class TestProductionConfig:
    """Validate production-readiness of ESPHome config."""

    def test_wifi_reboot_timeout(self):
        """WiFi must have reboot_timeout for auto-recovery."""
        config = load_yaml()
        wifi = config.get("wifi", {})
        assert "reboot_timeout" in wifi, "WiFi missing reboot_timeout"

    def test_wifi_power_save_configured(self):
        """WiFi power_save_mode must be explicitly configured."""
        config = load_yaml()
        wifi = config.get("wifi", {})
        assert "power_save_mode" in wifi, "WiFi missing power_save_mode"
        assert wifi.get("power_save_mode") in ("LIGHT", "NONE", "none"), (
            f"Unexpected power_save_mode: {wifi.get('power_save_mode')}. "
            "Expected LIGHT (power-saving) or NONE (max reliability)."
        )

    def test_wifi_fallback_ap(self):
        """WiFi must have fallback AP configured."""
        config = load_yaml()
        wifi = config.get("wifi", {})
        assert "ap" in wifi, "WiFi missing fallback AP"
        ap = wifi["ap"]
        assert "ssid" in ap, "Fallback AP missing SSID"

    def test_api_encryption(self):
        """API must have encryption key configured."""
        config = load_yaml()
        api = config.get("api", {})
        assert "encryption" in api, "API missing encryption"
        assert "key" in api["encryption"], "API encryption missing key"

    def test_api_reboot_timeout(self):
        """API must have reboot_timeout for ghost connectivity recovery."""
        config = load_yaml()
        api = config.get("api", {})
        assert "reboot_timeout" in api, "API missing reboot_timeout"

    def test_ota_has_password(self):
        """OTA must have a password to prevent unauthorized uploads."""
        config = load_yaml()
        ota = config.get("ota", [])
        assert len(ota) >= 1, "Missing OTA config"
        assert "password" in ota[0], "OTA missing password"

    def test_safe_mode_configured(self):
        """safe_mode must be explicitly configured at top level."""
        config = load_yaml()
        assert "safe_mode" in config, "Missing top-level safe_mode config"

    def test_restart_button_exists(self):
        """Must have a restart button for remote recovery."""
        config = load_yaml()
        buttons = config.get("button", [])
        platforms = [b.get("platform") for b in buttons]
        assert "restart" in platforms, "Missing restart button"

    def test_safe_mode_button_exists(self):
        """Must have a safe_mode button for remote recovery."""
        config = load_yaml()
        buttons = config.get("button", [])
        platforms = [b.get("platform") for b in buttons]
        assert "safe_mode" in platforms, "Missing safe_mode button"

    def test_status_binary_sensor(self):
        """Must have API status binary sensor."""
        config = load_yaml()
        sensors = config.get("binary_sensor", [])
        platforms = [s.get("platform") for s in sensors]
        assert "status" in platforms, "Missing status binary sensor"

    def test_wifi_signal_sensor(self):
        """Must have wifi_signal sensor for connectivity monitoring."""
        config = load_yaml()
        sensors = config.get("sensor", [])
        platforms = [s.get("platform") for s in sensors]
        assert "wifi_signal" in platforms, "Missing wifi_signal sensor"

    def test_uptime_sensor(self):
        """Must have uptime sensor for detecting unexpected reboots."""
        config = load_yaml()
        sensors = config.get("sensor", [])
        platforms = [s.get("platform") for s in sensors]
        assert "uptime" in platforms, "Missing uptime sensor"

    def test_version_text_sensor(self):
        """Must have version text sensor for firmware tracking."""
        config = load_yaml()
        text_sensors = config.get("text_sensor", [])
        platforms = [s.get("platform") for s in text_sensors]
        assert "version" in platforms, "Missing version text sensor"

    def test_wifi_info_text_sensor(self):
        """Must have wifi_info text sensor for IP/SSID/MAC."""
        config = load_yaml()
        text_sensors = config.get("text_sensor", [])
        platforms = [s.get("platform") for s in text_sensors]
        assert "wifi_info" in platforms, "Missing wifi_info text sensor"

    def test_diagnostic_entities_have_category(self):
        """All diagnostic sensors must have entity_category: diagnostic."""
        config = load_yaml()

        # Check numeric sensors
        for sensor_entry in config.get("sensor", []):
            platform = sensor_entry.get("platform", "")
            if platform in ("wifi_signal", "uptime"):
                assert sensor_entry.get("entity_category") == "diagnostic", (
                    f"sensor.{platform} missing entity_category: diagnostic"
                )

        # Check text sensors (wifi_info has nested entries)
        for ts in config.get("text_sensor", []):
            platform = ts.get("platform", "")
            if platform == "version":
                assert ts.get("entity_category") == "diagnostic", (
                    "text_sensor.version missing entity_category: diagnostic"
                )
            elif platform == "wifi_info":
                for key in ("ip_address", "ssid", "mac_address"):
                    if key in ts:
                        assert ts[key].get("entity_category") == "diagnostic", (
                            f"text_sensor.wifi_info.{key} missing entity_category"
                        )


class TestTemperatureSensorConfig:
    """Validate temperature sensor configuration in tublemetry_display sensor entry."""

    @pytest.fixture
    def yaml_config(self):
        return load_yaml()

    def _get_tublemetry_sensor_entry(self, config):
        """Return the tublemetry_display entry from the sensor list."""
        for entry in config.get("sensor", []):
            if entry.get("platform") == "tublemetry_display":
                return entry
        return None

    def test_temperature_sensor_present(self, yaml_config):
        entry = self._get_tublemetry_sensor_entry(yaml_config)
        assert entry is not None, "No tublemetry_display sensor platform entry found"
        assert "temperature" in entry, "tublemetry_display sensor entry missing 'temperature' key"

    def test_temperature_sensor_name(self, yaml_config):
        entry = self._get_tublemetry_sensor_entry(yaml_config)
        assert entry["temperature"]["name"] == "Hot Tub Temperature"

    def test_temperature_sensor_no_device_class(self, yaml_config):
        entry = self._get_tublemetry_sensor_entry(yaml_config)
        temp = entry.get("temperature", {})
        assert "device_class" not in temp, (
            "Temperature sensor must NOT have device_class — it triggers HA unit conversion"
        )

    def test_temperature_sensor_no_entity_category(self, yaml_config):
        entry = self._get_tublemetry_sensor_entry(yaml_config)
        temp = entry.get("temperature", {})
        assert "entity_category" not in temp, (
            "Temperature sensor should not have entity_category (it is a primary user-visible entity)"
        )


class TestNumberEntityConfig:
    """Validate number entity configuration in tublemetry.yaml."""

    @pytest.fixture
    def yaml_config(self):
        return load_yaml()

    def _get_tublemetry_number_entry(self, config):
        for entry in config.get("number", []):
            if entry.get("platform") == "tublemetry_display":
                return entry
        return None

    def test_number_block_exists(self, yaml_config):
        assert "number" in yaml_config, "Missing top-level 'number:' block"

    def test_number_tublemetry_platform(self, yaml_config):
        entry = self._get_tublemetry_number_entry(yaml_config)
        assert entry is not None, "No tublemetry_display number platform entry found"

    def test_number_setpoint_present(self, yaml_config):
        entry = self._get_tublemetry_number_entry(yaml_config)
        assert entry is not None
        assert "setpoint" in entry, "tublemetry_display number entry missing 'setpoint' key"

    def test_number_setpoint_name(self, yaml_config):
        entry = self._get_tublemetry_number_entry(yaml_config)
        assert entry["setpoint"]["name"] == "Hot Tub Setpoint"

    def test_number_tublemetry_id(self, yaml_config):
        entry = self._get_tublemetry_number_entry(yaml_config)
        assert entry.get("tublemetry_id") == "hot_tub_display"
