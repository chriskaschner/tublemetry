"""Tests for TOU oscillation prevention and thermal runaway auto-clear.

Validates:
  - ha/tou_automation.yaml has input_boolean.thermal_runaway_active condition
  - TOU structure preserved (6 triggers, alias, mode, setpoint range)
  - ha/thermal_runaway_clear.yaml auto-clears moderate tier flag
  - Auto-clear does NOT re-enable TOU automation (D-08)

Per SAFE-02 decisions D-05 through D-08.
"""

import pytest
import yaml
from pathlib import Path

TOU_FILE = Path(__file__).parent.parent / "ha" / "tou_automation.yaml"
RUNAWAY_FILE = Path(__file__).parent.parent / "ha" / "thermal_runaway.yaml"
CLEAR_FILE = Path(__file__).parent.parent / "ha" / "thermal_runaway_clear.yaml"


@pytest.fixture
def tou_config():
    return yaml.safe_load(TOU_FILE.read_text())


@pytest.fixture
def clear_config():
    return yaml.safe_load(CLEAR_FILE.read_text())


# ---------------------------------------------------------------------------
# TestTouOscillationPrevention: input_boolean condition gating
# ---------------------------------------------------------------------------
class TestTouOscillationPrevention:
    """Verify TOU automation blocks setpoint raises when runaway flag is on."""

    def test_condition_block_is_not_empty(self, tou_config):
        conditions = tou_config.get("condition")
        assert conditions is not None, "condition must not be None"
        assert conditions != [], "condition block must not be empty list"

    def test_condition_has_state_check(self, tou_config):
        conditions = tou_config["condition"]
        has_state = any(
            c.get("condition") == "state" for c in conditions
        )
        assert has_state, "Must have a state condition for input_boolean check"

    def test_condition_checks_thermal_runaway_active(self, tou_config):
        conditions = tou_config["condition"]
        raw = yaml.dump(conditions)
        assert "input_boolean.thermal_runaway_active" in raw, (
            "Must check input_boolean.thermal_runaway_active"
        )

    def test_condition_requires_flag_off(self, tou_config):
        """TOU should only run when thermal_runaway_active is 'off'."""
        conditions = tou_config["condition"]
        for cond in conditions:
            if cond.get("condition") == "state":
                entity = cond.get("entity_id", "")
                if "thermal_runaway_active" in entity:
                    assert cond.get("state") == "off", (
                        "TOU must require thermal_runaway_active == 'off'"
                    )
                    return
        pytest.fail("No state condition found for thermal_runaway_active")


# ---------------------------------------------------------------------------
# TestTouStructurePreserved: verify TOU structure unchanged
# ---------------------------------------------------------------------------
class TestTouStructurePreserved:
    """Verify TOU structure is preserved after adding condition."""

    def test_alias_unchanged(self, tou_config):
        assert tou_config.get("alias") == "Hot Tub TOU Schedule"

    def test_mode_is_single(self, tou_config):
        assert tou_config.get("mode") == "single"

    def test_has_six_triggers(self, tou_config):
        triggers = tou_config.get("trigger", [])
        assert len(triggers) == 6, f"Expected 6 triggers, got {len(triggers)}"

    def test_all_setpoint_values_in_range(self, tou_config):
        """All setpoint values must be within 80-104 range."""
        raw = yaml.dump(tou_config["action"])
        # Extract all 'value:' entries from YAML dump
        for item in tou_config["action"]:
            if "choose" in item:
                for branch in item["choose"]:
                    for act in branch.get("sequence", []):
                        if act.get("action") == "number.set_value":
                            value = act["data"]["value"]
                            assert 80 <= value <= 104, (
                                f"Setpoint {value} outside 80-104 range"
                            )


# ---------------------------------------------------------------------------
# TestTouCrossCheck: entity consistency with thermal_runaway.yaml
# ---------------------------------------------------------------------------
class TestTouCrossCheck:
    """Verify setpoint entity consistency between TOU and thermal runaway."""

    def test_setpoint_entity_matches_runaway(self):
        tou = yaml.safe_load(TOU_FILE.read_text())
        runaway = yaml.safe_load(RUNAWAY_FILE.read_text())

        # Get entity from first TOU choose branch
        tou_entity = None
        for item in tou.get("action", []):
            if "choose" in item:
                first_choice = item["choose"][0]
                for act in first_choice.get("sequence", []):
                    if act.get("action") == "number.set_value":
                        tou_entity = act["target"]["entity_id"]
                        break

        # Get entity from runaway severe branch
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

        assert tou_entity is not None, "Could not find setpoint entity in TOU"
        assert runaway_entity is not None, "Could not find setpoint entity in runaway"
        assert tou_entity == runaway_entity, (
            f"Entity mismatch: TOU={tou_entity}, runaway={runaway_entity}"
        )


# ---------------------------------------------------------------------------
# TestThermalRunawayClear: auto-clear automation structure and behavior
# ---------------------------------------------------------------------------
class TestThermalRunawayClear:
    """Verify thermal_runaway_clear.yaml structure and behavior."""

    def test_yaml_parses(self, clear_config):
        assert isinstance(clear_config, dict)

    def test_alias_contains_runaway_clear(self, clear_config):
        assert "Runaway Clear" in clear_config.get("alias", ""), (
            "Alias must contain 'Runaway Clear'"
        )

    def test_mode_is_single(self, clear_config):
        assert clear_config.get("mode") == "single"

    def test_trigger_is_template(self, clear_config):
        triggers = clear_config.get("trigger", [])
        assert len(triggers) >= 1
        assert triggers[0]["platform"] == "template"

    def test_trigger_compares_temp_le_setpoint(self, clear_config):
        """Trigger must compare temperature <= setpoint."""
        template = clear_config["trigger"][0]["value_template"]
        assert "<=" in template, "Auto-clear trigger must use <= comparison"

    def test_trigger_sustain_at_least_2_minutes(self, clear_config):
        """Trigger must sustain for at least 2 minutes before clearing."""
        trigger = clear_config["trigger"][0]
        minutes = trigger.get("for", {}).get("minutes", 0)
        assert minutes >= 2, f"Auto-clear sustain must be >= 2 min, got {minutes}"

    def test_trigger_uses_float_999_for_temp(self, clear_config):
        """For <= comparison, float(999) for temp is safe default (won't clear)."""
        template = clear_config["trigger"][0]["value_template"]
        assert "float(999)" in template, (
            "Temp must use float(999) safe default for <= comparison"
        )

    def test_trigger_uses_float_0_for_setpoint(self, clear_config):
        """For <= comparison, float(0) for setpoint is safe default (won't clear)."""
        template = clear_config["trigger"][0]["value_template"]
        assert "float(0)" in template, (
            "Setpoint must use float(0) safe default for <= comparison"
        )

    def test_condition_checks_flag_is_on(self, clear_config):
        """Must only clear when flag is actually on."""
        conditions = clear_config["condition"]
        raw = yaml.dump(conditions)
        assert "input_boolean.thermal_runaway_active" in raw
        for cond in conditions:
            if cond.get("condition") == "state":
                entity = cond.get("entity_id", "")
                if "thermal_runaway_active" in entity:
                    assert cond.get("state") == "on", (
                        "Auto-clear must only fire when flag is 'on'"
                    )
                    return
        pytest.fail("No state condition for thermal_runaway_active")

    def test_action_turns_off_flag(self, clear_config):
        actions = clear_config["action"]
        types = [a.get("action") for a in actions]
        assert "input_boolean.turn_off" in types, (
            "Must turn off thermal_runaway_active flag"
        )

    def test_action_turns_off_correct_entity(self, clear_config):
        for a in clear_config["action"]:
            if a.get("action") == "input_boolean.turn_off":
                entity = a.get("target", {}).get("entity_id", "")
                assert entity == "input_boolean.thermal_runaway_active"
                return
        pytest.fail("input_boolean.turn_off not found")

    def test_action_has_notification(self, clear_config):
        types = [a.get("action") for a in clear_config["action"]]
        assert "persistent_notification.create" in types

    def test_notification_id_is_thermal_cleared(self, clear_config):
        for a in clear_config["action"]:
            if a.get("action") == "persistent_notification.create":
                assert a["data"]["notification_id"] == "thermal_cleared"
                return
        pytest.fail("persistent_notification.create not found")

    def test_does_not_reenable_tou(self, clear_config):
        """Auto-clear must NOT re-enable TOU automation (D-08: severe requires manual)."""
        raw = yaml.dump(clear_config)
        assert "automation.turn_on" not in raw, (
            "Auto-clear must NOT re-enable TOU automation"
        )
