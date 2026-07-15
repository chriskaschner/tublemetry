"""Tests for the self-healing TOU automation and thermal runaway auto-clear.

Validates:
  - ha/tou_automation.yaml is the template-driven, self-healing apply automation:
    triggers on expected-setpoint change, HA start, ESP32 reconnect, and flag
    clear; gated by thermal_runaway_active off + ESP32 online; applies the
    expected setpoint from sensor.hot_tub_expected_setpoint.
  - ha/thermal_runaway_clear.yaml auto-clears the flag and does NOT re-enable TOU
    via automation.turn_on (recovery happens via the schedule's own trigger).

Per SAFE-02 and the auto-recover redesign (reverses D-08/D-12).
"""

import pytest
import yaml
from pathlib import Path

TOU_FILE = Path(__file__).parent.parent / "ha" / "tou_automation.yaml"
RUNAWAY_FILE = Path(__file__).parent.parent / "ha" / "thermal_runaway.yaml"
CLEAR_FILE = Path(__file__).parent.parent / "ha" / "thermal_runaway_clear.yaml"

EXPECTED_SENSOR = "sensor.hot_tub_expected_setpoint"
SETPOINT_ENTITY = "number.tublemetry_hot_tub_setpoint"


def _unwrap_automation(path):
    """Load YAML and unwrap packages automation: list to bare automation dict."""
    data = yaml.safe_load(path.read_text())
    if isinstance(data, dict) and "automation" in data:
        return data["automation"][0]
    return data


@pytest.fixture
def tou_config():
    return _unwrap_automation(TOU_FILE)


@pytest.fixture
def clear_config():
    return _unwrap_automation(CLEAR_FILE)


# ---------------------------------------------------------------------------
# TestTouStructure: identity preserved
# ---------------------------------------------------------------------------
class TestTouStructure:
    def test_id_is_stable(self, tou_config):
        # Other automations / tests reference this id -- must not drift.
        assert tou_config.get("id") == "hot_tub_tou_schedule"

    def test_alias_unchanged(self, tou_config):
        assert tou_config.get("alias") == "Hot Tub TOU Schedule"

    def test_mode_is_single(self, tou_config):
        assert tou_config.get("mode") == "single"


# ---------------------------------------------------------------------------
# TestTouTriggers: self-healing trigger set (replaces the old 6 time triggers)
# ---------------------------------------------------------------------------
class TestTouTriggers:
    def test_trigger_ids(self, tou_config):
        ids = {t.get("id") for t in tou_config["trigger"]}
        assert ids == {"expected_changed", "ha_start", "esp32_online", "runaway_cleared"}

    def test_triggers_on_expected_setpoint_change(self, tou_config):
        matches = [t for t in tou_config["trigger"]
                   if t.get("platform") == "state" and t.get("entity_id") == EXPECTED_SENSOR]
        assert len(matches) == 1, "Must trigger on the expected-setpoint sensor changing"

    def test_triggers_on_ha_start(self, tou_config):
        assert any(t.get("platform") == "homeassistant" and t.get("event") == "start"
                   for t in tou_config["trigger"]), "Must re-apply on HA start"

    def test_triggers_on_esp32_reconnect(self, tou_config):
        assert any(t.get("entity_id") == "binary_sensor.tublemetry_hot_tub_api_status"
                   and t.get("to") == "on" for t in tou_config["trigger"]), \
            "Must re-apply when the ESP32 reconnects (self-heal)"

    def test_triggers_on_flag_clear(self, tou_config):
        assert any(t.get("entity_id") == "input_boolean.thermal_runaway_active"
                   and t.get("to") == "off" for t in tou_config["trigger"]), \
            "Must re-apply when the thermal runaway flag clears"


# ---------------------------------------------------------------------------
# TestTouConditions: gates (not disables) -- self-clearing safety
# ---------------------------------------------------------------------------
class TestTouConditions:
    def test_condition_block_not_empty(self, tou_config):
        assert tou_config.get("condition")

    def test_condition_requires_flag_off(self, tou_config):
        for cond in tou_config["condition"]:
            if cond.get("condition") == "state" and "thermal_runaway_active" in cond.get("entity_id", ""):
                assert cond.get("state") == "off"
                return
        pytest.fail("No state condition requiring thermal_runaway_active == off")

    def test_condition_requires_esp32_online(self, tou_config):
        for cond in tou_config["condition"]:
            if cond.get("condition") == "state" and "api_status" in cond.get("entity_id", ""):
                assert cond.get("state") == "on"
                return
        pytest.fail("No state condition requiring api_status == on (stale-data gate)")


# ---------------------------------------------------------------------------
# TestTouAction: applies the expected setpoint (no hardcoded temps)
# ---------------------------------------------------------------------------
class TestTouAction:
    def _set_action(self, tou_config):
        acts = [a for a in tou_config["action"] if a.get("action") == "number.set_value"]
        assert len(acts) == 1, "Exactly one number.set_value action expected"
        return acts[0]

    def test_targets_setpoint_entity(self, tou_config):
        assert self._set_action(tou_config)["target"]["entity_id"] == SETPOINT_ENTITY

    def test_value_comes_from_expected_sensor(self, tou_config):
        value = self._set_action(tou_config)["data"]["value"]
        assert EXPECTED_SENSOR in value, "Setpoint must be driven by the expected-setpoint sensor"

    def test_value_is_template_not_literal(self, tou_config):
        value = self._set_action(tou_config)["data"]["value"]
        assert isinstance(value, str) and "{{" in value, \
            "Setpoint values must be templated (from sliders), not hardcoded"


# ---------------------------------------------------------------------------
# TestTouCrossCheck: entity consistency with thermal_runaway.yaml
# ---------------------------------------------------------------------------
class TestTouCrossCheck:
    def test_setpoint_entity_matches_runaway(self):
        tou = _unwrap_automation(TOU_FILE)
        runaway = _unwrap_automation(RUNAWAY_FILE)

        tou_entity = None
        for act in tou.get("action", []):
            if act.get("action") == "number.set_value":
                tou_entity = act["target"]["entity_id"]
                break

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

    def test_trigger_requires_heater_off(self, clear_config):
        """Summer-safe clear: release when the heater is OFF (danger source gone),
        not when water <= the floored setpoint (which deadlocked in summer)."""
        template = clear_config["trigger"][0]["value_template"]
        assert "binary_sensor.tublemetry_hot_tub_heater" in template and "'off'" in template, (
            "Auto-clear must require heater == 'off'"
        )

    def test_trigger_checks_below_ceiling(self, clear_config):
        """Must not clear while water is still above the safety ceiling."""
        template = clear_config["trigger"][0]["value_template"]
        assert "107" in template, "Auto-clear must require water below the 107F ceiling"

    def test_trigger_sustain_at_least_2_minutes(self, clear_config):
        """Trigger must sustain for at least 2 minutes before clearing."""
        trigger = clear_config["trigger"][0]
        minutes = trigger.get("for", {}).get("minutes", 0)
        assert minutes >= 2, f"Auto-clear sustain must be >= 2 min, got {minutes}"

    def test_trigger_uses_float_999_for_temp(self, clear_config):
        """float(999) temp default means bad data won't satisfy '< 107' (won't clear)."""
        template = clear_config["trigger"][0]["value_template"]
        assert "float(999)" in template, (
            "Temp must use float(999) safe default so unknown data won't clear"
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

    def test_condition_gates_on_esp32_online(self, clear_config):
        """Must not clear flag on stale data -- require ESP32 online."""
        conditions = clear_config["condition"]
        raw = yaml.dump(conditions)
        assert "tublemetry_hot_tub_api_status" in raw, (
            "Auto-clear must gate on ESP32 online status"
        )

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
        """Auto-clear must NOT call automation.turn_on. Recovery is handled by the
        TOU schedule's own runaway_cleared trigger, not by re-enabling here."""
        raw = yaml.dump(clear_config)
        assert "automation.turn_on" not in raw, (
            "Auto-clear must NOT re-enable TOU via automation.turn_on"
        )
