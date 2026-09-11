"""Structural tests for ha/ac_vent_monitor.yaml.

The vent sensor is now the PRIMARY compressor watchdog, with the slow
indoor-temperature check in ac_compressor_monitor.yaml demoted to a log-only
fallback. That trade is only safe if a dead vent sensor is itself alarmed, so
these tests pin that guarantee down alongside the detection logic.
"""

from pathlib import Path

import pytest
import yaml

HA_DIR = Path(__file__).parent.parent / "ha"
VENT_FILE = HA_DIR / "ac_vent_monitor.yaml"
LEGACY_FILE = HA_DIR / "ac_compressor_monitor.yaml"

VENT_SENSOR = "sensor.ac_vent_temperature"


@pytest.fixture
def pkg():
    return yaml.safe_load(VENT_FILE.read_text())


def _auto(pkg, auto_id):
    return next(a for a in pkg["automation"] if a["id"] == auto_id)


# --- package structure ---


def test_is_valid_package(pkg):
    assert isinstance(pkg, dict)
    assert isinstance(pkg.get("automation"), list)
    for key in ("template", "input_number", "input_boolean"):
        assert key in pkg, f"missing {key}"


def test_three_automations_present(pkg):
    ids = {a["id"] for a in pkg["automation"]}
    assert ids == {
        "ac_vent_compressor_not_cooling",
        "ac_vent_cooling_recovered",
        "ac_vent_sensor_offline",
    }


# --- tunables ---


def test_thresholds_are_sliders_not_constants(pkg):
    """Correct delta depends on physical placement, which is not known until the
    sensor is mounted -- retuning must not require a redeploy."""
    inums = pkg["input_number"]
    assert "ac_vent_delta_threshold" in inums
    assert "ac_vent_confirm_minutes" in inums


def test_no_initial_on_sliders(pkg):
    """`initial:` re-applies on every restart and would silently wipe the user's
    calibration -- the same trap documented in helpers.yaml."""
    for name, entry in pkg["input_number"].items():
        assert "initial" not in entry, f"{name} must not declare initial:"


def test_slider_minimums_are_the_intended_defaults(pkg):
    """With no `initial:`, an unconfigured slider comes up at its minimum, so
    the minimum has to be a value that is safe to run with untuned."""
    inums = pkg["input_number"]
    # Conservative: only fires when the vent is basically at room temperature.
    assert inums["ac_vent_delta_threshold"]["min"] == 2
    # Must exceed the ecobee's ~3 min poll lag plus sensor settling.
    assert inums["ac_vent_confirm_minutes"]["min"] >= 10


def test_stale_window_is_not_one_hour(pkg):
    """Measured 2026-08-31: the SNZB-02B reports on ~0.5 F change, not on a
    dependable heartbeat -- 4 points in 6 hours with a 5.5-hour gap while sitting
    in still air. A 1-hour window cried 'sensor offline' every night once the AC
    stopped cycling. Regression guard against reintroducing that."""
    assert "ac_vent_stale_hours" in pkg["input_number"]
    assert pkg["input_number"]["ac_vent_stale_hours"]["min"] >= 3

    health = next(
        b
        for b in pkg["template"][1]["binary_sensor"]
        if b["unique_id"] == "ac_vent_sensor_healthy"
    )
    assert "ac_vent_stale_hours" in health["state"]
    assert "3600" not in health["state"].replace("* 3600", ""), (
        "stale window must come from the slider, not a hardcoded hour"
    )


# --- detection logic ---


def test_delta_sensor_compares_vent_to_indoor(pkg):
    sensors = pkg["template"][0]["sensor"]
    delta = next(s for s in sensors if s["unique_id"] == "ac_vent_delta")
    assert VENT_SENSOR in delta["state"]
    assert "climate.my_ecobee" in delta["state"]
    assert "availability" in delta, "must not publish a delta from missing inputs"


def test_fault_requires_cooling_commanded_and_healthy_sensor(pkg):
    trig = _auto(pkg, "ac_vent_compressor_not_cooling")["trigger"][0]
    tpl = trig["value_template"]
    assert "binary_sensor.ac_cooling_commanded" in tpl
    assert "binary_sensor.ac_vent_sensor_healthy" in tpl
    assert "input_number.ac_vent_delta_threshold" in tpl


def test_fault_reverifies_at_fire_time(pkg):
    """The `for:` window can end on a state that has since flipped back."""
    conds = yaml.dump(_auto(pkg, "ac_vent_compressor_not_cooling")["condition"])
    assert "binary_sensor.ac_cooling_commanded" in conds
    assert "binary_sensor.ac_vent_sensor_healthy" in conds


def test_fault_pushes_to_phone(pkg):
    actions = [s.get("action") for s in _auto(pkg, "ac_vent_compressor_not_cooling")["action"]]
    assert "notify.mobile_app_chris_iphone" in actions


# --- the guarantee that makes demoting the old check safe ---


def test_sensor_health_uses_last_reported(pkg):
    """last_changed would call a stable temperature 'dead'; last_reported
    advances on every report even when the value has not moved."""
    bins = pkg["template"][1]["binary_sensor"]
    health = next(b for b in bins if b["unique_id"] == "ac_vent_sensor_healthy")
    assert "last_reported" in health["state"]
    assert VENT_SENSOR.split(".")[1] in health["state"]


def _offline_branches(pkg):
    """Return (gateway_up_sequence, gateway_down_sequence) for the offline alert."""
    offline = _auto(pkg, "ac_vent_sensor_offline")
    choose = next(s for s in offline["action"] if "choose" in s)
    return choose["choose"][0]["sequence"], choose["default"]


def test_dead_vent_sensor_alerts(pkg):
    """Primary watchdog going blind must not be silent."""
    offline = _auto(pkg, "ac_vent_sensor_offline")
    trig = offline["trigger"][0]
    assert trig["entity_id"] == "binary_sensor.ac_vent_sensor_healthy"
    assert trig["to"] == "off"
    up_branch, _ = _offline_branches(pkg)
    actions = [s.get("action") for s in up_branch]
    assert "notify.mobile_app_chris_iphone" in actions


def test_offline_alert_is_gated_on_gateway_health(pkg):
    """REGRESSION (2026-09-09): ac_vent_sensor_healthy goes off both on the
    stale-hours window AND on the sensor reading 'unavailable'. The second fires
    on every deCONZ gateway freeze, and 58 of 80 freezes over 10 days outlasted
    the 30-minute `for:` -- about 5.8 false pushes a day. The push branch must
    require the gateway to be UP, so it only fires for a genuinely dead device."""
    up_branch, _ = _offline_branches(pkg)
    offline = _auto(pkg, "ac_vent_sensor_offline")
    choose = next(s for s in offline["action"] if "choose" in s)
    conds = choose["choose"][0]["conditions"]
    assert any(
        c.get("entity_id") == "binary_sensor.zigbee_gateway_up" and c.get("state") == "on"
        for c in conds
    ), "push branch is not gated on gateway health"
    assert any(s.get("action") == "notify.mobile_app_chris_iphone" for s in up_branch)


def test_gateway_freeze_branch_is_silent(pkg):
    """deconz_freeze_watchdog already owns the gateway case and pushes if its
    restart fails, so pushing here too would page twice for one fault."""
    _, down_branch = _offline_branches(pkg)
    actions = [s.get("action", "") for s in down_branch]
    assert not any(a.startswith("notify.") for a in actions), "gateway branch pushes"
    assert "system_log.write" in actions, "gateway branch is completely silent"


def test_offline_message_reports_real_silence_not_the_threshold(pkg):
    """The old text asserted 'has not reported in 3h' during a 30-minute freeze
    and told you to check a battery sitting at 100%."""
    offline = _auto(pkg, "ac_vent_sensor_offline")
    var_step = next(s for s in offline["action"] if "variables" in s)
    assert "last_reported" in var_step["variables"]["silent_minutes"]
    up_branch, _ = _offline_branches(pkg)
    push = next(s for s in up_branch if s.get("action") == "notify.mobile_app_chris_iphone")
    assert "silent_minutes" in push["data"]["message"]
    assert "ac_vent_stale_hours" not in push["data"]["message"]


def test_recovery_clears_the_fault(pkg):
    recovered = _auto(pkg, "ac_vent_cooling_recovered")
    actions = [s.get("action") for s in recovered["action"]]
    assert "persistent_notification.dismiss" in actions
    assert "input_boolean.turn_off" in actions


# --- contract with the demoted legacy package ---


def test_legacy_package_no_longer_pushes():
    """Demoted to log-only so one failure does not page twice."""
    legacy = yaml.safe_load(LEGACY_FILE.read_text())
    auto = legacy["automation"][0]
    actions = [s.get("action") for s in auto["action"]]
    assert "notify.mobile_app_chris_iphone" not in actions
    assert "system_log.write" in actions, "must still leave a diagnostic trail"


def test_legacy_package_still_owns_cooling_commanded():
    """ac_vent_monitor depends on this sensor and must not redefine it."""
    legacy = yaml.safe_load(LEGACY_FILE.read_text())
    names = {
        b["unique_id"]
        for block in legacy["template"]
        for b in block.get("binary_sensor", [])
    }
    assert "ac_cooling_commanded" in names

    vent = yaml.safe_load(VENT_FILE.read_text())
    vent_names = {
        b.get("unique_id")
        for block in vent["template"]
        for b in block.get("binary_sensor", [])
    }
    assert "ac_cooling_commanded" not in vent_names, "would register a duplicate _2 entity"
