"""Tests for the graduated thermal runaway protection automation.

Validates that ha/thermal_runaway.yaml implements a 3-tier response:
  - Warning (2-4F): log + notify only
  - Moderate (4-6F): proportional setpoint reduction + flag
  - Severe (>6F): floor drop + disable TOU + flag

Per SAFE-01 decisions D-01 through D-04.
"""

import pytest
import yaml
from pathlib import Path

RUNAWAY_FILE = Path(__file__).parent.parent / "ha" / "thermal_runaway.yaml"
TOU_FILE = Path(__file__).parent.parent / "ha" / "tou_automation.yaml"
TEMP_FLOOR = 80


@pytest.fixture
def config():
    return yaml.safe_load(RUNAWAY_FILE.read_text())


@pytest.fixture
def triggers(config):
    return config["trigger"]


@pytest.fixture
def actions(config):
    return config["action"]


def get_choose_branch(actions, trigger_id):
    """Extract a choose branch by its trigger condition id."""
    for item in actions:
        if "choose" in item:
            for branch in item["choose"]:
                for cond in branch.get("conditions", []):
                    if cond.get("id") == trigger_id:
                        return branch
    return None


def get_default_branch(actions):
    """Extract the default branch from a choose block."""
    for item in actions:
        if "default" in item:
            return item["default"]
    return None


# ---------------------------------------------------------------------------
# TestGraduatedThermalRunaway: basic structure
# ---------------------------------------------------------------------------
class TestGraduatedThermalRunaway:
    """Verify YAML parses and has required top-level keys."""

    def test_yaml_parses(self, config):
        assert isinstance(config, dict)

    def test_alias_contains_thermal_runaway(self, config):
        assert "Thermal Runaway" in config.get("alias", "")

    def test_mode_is_single(self, config):
        assert config.get("mode") == "single"

    def test_exactly_three_triggers(self, triggers):
        assert len(triggers) == 3, f"Expected 3 triggers, got {len(triggers)}"

    def test_action_has_choose_block(self, actions):
        has_choose = any("choose" in item for item in actions)
        assert has_choose, "Action must use a choose block for tier dispatch"


# ---------------------------------------------------------------------------
# TestTriggerTiers: tier ordering, thresholds, timing, safe defaults
# ---------------------------------------------------------------------------
class TestTriggerTiers:
    """Verify trigger tier ordering, thresholds, and sustain durations."""

    def test_severe_is_first(self, triggers):
        assert triggers[0].get("id") == "severe", (
            f"Severe must be first trigger (index 0), got '{triggers[0].get('id')}'"
        )

    def test_moderate_is_second(self, triggers):
        assert triggers[1].get("id") == "moderate", (
            f"Moderate must be second trigger (index 1), got '{triggers[1].get('id')}'"
        )

    def test_warning_is_third(self, triggers):
        assert triggers[2].get("id") == "warning", (
            f"Warning must be third trigger (index 2), got '{triggers[2].get('id')}'"
        )

    def test_severe_threshold_plus_6(self, triggers):
        template = triggers[0]["value_template"]
        assert "+ 6" in template, "Severe trigger must use threshold + 6"

    def test_moderate_threshold_plus_4(self, triggers):
        template = triggers[1]["value_template"]
        assert "+ 4" in template, "Moderate trigger must use threshold + 4"

    def test_warning_threshold_plus_2(self, triggers):
        template = triggers[2]["value_template"]
        assert "+ 2" in template, "Warning trigger must use threshold + 2"

    def test_all_triggers_sustain_5_minutes(self, triggers):
        for i, trig in enumerate(triggers):
            minutes = trig.get("for", {}).get("minutes")
            assert minutes == 5, (
                f"Trigger {i} ({trig.get('id')}) sustain must be 5 min, got {minutes}"
            )

    def test_all_triggers_use_float_0_for_temp(self, triggers):
        for trig in triggers:
            template = trig["value_template"]
            assert "float(0)" in template, (
                f"Trigger {trig.get('id')} must use float(0) for temperature safe default"
            )

    def test_all_triggers_use_float_999_for_setpoint(self, triggers):
        for trig in triggers:
            template = trig["value_template"]
            assert "float(999)" in template, (
                f"Trigger {trig.get('id')} must use float(999) for setpoint safe default"
            )


# ---------------------------------------------------------------------------
# TestConditionGating: unknown/unavailable checks, ESP32 online status
# ---------------------------------------------------------------------------
class TestConditionGating:
    """Verify conditions gate on sensor availability and ESP32 status."""

    @pytest.fixture
    def conditions(self, config):
        return config["condition"]

    def test_has_at_least_two_conditions(self, conditions):
        assert len(conditions) >= 2, "Need unknown/unavailable check + ESP32 status check"

    def test_rejects_unknown_sensors(self, conditions):
        raw = yaml.dump(conditions)
        assert "unknown" in raw, "Must check for 'unknown' sensor state"

    def test_rejects_unavailable_sensors(self, conditions):
        raw = yaml.dump(conditions)
        assert "unavailable" in raw, "Must check for 'unavailable' sensor state"

    def test_gates_on_esp32_api_status(self, conditions):
        raw = yaml.dump(conditions)
        assert "binary_sensor.tublemetry_hot_tub_api_status" in raw, (
            "Must gate on ESP32 API status entity (SAFE-03 coordination)"
        )

    def test_esp32_status_must_be_on(self, conditions):
        """ESP32 status condition must require state 'on'."""
        for cond in conditions:
            if cond.get("condition") == "state":
                entity = cond.get("entity_id", "")
                if "api_status" in entity:
                    assert cond.get("state") == "on", "ESP32 status must be 'on'"
                    return
        pytest.fail("No state condition found for ESP32 API status")


# ---------------------------------------------------------------------------
# TestSevereResponse: floor drop, disable TOU, set flag
# ---------------------------------------------------------------------------
class TestSevereResponse:
    """Verify severe tier actions: log, notify, flag, disable TOU, drop to 80."""

    @pytest.fixture
    def branch(self, actions):
        b = get_choose_branch(actions, "severe")
        assert b is not None, "No choose branch found for trigger id 'severe'"
        return b

    @pytest.fixture
    def sequence(self, branch):
        return branch["sequence"]

    def test_has_system_log(self, sequence):
        types = [a.get("action") for a in sequence]
        assert "system_log.write" in types

    def test_has_persistent_notification(self, sequence):
        types = [a.get("action") for a in sequence]
        assert "persistent_notification.create" in types

    def test_notification_id_is_thermal_severe(self, sequence):
        for a in sequence:
            if a.get("action") == "persistent_notification.create":
                assert a["data"]["notification_id"] == "thermal_severe"
                return
        pytest.fail("persistent_notification.create not found in severe sequence")

    def test_sets_runaway_flag(self, sequence):
        types = [a.get("action") for a in sequence]
        assert "input_boolean.turn_on" in types, "Severe must set thermal_runaway_active flag"

    def test_runaway_flag_entity(self, sequence):
        for a in sequence:
            if a.get("action") == "input_boolean.turn_on":
                entity = a.get("target", {}).get("entity_id", "")
                assert entity == "input_boolean.thermal_runaway_active"
                return
        pytest.fail("input_boolean.turn_on not found")

    def test_disables_tou(self, sequence):
        types = [a.get("action") for a in sequence]
        assert "automation.turn_off" in types, "Severe must disable TOU schedule"

    def test_disables_correct_tou_entity(self, sequence):
        for a in sequence:
            if a.get("action") == "automation.turn_off":
                entity = a.get("target", {}).get("entity_id", "")
                assert entity == "automation.hot_tub_tou_schedule"
                return
        pytest.fail("automation.turn_off not found")

    def test_drops_setpoint_to_floor(self, sequence):
        for a in sequence:
            if a.get("action") == "number.set_value":
                value = a.get("data", {}).get("value")
                assert value == TEMP_FLOOR, f"Severe must drop to {TEMP_FLOOR}, got {value}"
                return
        pytest.fail("number.set_value not found in severe sequence")

    def test_has_five_actions(self, sequence):
        assert len(sequence) == 5, (
            f"Severe needs 5 actions (log, notify, flag, disable TOU, drop setpoint), got {len(sequence)}"
        )


# ---------------------------------------------------------------------------
# TestModerateResponse: proportional reduction, set flag, no TOU disable
# ---------------------------------------------------------------------------
class TestModerateResponse:
    """Verify moderate tier: log, notify, flag, proportional reduction."""

    @pytest.fixture
    def branch(self, actions):
        b = get_choose_branch(actions, "moderate")
        assert b is not None, "No choose branch found for trigger id 'moderate'"
        return b

    @pytest.fixture
    def sequence(self, branch):
        return branch["sequence"]

    def test_has_system_log(self, sequence):
        types = [a.get("action") for a in sequence]
        assert "system_log.write" in types

    def test_has_persistent_notification(self, sequence):
        types = [a.get("action") for a in sequence]
        assert "persistent_notification.create" in types

    def test_notification_id_is_thermal_moderate(self, sequence):
        for a in sequence:
            if a.get("action") == "persistent_notification.create":
                assert a["data"]["notification_id"] == "thermal_moderate"
                return
        pytest.fail("persistent_notification.create not found in moderate sequence")

    def test_sets_runaway_flag(self, sequence):
        types = [a.get("action") for a in sequence]
        assert "input_boolean.turn_on" in types, "Moderate must set thermal_runaway_active flag"

    def test_proportional_setpoint_reduction(self, sequence):
        """Moderate tier must use a template for proportional setpoint reduction."""
        for a in sequence:
            if a.get("action") == "number.set_value":
                value = a.get("data", {}).get("value", "")
                # Value must be a template string (not a fixed number)
                assert isinstance(value, str), (
                    "Moderate setpoint must be a template (proportional), not a fixed value"
                )
                return
        pytest.fail("number.set_value not found in moderate sequence")

    def test_does_not_disable_tou(self, sequence):
        """Moderate tier must NOT disable TOU -- only sets the flag."""
        types = [a.get("action") for a in sequence]
        assert "automation.turn_off" not in types, (
            "Moderate must NOT disable TOU automation (only sets flag)"
        )

    def test_has_four_actions(self, sequence):
        assert len(sequence) == 4, (
            f"Moderate needs 4 actions (log, notify, flag, reduce setpoint), got {len(sequence)}"
        )


# ---------------------------------------------------------------------------
# TestWarningResponse: log + notify only -- no flag, no setpoint change
# ---------------------------------------------------------------------------
class TestWarningResponse:
    """Verify warning tier: log + notify only. No flag, no setpoint change."""

    @pytest.fixture
    def default(self, actions):
        d = get_default_branch(actions)
        assert d is not None, "No default branch found in choose block"
        return d

    def test_has_system_log(self, default):
        types = [a.get("action") for a in default]
        assert "system_log.write" in types

    def test_has_persistent_notification(self, default):
        types = [a.get("action") for a in default]
        assert "persistent_notification.create" in types

    def test_notification_id_is_thermal_warning(self, default):
        for a in default:
            if a.get("action") == "persistent_notification.create":
                assert a["data"]["notification_id"] == "thermal_warning"
                return
        pytest.fail("persistent_notification.create not found in warning default")

    def test_does_not_set_flag(self, default):
        """Warning tier is monitoring-only -- no input_boolean action."""
        types = [a.get("action") for a in default]
        assert "input_boolean.turn_on" not in types, (
            "Warning must NOT set thermal_runaway_active flag (monitoring-only)"
        )

    def test_does_not_change_setpoint(self, default):
        """Warning tier must NOT change the setpoint."""
        types = [a.get("action") for a in default]
        assert "number.set_value" not in types, (
            "Warning must NOT change setpoint (monitoring-only)"
        )

    def test_has_two_actions(self, default):
        assert len(default) == 2, (
            f"Warning needs 2 actions (log, notify), got {len(default)}"
        )


# ---------------------------------------------------------------------------
# TestCrossCheck: entity consistency with TOU automation
# ---------------------------------------------------------------------------
class TestCrossCheck:
    """Verify entity references match between thermal runaway and TOU."""

    def test_setpoint_entity_matches_tou(self):
        runaway = yaml.safe_load(RUNAWAY_FILE.read_text())
        tou = yaml.safe_load(TOU_FILE.read_text())

        # Get entity from severe drop action
        runaway_entity = None
        for item in runaway["action"]:
            if "choose" in item:
                for branch in item["choose"]:
                    for cond in branch.get("conditions", []):
                        if cond.get("id") == "severe":
                            for act in branch["sequence"]:
                                if act.get("action") == "number.set_value":
                                    runaway_entity = act["target"]["entity_id"]
                                    break

        # Get entity from first TOU action
        tou_entity = None
        for item in tou.get("action", []):
            if "choose" in item:
                first_choice = item["choose"][0]
                for act in first_choice.get("sequence", []):
                    if "target" in act:
                        tou_entity = act["target"]["entity_id"]
                        break

        assert runaway_entity is not None, "Could not find setpoint entity in runaway severe"
        assert tou_entity is not None, "Could not find setpoint entity in TOU"
        assert runaway_entity == tou_entity, (
            f"Entity mismatch: runaway targets {runaway_entity}, TOU targets {tou_entity}"
        )

    def test_tou_disable_entity_matches_tou_alias(self):
        runaway = yaml.safe_load(RUNAWAY_FILE.read_text())
        tou = yaml.safe_load(TOU_FILE.read_text())

        # HA generates entity_id from alias
        tou_alias = tou.get("alias", "")
        expected_entity = "automation." + tou_alias.lower().replace(" ", "_").replace("-", "_")

        disabled_entity = None
        for item in runaway["action"]:
            if "choose" in item:
                for branch in item["choose"]:
                    for cond in branch.get("conditions", []):
                        if cond.get("id") == "severe":
                            for act in branch["sequence"]:
                                if act.get("action") == "automation.turn_off":
                                    disabled_entity = act["target"]["entity_id"]
                                    break

        assert disabled_entity is not None, "Could not find TOU disable in severe branch"
        assert disabled_entity == expected_entity, (
            f"TOU disable targets '{disabled_entity}' but TOU alias generates '{expected_entity}'"
        )
