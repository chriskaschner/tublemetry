"""Tests for drift detection HA automation YAML.

Validates that ha/drift_detection.yaml has correct structure, entity
references, timing, gating conditions, and action types per CMD-02
(D-08 through D-10).
"""

import pytest
import yaml
from pathlib import Path


@pytest.fixture
def drift_config():
    yaml_path = Path(__file__).parent.parent / "ha" / "drift_detection.yaml"
    with open(yaml_path) as f:
        return yaml.safe_load(f)


class TestDriftDetectionYaml:
    def test_yaml_is_valid(self, drift_config):
        assert drift_config is not None

    def test_has_alias(self, drift_config):
        assert "alias" in drift_config
        assert "Drift Detection" in drift_config["alias"]

    def test_mode_is_single(self, drift_config):
        assert drift_config.get("mode") == "single"


class TestDriftDetectionEntities:
    def test_trigger_references_detected_setpoint(self, drift_config):
        trigger = drift_config["trigger"][0]
        assert "sensor.tublemetry_hot_tub_detected_setpoint" in trigger["value_template"]

    def test_trigger_references_commanded_setpoint(self, drift_config):
        trigger = drift_config["trigger"][0]
        assert "number.tublemetry_hot_tub_setpoint" in trigger["value_template"]

    def test_trigger_references_injection_phase(self, drift_config):
        trigger = drift_config["trigger"][0]
        assert "text_sensor.tublemetry_hot_tub_injection_phase" in trigger["value_template"]

    def test_trigger_checks_idle(self, drift_config):
        trigger = drift_config["trigger"][0]
        assert "'idle'" in trigger["value_template"]


class TestDriftDetectionTiming:
    def test_trigger_has_for_duration(self, drift_config):
        trigger = drift_config["trigger"][0]
        assert "for" in trigger

    def test_for_duration_is_2_minutes(self, drift_config):
        trigger = drift_config["trigger"][0]
        assert trigger["for"]["minutes"] == 2


class TestDriftDetectionGating:
    def test_condition_excludes_unknown(self, drift_config):
        conditions = drift_config["condition"]
        condition_text = str(conditions)
        assert "unknown" in condition_text

    def test_condition_excludes_unavailable(self, drift_config):
        conditions = drift_config["condition"]
        condition_text = str(conditions)
        assert "unavailable" in condition_text


class TestDriftDetectionAction:
    def test_has_system_log_action(self, drift_config):
        actions = drift_config["action"]
        action_types = [a.get("action", "") for a in actions]
        assert "system_log.write" in action_types

    def test_has_persistent_notification(self, drift_config):
        actions = drift_config["action"]
        action_types = [a.get("action", "") for a in actions]
        assert "persistent_notification.create" in action_types

    def test_notification_id_is_setpoint_drift(self, drift_config):
        actions = drift_config["action"]
        for a in actions:
            if a.get("action") == "persistent_notification.create":
                assert a["data"]["notification_id"] == "setpoint_drift"
                return
        pytest.fail("persistent_notification.create action not found")
