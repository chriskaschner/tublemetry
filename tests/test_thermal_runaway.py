"""Tests for the thermal runaway protection automation."""

import pytest
import yaml
from pathlib import Path

RUNAWAY_FILE = Path(__file__).parent.parent / "ha" / "thermal_runaway.yaml"
TOU_FILE = Path(__file__).parent.parent / "ha" / "tou_automation.yaml"

# Safety constants — must match button_injector.h
TEMP_FLOOR = 80
TEMP_CEILING = 104


def load_runaway() -> dict:
    return yaml.safe_load(RUNAWAY_FILE.read_text())


class TestThermalRunawayYamlStructure:
    """Verify the YAML parses and has required top-level keys."""

    @pytest.fixture
    def config(self):
        return load_runaway()

    def test_yaml_parses(self):
        config = load_runaway()
        assert isinstance(config, dict)

    def test_has_alias(self, config):
        assert "alias" in config

    def test_has_trigger(self, config):
        assert "trigger" in config
        assert len(config["trigger"]) > 0

    def test_has_condition(self, config):
        assert "condition" in config

    def test_has_action(self, config):
        assert "action" in config
        assert len(config["action"]) > 0

    def test_mode_is_single(self, config):
        assert config.get("mode") == "single"


class TestThermalRunawayTrigger:
    """Verify trigger logic: template comparison with sustained duration."""

    @pytest.fixture
    def trigger(self):
        return load_runaway()["trigger"][0]

    def test_trigger_is_template(self, trigger):
        assert trigger["platform"] == "template"

    def test_trigger_has_for_duration(self, trigger):
        duration = trigger.get("for", {})
        assert "minutes" in duration, "Trigger must have a 'for' duration in minutes"

    def test_sustain_duration_at_least_3_minutes(self, trigger):
        minutes = trigger["for"]["minutes"]
        assert minutes >= 3, f"Sustain duration {minutes}m too short — risk of false positives"

    def test_sustain_duration_at_most_15_minutes(self, trigger):
        minutes = trigger["for"]["minutes"]
        assert minutes <= 15, f"Sustain duration {minutes}m too long — slow to react"

    def test_trigger_references_temperature_sensor(self, trigger):
        template = trigger["value_template"]
        assert "sensor.tublemetry_hot_tub_temperature" in template

    def test_trigger_references_setpoint_entity(self, trigger):
        template = trigger["value_template"]
        assert "number.tublemetry_hot_tub_setpoint" in template

    def test_trigger_uses_safe_float_default(self, trigger):
        """float(0) for temp means unavailable temp reads as 0 (safe, won't trigger).
        float(999) for setpoint means unavailable setpoint reads as 999 (safe, won't trigger)."""
        template = trigger["value_template"]
        assert "float(0)" in template, "Temperature must default to 0 (safe low) on unavailable"
        assert "float(999)" in template, "Setpoint must default to 999 (safe high) on unavailable"

    def test_overshoot_threshold_is_positive(self, trigger):
        """The template must add a positive margin — we don't want to trigger on exact match."""
        template = trigger["value_template"]
        # Should contain "+ N" where N > 0
        assert "+ 2" in template or "+2" in template, (
            "Trigger must include an overshoot threshold (expected '+ 2')"
        )


class TestThermalRunawayCondition:
    """Verify conditions gate on sensor availability."""

    @pytest.fixture
    def conditions(self):
        return load_runaway()["condition"]

    def test_has_at_least_one_condition(self, conditions):
        assert len(conditions) >= 1

    def test_rejects_unavailable_sensors(self, conditions):
        """At least one condition must check for 'unavailable' or 'unknown' states."""
        raw = yaml.dump(conditions)
        assert "unavailable" in raw, "Must check for 'unavailable' sensor state"
        assert "unknown" in raw, "Must check for 'unknown' sensor state"


class TestThermalRunawayActions:
    """Verify the response sequence: log, notify, disable TOU, drop setpoint."""

    @pytest.fixture
    def actions(self):
        return load_runaway()["action"]

    def test_has_four_actions(self, actions):
        assert len(actions) == 4, f"Expected 4 actions (log, notify, disable TOU, drop setpoint), got {len(actions)}"

    def test_first_action_is_system_log(self, actions):
        assert actions[0].get("action") == "system_log.write"

    def test_log_level_is_warning_or_error(self, actions):
        level = actions[0]["data"]["level"]
        assert level in ("warning", "error"), f"Log level should be warning or error, got {level}"

    def test_second_action_is_persistent_notification(self, actions):
        assert actions[1].get("action") == "persistent_notification.create"

    def test_notification_has_id(self, actions):
        """notification_id allows overwriting on repeated triggers instead of stacking."""
        assert "notification_id" in actions[1]["data"]

    def test_third_action_disables_tou(self, actions):
        assert actions[2].get("action") == "automation.turn_off"
        entity = actions[2]["target"]["entity_id"]
        assert entity == "automation.hot_tub_tou_schedule"

    def test_fourth_action_drops_setpoint(self, actions):
        assert actions[3].get("action") == "number.set_value"
        entity = actions[3]["target"]["entity_id"]
        assert entity == "number.tublemetry_hot_tub_setpoint"

    def test_drop_target_is_floor(self, actions):
        value = actions[3]["data"]["value"]
        assert value == TEMP_FLOOR, f"Drop target should be {TEMP_FLOOR}, got {value}"

    def test_drop_target_within_safe_range(self, actions):
        value = actions[3]["data"]["value"]
        assert TEMP_FLOOR <= value <= TEMP_CEILING


class TestThermalRunawayActionOrder:
    """Verify actions execute in the correct order: log before drop."""

    @pytest.fixture
    def actions(self):
        return load_runaway()["action"]

    def test_log_before_setpoint_drop(self, actions):
        """Log must come before the setpoint drop so we have a record even if drop fails."""
        action_types = [a.get("action") for a in actions]
        log_idx = action_types.index("system_log.write")
        drop_idx = action_types.index("number.set_value")
        assert log_idx < drop_idx

    def test_tou_disable_before_setpoint_drop(self, actions):
        """TOU must be disabled before dropping setpoint, otherwise TOU could
        immediately raise it back on the next trigger."""
        action_types = [a.get("action") for a in actions]
        tou_idx = action_types.index("automation.turn_off")
        drop_idx = action_types.index("number.set_value")
        assert tou_idx < drop_idx


class TestCrossCheckWithTou:
    """Verify the runaway automation references the same entities as TOU."""

    def test_setpoint_entity_matches_tou(self):
        """Both automations must target the same setpoint entity."""
        runaway = load_runaway()
        tou = yaml.safe_load(TOU_FILE.read_text())

        # Get entity from runaway drop action
        runaway_entity = None
        for action in runaway["action"]:
            if action.get("action") == "number.set_value":
                runaway_entity = action["target"]["entity_id"]
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

        assert runaway_entity == tou_entity, (
            f"Entity mismatch: runaway targets {runaway_entity}, TOU targets {tou_entity}"
        )

    def test_tou_automation_entity_id_is_valid(self):
        """The automation entity ID we disable must match the TOU alias (HA convention)."""
        runaway = load_runaway()
        tou = yaml.safe_load(TOU_FILE.read_text())

        # HA generates entity_id from alias: "Hot Tub TOU Schedule" -> "hot_tub_tou_schedule"
        tou_alias = tou.get("alias", "")
        expected_entity = "automation." + tou_alias.lower().replace(" ", "_").replace("-", "_")

        disabled_entity = None
        for action in runaway["action"]:
            if action.get("action") == "automation.turn_off":
                disabled_entity = action["target"]["entity_id"]
                break

        assert disabled_entity == expected_entity, (
            f"TOU disable targets '{disabled_entity}' but TOU alias generates '{expected_entity}'"
        )
