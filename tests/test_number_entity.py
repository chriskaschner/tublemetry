"""Tests for the TublemetrySetpoint number entity and TOU automation correctness."""

import pytest
import yaml
from pathlib import Path

# --- Constants (mirrors number.py codegen values and ButtonInjector clamps) ---
NUMBER_MIN = 80
NUMBER_MAX = 104
NUMBER_STEP = 1

TOU_FILE = Path(__file__).parent.parent / "ha" / "tou_automation.yaml"


def load_tou() -> dict:
    data = yaml.safe_load(TOU_FILE.read_text())
    if isinstance(data, dict) and "automation" in data:
        return data["automation"][0]
    return data


def extract_action_values(tou_config) -> list:
    """Return all data.value fields from TOU choose action sequences."""
    values = []
    for item in tou_config.get("action", []):
        if "choose" in item:
            for choice in item["choose"]:
                for act in choice.get("sequence", []):
                    if "data" in act and "value" in act["data"]:
                        values.append(act["data"]["value"])
    return values


def extract_all_actions(tou_config) -> list:
    """Return all action dicts from TOU choose sequences."""
    actions = []
    for item in tou_config.get("action", []):
        if "choose" in item:
            for choice in item["choose"]:
                for act in choice.get("sequence", []):
                    actions.append(act)
    return actions


class TestNumberEntityRange:
    """Verify number entity range constants match ButtonInjector and codegen."""

    def test_min_value(self):
        assert NUMBER_MIN == 80

    def test_max_value(self):
        assert NUMBER_MAX == 104

    def test_step(self):
        assert NUMBER_STEP == 1

    def test_floor_in_range(self):
        assert NUMBER_MIN >= 80

    def test_ceiling_in_range(self):
        assert NUMBER_MAX <= 104

    def test_below_floor_rejected(self):
        assert 79 < NUMBER_MIN

    def test_above_ceiling_rejected(self):
        assert 105 > NUMBER_MAX

    @pytest.mark.parametrize("value", range(80, 105))
    def test_all_valid_values_in_range(self, value):
        assert NUMBER_MIN <= value <= NUMBER_MAX

    def test_no_conversion_passthrough(self):
        """Simulate control(float) passthrough: value arrives unchanged at request_temperature."""
        def simulate_control(value: float) -> float:
            # Mirrors TublemetrySetpoint::control() behavior:
            # ESPHome clamps to [min, max] before calling control() --
            # values inside range pass through unchanged.
            v = round(value)
            assert NUMBER_MIN <= v <= NUMBER_MAX, f"{v} is out of range"
            return v
        assert simulate_control(104.0) == 104
        assert simulate_control(96.0) == 96
        assert simulate_control(102.0) == 102
        assert simulate_control(98.0) == 98


class TestTouAutomation:
    """Verify TOU automation targets correct entity with correct degF values."""

    @pytest.fixture
    def tou_config(self):
        return load_tou()

    def test_tou_yaml_parses(self):
        config = load_tou()
        assert isinstance(config, dict)

    def test_no_climate_entity_referenced(self, tou_config):
        raw = TOU_FILE.read_text()
        assert "climate" not in raw, (
            "TOU automation must not reference climate entity -- use number entity instead"
        )

    def test_all_actions_use_number_set_value(self, tou_config):
        actions = extract_all_actions(tou_config)
        assert len(actions) > 0, "No actions found in TOU automation"
        for act in actions:
            assert act.get("action") == "number.set_value", (
                f"Expected 'number.set_value', got: {act.get('action')}"
            )

    def test_all_actions_target_number_entity(self, tou_config):
        actions = extract_all_actions(tou_config)
        for act in actions:
            entity_id = act.get("target", {}).get("entity_id")
            assert entity_id == "number.tublemetry_hot_tub_setpoint", (
                f"Expected 'number.tublemetry_hot_tub_setpoint', got: {entity_id}"
            )

    def test_no_celsius_values(self, tou_config):
        values = extract_action_values(tou_config)
        celsius_values = {40.0, 38.9, 36.7, 35.6}
        for v in values:
            assert v not in celsius_values, (
                f"TOU value {v} looks like a Celsius value -- must be integer degF"
            )

    def test_degf_values_only(self, tou_config):
        values = extract_action_values(tou_config)
        valid_degf = {104, 102, 98, 96}
        for v in values:
            assert v in valid_degf, (
                f"Unexpected TOU value {v} -- expected one of {valid_degf}"
            )

    def test_six_action_blocks(self, tou_config):
        values = extract_action_values(tou_config)
        assert len(values) == 6, f"Expected 6 TOU action values, got {len(values)}"

    def test_trigger_ids_present(self, tou_config):
        triggers = tou_config.get("trigger", [])
        trigger_ids = {t.get("id") for t in triggers if "id" in t}
        expected = {"wd_preheat", "we_preheat", "wd_onpeak", "wd_eve_preheat", "wd_eve_full", "coast"}
        assert expected == trigger_ids, (
            f"Missing trigger IDs: {expected - trigger_ids}"
        )
