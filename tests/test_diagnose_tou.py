"""Tests for scripts/diagnose_tou.py -- the pure diagnose() core.

The REST I/O (class HA) is not exercised here; we feed diagnose() a
{entity_id: state_obj} mapping just like HA's /api/states returns and assert on
the findings it produces.
"""

from datetime import datetime, timezone

import pytest

import diagnose_tou as d


# --------------------------------------------------------------------------- #
# Fixtures / builders
# --------------------------------------------------------------------------- #
def st(state, **attrs):
    """Build an HA state object."""
    return {"state": state, "attributes": attrs}


CANONICAL = {
    d.SCHEDULE: "Hot Tub TOU Schedule",
    "automation.hot_tub_thermal_runaway_protection": "Hot Tub Thermal Runaway Protection",
    "automation.hot_tub_thermal_runaway_clear": "Hot Tub Thermal Runaway Clear",
    "automation.hot_tub_esp32_offline_detection": "Hot Tub ESP32 Offline Detection",
    "automation.hot_tub_setpoint_drift_detection": "Hot Tub Setpoint Drift Detection",
    "automation.hot_tub_refresh_thermal_model": "Hot Tub Refresh Thermal Model",
}


def healthy_states():
    states = {
        d.SCHEDULE: st("on", friendly_name="Hot Tub TOU Schedule",
                       last_triggered="2026-07-15T10:00:03+00:00", id="hot_tub_tou_schedule"),
        d.FLAG: st("off"),
        d.API_STATUS: st("on"),
        d.COMMANDED: st("104"),
        d.DETECTED: st("104"),
        d.RETRY: st("0"),
        d.INJECTION_PHASE[0]: st("idle"),
        d.LAST_RESULT[0]: st("ok"),
        d.COMPONENT_VERSION: st("0.2.0"),
        d.UPTIME: st("86400"),
    }
    for eid, name in CANONICAL.items():
        states.setdefault(eid, st("on", friendly_name=name))
    return states


NOW = datetime(2026, 7, 15, 17, 0, 0, tzinfo=timezone.utc)


def status_of(report, key):
    f = report.get(key)
    return f.status if f else None


# --------------------------------------------------------------------------- #
# Healthy baseline
# --------------------------------------------------------------------------- #
def test_healthy_overall_pass():
    report = d.diagnose(healthy_states(), now=NOW, repo_version="0.2.0")
    assert report.overall == d.PASS
    assert status_of(report, "schedule") == d.PASS
    assert status_of(report, "runaway_flag") == d.PASS
    assert status_of(report, "esp32") == d.PASS
    assert status_of(report, "setpoint") == d.PASS
    assert status_of(report, "duplicates") == d.PASS
    assert status_of(report, "firmware") == d.PASS
    assert status_of(report, "inventory") == d.PASS


# --------------------------------------------------------------------------- #
# The core failure mode: schedule silently disabled
# --------------------------------------------------------------------------- #
def test_disabled_schedule_fails():
    states = healthy_states()
    states[d.SCHEDULE] = st("off", friendly_name="Hot Tub TOU Schedule",
                            last_triggered="2026-07-09T10:00:00+00:00")
    report = d.diagnose(states, now=NOW, repo_version="0.2.0")
    assert report.overall == d.FAIL
    assert status_of(report, "schedule") == d.FAIL
    assert "days ago" in report.get("schedule").detail


def test_missing_schedule_entity_fails():
    states = healthy_states()
    del states[d.SCHEDULE]
    report = d.diagnose(states, now=NOW, repo_version="0.2.0")
    assert status_of(report, "schedule") == d.FAIL


# --------------------------------------------------------------------------- #
# Other blocking conditions
# --------------------------------------------------------------------------- #
def test_stuck_runaway_flag_fails():
    states = healthy_states()
    states[d.FLAG] = st("on")
    report = d.diagnose(states, now=NOW, repo_version="0.2.0")
    assert status_of(report, "runaway_flag") == d.FAIL
    assert report.overall == d.FAIL


def test_esp32_offline_fails():
    states = healthy_states()
    states[d.API_STATUS] = st("off")
    report = d.diagnose(states, now=NOW, repo_version="0.2.0")
    assert status_of(report, "esp32") == d.FAIL


def test_setpoint_mismatch_fails():
    states = healthy_states()
    states[d.COMMANDED] = st("104")
    states[d.DETECTED] = st("99")
    report = d.diagnose(states, now=NOW, repo_version="0.2.0")
    assert status_of(report, "setpoint") == d.FAIL
    assert "MISMATCH" in report.get("setpoint").title


def test_setpoint_within_tolerance_passes():
    states = healthy_states()
    states[d.COMMANDED] = st("104")
    states[d.DETECTED] = st("104.0")
    report = d.diagnose(states, now=NOW, repo_version="0.2.0")
    assert status_of(report, "setpoint") == d.PASS


# --------------------------------------------------------------------------- #
# Cruft detection
# --------------------------------------------------------------------------- #
def test_duplicate_entities_warn():
    states = healthy_states()
    states["sensor.hot_tub_heating_rate_2"] = st("0.5")
    report = d.diagnose(states, now=NOW, repo_version="0.2.0")
    assert status_of(report, "duplicates") == d.WARN
    assert "sensor.hot_tub_heating_rate_2" in report.get("duplicates").detail


def test_lingering_automation_warn():
    states = healthy_states()
    states["automation.log_heating_command"] = st("on", friendly_name="Log Heating Command")
    report = d.diagnose(states, now=NOW, repo_version="0.2.0")
    inv = report.get("inventory")
    assert inv.status == d.WARN
    assert "Log Heating Command" in inv.detail


def test_missing_canonical_automation_warn():
    states = healthy_states()
    del states["automation.hot_tub_setpoint_drift_detection"]
    report = d.diagnose(states, now=NOW, repo_version="0.2.0")
    assert status_of(report, "missing") == d.WARN
    assert "Hot Tub Setpoint Drift Detection" in report.get("missing").detail


def test_watchdog_absence_is_info_not_warn():
    # Pre-deploy, the watchdog isn't present; that must not be flagged as lingering
    # (it's a NEW automation) nor as a missing-core WARN.
    report = d.diagnose(healthy_states(), now=NOW, repo_version="0.2.0")
    assert status_of(report, "inventory") == d.PASS
    assert status_of(report, "pending") == d.INFO


# --------------------------------------------------------------------------- #
# Firmware
# --------------------------------------------------------------------------- #
def test_firmware_drift_warn():
    states = healthy_states()
    states[d.COMPONENT_VERSION] = st("0.1.0")
    report = d.diagnose(states, now=NOW, repo_version="0.2.0")
    assert status_of(report, "firmware") == d.WARN
    assert "0.1.0" in report.get("firmware").title


def test_firmware_match_pass():
    report = d.diagnose(healthy_states(), now=NOW, repo_version="0.2.0")
    assert status_of(report, "firmware") == d.PASS


def test_firmware_unknown_info():
    states = healthy_states()
    states[d.COMPONENT_VERSION] = st("unavailable")
    report = d.diagnose(states, now=NOW, repo_version="0.2.0")
    assert status_of(report, "firmware") == d.INFO


# --------------------------------------------------------------------------- #
# Helper units
# --------------------------------------------------------------------------- #
def test_num_parses_and_rejects():
    assert d._num(st("104")) == 104.0
    assert d._num(st("unavailable")) is None
    assert d._num(st("unknown")) is None
    assert d._num(None) is None
    assert d._num(st("not-a-number")) is None


def test_pick_first_present():
    states = {"sensor.b": st("2")}
    assert d._pick(states, "sensor.a", "sensor.b")["state"] == "2"
    assert d._pick(states, "sensor.x") is None


def test_age_days():
    now = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
    assert "days ago" in d._age("2026-07-09T12:00:00+00:00", now)
    assert d._age(None, now) == ""


def test_repo_component_version_matches_header():
    # The script reads the same literal the firmware publishes.
    assert d.repo_component_version() == "0.3.0"
