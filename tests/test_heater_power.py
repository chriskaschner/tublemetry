"""Tests for heater power binary sensor YAML (PWR-01).

Validates that ha/heater_power.yaml has correct template binary sensor
structure, safe defaults (debounce timing), and documentation for
Enphase entity configuration and stub fallback behavior.
"""

import pytest
import yaml
from pathlib import Path

HEATER_FILE = Path(__file__).parent.parent / "ha" / "heater_power.yaml"


@pytest.fixture
def heater_config():
    return yaml.safe_load(HEATER_FILE.read_text())


@pytest.fixture
def heater_raw():
    return HEATER_FILE.read_text()


class TestHeaterPowerYaml:
    """Basic YAML validity and structure."""

    def test_yaml_parses(self, heater_config):
        assert heater_config is not None

    def test_yaml_is_dict(self, heater_config):
        assert isinstance(heater_config, dict)

    def test_top_level_key_is_template(self, heater_config):
        assert "template" in heater_config


class TestHeaterPowerSensor:
    """Binary sensor entity structure."""

    def test_template_contains_binary_sensor_list(self, heater_config):
        template = heater_config["template"]
        assert isinstance(template, list)
        assert len(template) > 0
        first = template[0]
        assert "binary_sensor" in first

    def test_binary_sensor_name(self, heater_config):
        sensors = heater_config["template"][0]["binary_sensor"]
        assert isinstance(sensors, list)
        assert len(sensors) > 0
        assert sensors[0]["name"] == "Hot Tub Heater Power"

    def test_binary_sensor_has_state_template(self, heater_config):
        sensors = heater_config["template"][0]["binary_sensor"]
        assert "state" in sensors[0]

    def test_binary_sensor_device_class_is_power(self, heater_config):
        sensors = heater_config["template"][0]["binary_sensor"]
        assert sensors[0]["device_class"] == "power"


class TestHeaterPowerSafeDefaults:
    """Debounce timing and safe default configuration."""

    def test_has_delay_on(self, heater_config):
        sensors = heater_config["template"][0]["binary_sensor"]
        assert "delay_on" in sensors[0]

    def test_has_delay_off(self, heater_config):
        sensors = heater_config["template"][0]["binary_sensor"]
        assert "delay_off" in sensors[0]

    def test_delay_off_gte_delay_on(self, heater_config):
        sensors = heater_config["template"][0]["binary_sensor"]
        sensor = sensors[0]
        delay_on_sec = sensor["delay_on"].get("seconds", 0)
        delay_off_sec = sensor["delay_off"].get("seconds", 0)
        assert delay_off_sec >= delay_on_sec, (
            f"delay_off ({delay_off_sec}s) should be >= delay_on ({delay_on_sec}s)"
        )


class TestHeaterPowerDocumentation:
    """Documentation comments in the raw YAML file."""

    def test_has_enphase_configuration_comment(self, heater_raw):
        assert "CONFIGURATION" in heater_raw, (
            "File must contain a comment explaining how to configure the Enphase entity ID"
        )

    def test_has_stub_behavior_comment(self, heater_raw):
        assert "STUB" in heater_raw, (
            "File must contain a comment explaining the stub behavior if Enphase is unavailable"
        )
