"""Structural tests for ha/hot_tub_button.yaml and its override contract.

The SNZB-01P button drives the tub setpoint through a manual-override flag that
three OTHER packages have to respect. These tests pin down both the button
wiring and that cross-package contract, because breaking either one fails
silently in ways that look like flaky hardware:

  - wrong event code    -> button does nothing, looks like a dead battery
  - override not honored in tou_automation -> press reverted on ESP32 reconnect
  - override not honored in tou_watchdog   -> false "TOU NOT WORKING" pages
"""

from pathlib import Path

import pytest
import yaml

HA_DIR = Path(__file__).parent.parent / "ha"
BUTTON_FILE = HA_DIR / "hot_tub_button.yaml"
TOU_FILE = HA_DIR / "tou_automation.yaml"
WATCHDOG_FILE = HA_DIR / "tou_watchdog.yaml"

# Captured live from the device with scripts/capture_button_events.py on
# 2026-08-31 (two clean passes). These are OBSERVED values, not datasheet
# values -- do not "correct" them without recapturing.
SINGLE_PRESS = 1002
DOUBLE_PRESS = 1004
LONG_PRESS = 1003
DEVICE_ID = "roundbutton"


@pytest.fixture
def pkg():
    return yaml.safe_load(BUTTON_FILE.read_text())


@pytest.fixture
def control(pkg):
    return next(a for a in pkg["automation"] if a["id"] == "hot_tub_button_control")


@pytest.fixture
def expiry(pkg):
    return next(a for a in pkg["automation"] if a["id"] == "hot_tub_override_expiry")


@pytest.fixture
def script(pkg):
    return pkg["script"]["hot_tub_apply_setpoint"]


def _branch(automation, trigger_id):
    """The choose-branch sequence guarded by the given trigger id."""
    for option in automation["action"][0]["choose"]:
        for cond in option["conditions"]:
            if cond.get("id") == trigger_id or trigger_id in (cond.get("id") or []):
                return option["sequence"]
    raise AssertionError(f"no branch for trigger id {trigger_id!r}")


# --- package structure ---


def test_is_valid_package(pkg):
    assert isinstance(pkg, dict)
    assert isinstance(pkg.get("automation"), list)
    assert "script" in pkg and "input_boolean" in pkg


def test_defines_override_flag(pkg):
    assert "hot_tub_manual_override" in pkg["input_boolean"]


# --- button wiring: the empirically captured codes ---


def test_all_three_gestures_bound(control):
    codes = {t["event_data"]["event"] for t in control["trigger"]}
    assert codes == {SINGLE_PRESS, DOUBLE_PRESS, LONG_PRESS}


def test_triggers_are_deconz_events_for_this_device(control):
    for trig in control["trigger"]:
        assert trig["platform"] == "event"
        assert trig["event_type"] == "deconz_event"
        assert trig["event_data"]["id"] == DEVICE_ID


def test_gesture_to_trigger_id_mapping(control):
    by_code = {t["event_data"]["event"]: t["id"] for t in control["trigger"]}
    assert by_code[SINGLE_PRESS] == "single_press"
    assert by_code[DOUBLE_PRESS] == "double_press"
    assert by_code[LONG_PRESS] == "long_press"


def test_queued_mode_does_not_drop_fast_presses(control):
    assert control["mode"] == "queued"
    assert control["max"] >= 2


# --- gesture semantics ---


def test_single_press_applies_max_slider(control):
    data = _branch(control, "single_press")[0]["data"]
    assert "input_number.hot_tub_max_setpoint" in data["target"]
    assert data["set_override"] is True


def test_double_press_applies_coast_slider(control):
    data = _branch(control, "double_press")[0]["data"]
    assert "input_number.hot_tub_coast_setpoint" in data["target"]
    # A deliberate Coast press is just as much an override as a Max press; if
    # this is False the press gets reverted on the next ESP32 reconnect.
    assert data["set_override"] is True


def test_long_press_resumes_schedule_and_clears_override(control):
    data = _branch(control, "long_press")[0]["data"]
    assert "sensor.hot_tub_expected_setpoint" in data["target"]
    assert data["set_override"] is False


# --- the script's refuse-loudly safety gates ---


def test_script_gates_on_runaway_esp32_and_range(script):
    gates = yaml.dump(script["sequence"][1]["choose"])
    assert "input_boolean.thermal_runaway_active" in gates
    assert "binary_sensor.tublemetry_hot_tub_api_status" in gates
    assert "80" in gates and "104" in gates, "must clamp to the firmware range"


def test_every_refusal_notifies(script):
    """A blocked press must still push, or it is indistinguishable from a
    press that never registered -- the button has no feedback of its own."""
    for option in script["sequence"][1]["choose"]:
        actions = {step.get("action") for step in option["sequence"]}
        assert "notify.mobile_app_chris_iphone" in actions
        assert any("stop" in step for step in option["sequence"])


def test_script_verifies_before_notifying_success(script):
    """The push must report the panel's actual value, not merely that a command
    was sent -- injection can and does fail."""
    waits = [s for s in script["sequence"] if "wait_template" in s]
    assert len(waits) == 1
    tpl = waits[0]["wait_template"]
    assert "sensor.tublemetry_hot_tub_detected_setpoint" in tpl
    assert "sensor.tublemetry_hot_tub_injection_phase" in tpl
    assert waits[0]["continue_on_timeout"] is True, "a timeout must still notify"


def test_script_restart_mode(script):
    assert script["mode"] == "restart"


# --- override expiry ---


def test_override_expires_on_boundary_and_runaway(expiry):
    ids = {t.get("id") for t in expiry["trigger"]}
    assert ids == {"boundary", "runaway"}


def test_boundary_trigger_ignores_unknown_transitions(expiry):
    """HA-start 'unknown' -> value must not count as a boundary and silently
    eat an override the user just set."""
    trig = next(t for t in expiry["trigger"] if t["id"] == "boundary")
    assert trig["entity_id"] == "sensor.hot_tub_expected_setpoint"
    assert "unknown" in trig["not_from"] and "unknown" in trig["not_to"]


def test_expiry_turns_the_flag_off(expiry):
    actions = [s.get("action") for s in expiry["action"]]
    assert "input_boolean.turn_off" in actions


# --- cross-package contract ---


def test_tou_automation_yields_to_override():
    tou = yaml.safe_load(TOU_FILE.read_text())["automation"][0]
    dumped = yaml.dump(tou["condition"])
    assert "input_boolean.hot_tub_manual_override" in dumped, (
        "tou_automation must not clobber a manual override on ESP32 reconnect"
    )


def test_tou_automation_still_applies_at_boundaries():
    """The override must EXPIRE at a boundary, not survive it -- so the boundary
    and runaway-clear triggers stay exempt from the override check."""
    tou = yaml.safe_load(TOU_FILE.read_text())["automation"][0]
    or_cond = next(c for c in tou["condition"] if c.get("condition") == "or")
    trig_cond = next(
        c for c in or_cond["conditions"] if c.get("condition") == "trigger"
    )
    assert set(trig_cond["id"]) == {"expected_changed", "runaway_cleared"}


def test_watchdog_suppressed_during_override():
    wd = yaml.safe_load(WATCHDOG_FILE.read_text())["automation"][0]
    trig = next(t for t in wd["trigger"] if t.get("id") == "setpoint_stuck")
    assert "input_boolean.hot_tub_manual_override" in trig["value_template"], (
        "a deliberate override must not page the user as a stuck setpoint"
    )


def test_drift_detection_not_suppressed():
    """Deliberately NOT suppressed: drift compares PANEL vs COMMANDED, which
    must agree no matter who commanded it, so it stays valid during overrides."""
    drift = yaml.safe_load((HA_DIR / "drift_detection.yaml").read_text())
    assert "hot_tub_manual_override" not in yaml.dump(drift)
