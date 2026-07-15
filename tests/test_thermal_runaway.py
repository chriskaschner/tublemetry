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


def _unwrap_automation(path):
    """Load YAML and unwrap packages automation: list to bare automation dict."""
    data = yaml.safe_load(path.read_text())
    if isinstance(data, dict) and "automation" in data:
        return data["automation"][0]
    return data


@pytest.fixture
def config():
    return _unwrap_automation(RUNAWAY_FILE)


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

    def test_four_triggers_three_tiers_plus_ceiling(self, triggers):
        # 3 heater-gated relative tiers (severe/moderate/warning) + 1 absolute
        # ceiling backstop (also id 'severe').
        assert len(triggers) == 4, f"Expected 4 triggers, got {len(triggers)}"
        ids = [t.get("id") for t in triggers]
        assert ids.count("severe") == 2 and "moderate" in ids and "warning" in ids

    def test_action_has_choose_block(self, actions):
        has_choose = any("choose" in item for item in actions)
        assert has_choose, "Action must use a choose block for tier dispatch"


# ---------------------------------------------------------------------------
# TestTriggerTiers: tier ordering, thresholds, timing, safe defaults
# ---------------------------------------------------------------------------
SETPOINT_ENTITY = "number.tublemetry_hot_tub_setpoint"


def _relative(triggers):
    """Overshoot tiers compare against the setpoint (heater-gated)."""
    return [t for t in triggers if SETPOINT_ENTITY in t["value_template"]]


def _ceiling(triggers):
    """Absolute-ceiling backstop triggers do not reference the setpoint."""
    return [t for t in triggers
            if t.get("id") == "severe" and SETPOINT_ENTITY not in t["value_template"]]


class TestTriggerTiers:
    """Verify tier thresholds, the summer heater-gate, and the ceiling backstop."""

    def test_severe_is_first(self, triggers):
        assert triggers[0].get("id") == "severe", (
            f"Severe must be first trigger (index 0), got '{triggers[0].get('id')}'"
        )

    def test_has_all_three_tiers(self, triggers):
        ids = {t.get("id") for t in triggers}
        assert {"severe", "moderate", "warning"} <= ids

    def test_severe_relative_threshold_plus_6(self, triggers):
        rel = [t for t in _relative(triggers) if t.get("id") == "severe"]
        assert rel and "+ 6" in rel[0]["value_template"], "Severe tier must use setpoint + 6"

    def test_moderate_threshold_plus_4(self, triggers):
        m = [t for t in triggers if t.get("id") == "moderate"]
        assert m and "+ 4" in m[0]["value_template"], "Moderate tier must use setpoint + 4"

    def test_warning_threshold_plus_2(self, triggers):
        w = [t for t in triggers if t.get("id") == "warning"]
        assert w and "+ 2" in w[0]["value_template"], "Warning tier must use setpoint + 2"

    def test_relative_tiers_gate_on_heater_on(self, triggers):
        """Summer fix: overshoot tiers must require the heater to be ON so a
        setpoint coast-down (heater off) does not false-trigger."""
        for t in _relative(triggers):
            tpl = t["value_template"]
            assert "binary_sensor.tublemetry_hot_tub_heater" in tpl and "'on'" in tpl, (
                f"Relative tier '{t.get('id')}' must gate on heater == 'on'"
            )

    def test_has_absolute_ceiling_backstop(self, triggers):
        ceiling = _ceiling(triggers)
        assert ceiling, "Must have an absolute ceiling severe trigger (heater-independent)"
        assert "107" in ceiling[0]["value_template"]

    def test_ceiling_is_not_heater_gated(self, triggers):
        for t in _ceiling(triggers):
            assert "heater" not in t["value_template"], (
                "Ceiling backstop must fire regardless of heater state"
            )

    def test_relative_tiers_sustain_5_minutes(self, triggers):
        for t in _relative(triggers):
            assert t.get("for", {}).get("minutes") == 5, (
                f"Relative tier '{t.get('id')}' sustain must be 5 min"
            )

    def test_all_triggers_use_float_0_for_temp(self, triggers):
        for trig in triggers:
            assert "float(0)" in trig["value_template"], (
                f"Trigger {trig.get('id')} must use float(0) for temperature safe default"
            )

    def test_relative_tiers_use_float_999_for_setpoint(self, triggers):
        for trig in _relative(triggers):
            assert "float(999)" in trig["value_template"], (
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
    """Verify severe tier actions: log, notify, flag, drop to 80 (no TOU disable)."""

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

    def test_does_not_disable_tou(self, sequence):
        """Severe must NOT disable the TOU automation. The runaway flag gates the
        schedule instead, so recovery is automatic once the flag clears (reverses
        D-08)."""
        types = [a.get("action") for a in sequence]
        assert "automation.turn_off" not in types, (
            "Severe must not disable TOU -- the flag gates the schedule"
        )

    def test_drops_setpoint_to_floor(self, sequence):
        for a in sequence:
            if a.get("action") == "number.set_value":
                value = a.get("data", {}).get("value")
                assert value == TEMP_FLOOR, f"Severe must drop to {TEMP_FLOOR}, got {value}"
                return
        pytest.fail("number.set_value not found in severe sequence")

    def test_has_four_actions(self, sequence):
        assert len(sequence) == 4, (
            f"Severe needs 4 actions (log, notify, flag, drop setpoint), got {len(sequence)}"
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
        runaway = _unwrap_automation(RUNAWAY_FILE)
        tou = _unwrap_automation(TOU_FILE)

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

        # Get entity from the TOU apply action (direct number.set_value)
        tou_entity = None
        for act in tou.get("action", []):
            if act.get("action") == "number.set_value":
                tou_entity = act["target"]["entity_id"]
                break

        assert runaway_entity is not None, "Could not find setpoint entity in runaway severe"
        assert tou_entity is not None, "Could not find setpoint entity in TOU"
        assert runaway_entity == tou_entity, (
            f"Entity mismatch: runaway targets {runaway_entity}, TOU targets {tou_entity}"
        )

    def test_severe_does_not_reference_tou_disable(self):
        """The redesign removed automation.turn_off from the severe branch."""
        runaway = _unwrap_automation(RUNAWAY_FILE)
        raw = yaml.dump(runaway)
        assert "automation.turn_off" not in raw, (
            "thermal_runaway.yaml must no longer disable the TOU automation"
        )
