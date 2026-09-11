"""Structural tests for ha/hot_tub_button.yaml and its override contract.

The SNZB-01P button drives the tub setpoint through a manual-override flag that
three OTHER packages have to respect. These tests pin down both the button
wiring and that cross-package contract, because breaking either one fails
silently in ways that look like flaky hardware:

  - wrong event code    -> button does nothing, looks like a dead battery
  - override not honored in tou_automation -> press reverted on ESP32 reconnect
  - override not honored in tou_watchdog   -> false "TOU NOT WORKING" pages
"""

import re
from pathlib import Path

import pytest
import yaml

from ha_yaml import is_secret, load_ha_yaml

HA_DIR = Path(__file__).parent.parent / "ha"
BUTTON_FILE = HA_DIR / "hot_tub_button.yaml"
TOU_FILE = HA_DIR / "tou_automation.yaml"
WATCHDOG_FILE = HA_DIR / "tou_watchdog.yaml"

# RECAPTURED live with scripts/capture_button_events.py on 2026-09-11, after the
# coordinator moved from ConBee II/deCONZ to SONOFF ZBDongle-E/ZHA. These are
# OBSERVED values (5/4/4 clean observations), not datasheet values -- do not
# "correct" them without recapturing.
#
# The names are ZCL On/Off cluster commands and are NOT semantic: "on" is simply
# what this device emits for a double press. It does not mean "turn something
# on".
SINGLE_PRESS = "toggle"
DOUBLE_PRESS = "on"
LONG_PRESS = "off"

# The button is matched by its Zigbee IEEE, which is burned into the radio and so
# survived the deCONZ -> ZHA migration unchanged and will survive any future
# re-pair. HA's `device_id` would not -- it is a registry key regenerated on
# every remove/re-add.
#
# The address itself is NOT stored here. ha/ is deployed to the PUBLIC
# tublemetry-ha repo, so the real value lives in /config/secrets.yaml under this
# key and the YAML references it with !secret.
IEEE_SECRET_KEY = "hot_tub_button_ieee"

# Anything that looks like a bare EUI-64 (8 colon-separated hex octets). Used to
# prove no hardware address has been inlined back into the package.
EUI64_RE = re.compile(r"\b(?:[0-9a-fA-F]{2}:){7}[0-9a-fA-F]{2}\b")


@pytest.fixture
def pkg():
    return load_ha_yaml(BUTTON_FILE)


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
    codes = {t["event_data"]["command"] for t in control["trigger"]}
    assert codes == {SINGLE_PRESS, DOUBLE_PRESS, LONG_PRESS}


def test_triggers_are_zha_events_for_this_device(control):
    for trig in control["trigger"]:
        assert trig["platform"] == "event"
        assert trig["event_type"] == "zha_event"
        assert is_secret(trig["event_data"]["device_ieee"], IEEE_SECRET_KEY), (
            f"trigger {trig['id']} must source device_ieee from "
            f"!secret {IEEE_SECRET_KEY}"
        )


def test_no_hardware_address_is_inlined_in_the_package():
    """ha/ is deployed to a PUBLIC repo, so no EUI-64 may appear in this file.

    Guards the specific regression of someone replacing the !secret with a
    literal address to "just make it work" -- which would silently republish the
    hardware address on the next deploy.
    """
    found = EUI64_RE.findall(BUTTON_FILE.read_text())
    assert not found, f"hardware address(es) inlined in {BUTTON_FILE.name}: {found}"


def test_gesture_to_trigger_id_mapping(control):
    by_code = {t["event_data"]["command"]: t["id"] for t in control["trigger"]}
    assert by_code[SINGLE_PRESS] == "single_press"
    assert by_code[DOUBLE_PRESS] == "double_press"
    assert by_code[LONG_PRESS] == "long_press"


def test_on_off_commands_are_strings_not_yaml_booleans(control):
    """`on` and `off` are YAML 1.1 booleans, so unquoted they load as True/False.

    An unquoted `command: on` silently becomes `command: True`, which matches no
    real zha_event -- the double press would simply stop working, and it would
    look exactly like a dead battery. Quoting is load-bearing, so pin it.
    """
    for trig in control["trigger"]:
        command = trig["event_data"]["command"]
        assert isinstance(command, str), (
            f"trigger {trig['id']} has command={command!r} of type "
            f"{type(command).__name__}; quote it in the YAML"
        )


def test_does_not_trigger_on_cluster_attribute_updates(control):
    """The device emits `attribute_updated` alongside every gesture.

    Binding it would fire each press twice -- once for the gesture and once for
    the On/Off attribute mirroring it.
    """
    codes = {t["event_data"]["command"] for t in control["trigger"]}
    assert "attribute_updated" not in codes


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


# --- Dashboard-facing wrappers -------------------------------------------
#
# The card rows used to point at button.tublemetry_hot_tub_temp_up_test, which
# fires one raw relay pulse: no wake-press make-up, no verification, and it
# clears the injector's cached setpoint. These wrappers exist so the dashboard
# reaches the same closed loop the physical button uses. The tests below pin the
# delegation itself, because a wrapper that reimplements the guards instead of
# delegating would lose the runaway/offline refusals silently.

WRAPPERS = [
    "hot_tub_set_hot",
    "hot_tub_set_cold",
    "hot_tub_resume_schedule",
    "hot_tub_nudge_up",
    "hot_tub_nudge_down",
]


def _delegating_call(sequence):
    """The hot_tub_apply_setpoint call inside a wrapper's sequence."""
    for step in sequence:
        if step.get("action") == "script.hot_tub_apply_setpoint":
            return step
    raise AssertionError("wrapper does not delegate to hot_tub_apply_setpoint")


@pytest.mark.parametrize("name", WRAPPERS)
def test_wrapper_exists(pkg, name):
    assert name in pkg["script"], f"{name} missing -- dashboard card would 404"


@pytest.mark.parametrize("name", WRAPPERS)
def test_wrapper_delegates_rather_than_reimplementing(pkg, name):
    """Guards live in hot_tub_apply_setpoint. A wrapper must not bypass them."""
    seq = pkg["script"][name]["sequence"]
    _delegating_call(seq)
    assert not any(
        step.get("action") == "number.set_value" for step in seq
    ), f"{name} sets the number directly, skipping the runaway/offline guards"


def test_set_hot_reads_the_max_slider(pkg):
    """Hardcoding 102 here is the bug the seasonal sliders were added to stop."""
    call = _delegating_call(pkg["script"]["hot_tub_set_hot"]["sequence"])
    assert "input_number.hot_tub_max_setpoint" in call["data"]["target"]
    assert call["data"]["set_override"] is True


def test_set_cold_reads_the_coast_slider(pkg):
    call = _delegating_call(pkg["script"]["hot_tub_set_cold"]["sequence"])
    assert "input_number.hot_tub_coast_setpoint" in call["data"]["target"]
    assert call["data"]["set_override"] is True


def test_resume_schedule_clears_the_override(pkg):
    """The app-side equivalent of the long press -- must NOT raise the flag."""
    call = _delegating_call(pkg["script"]["hot_tub_resume_schedule"]["sequence"])
    assert "sensor.hot_tub_expected_setpoint" in call["data"]["target"]
    assert call["data"]["set_override"] is False


@pytest.mark.parametrize("name", ["hot_tub_nudge_up", "hot_tub_nudge_down"])
def test_nudges_hold_until_the_next_boundary(pkg, name):
    call = _delegating_call(pkg["script"][name]["sequence"])
    assert call["data"]["set_override"] is True


@pytest.mark.parametrize("name", ["hot_tub_nudge_up", "hot_tub_nudge_down"])
def test_nudges_base_on_the_panel_not_the_command(pkg, name):
    """A nudge after a failed injection must move from where the tub IS."""
    seq = pkg["script"][name]["sequence"]
    base = seq[0]["variables"]["base"]
    assert "sensor.tublemetry_hot_tub_detected_setpoint" in base
    assert "number.tublemetry_hot_tub_setpoint" in base, "no fallback source"


@pytest.mark.parametrize(
    "name,limit", [("hot_tub_nudge_up", "104"), ("hot_tub_nudge_down", "80")]
)
def test_nudges_refuse_at_the_clamp_instead_of_a_no_op(pkg, name, limit):
    """A no-op target runs the retry ladder and latches failed (known bug).

    The clamp values mirror button_injector.h TEMP_CEILING / TEMP_FLOOR.
    """
    seq = pkg["script"][name]["sequence"]
    guard = next(step for step in seq if "if" in step)
    assert limit in guard["if"]
    actions = [s.get("action") for s in guard["then"]]
    assert any(a and a.startswith("notify.") for a in actions), "silent refusal"
    assert any("stop" in s for s in guard["then"]), "does not stop before nudging"
