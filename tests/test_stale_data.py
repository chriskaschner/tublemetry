"""Tests for stale data gating HA automation YAML.

Validates that ha/stale_data.yaml has correct structure for ESP32 offline
detection and TOU gating per SAFE-03 (D-09 through D-12).

When ESP32 goes offline:
- User is notified via persistent notification
- The TOU schedule is NOT disabled here; it self-pauses via its api_status
  condition and resumes on reconnect (auto-recover redesign, reverses D-12)

When ESP32 comes back online:
- User is notified
- The schedule resumes automatically (no automation.turn_on needed)
"""

import pytest
import yaml
from pathlib import Path


STALE_FILE = Path(__file__).parent.parent / "ha" / "stale_data.yaml"
TOU_FILE = Path(__file__).parent.parent / "ha" / "tou_automation.yaml"


def _unwrap_automation(path):
    """Load YAML and unwrap packages automation: list to bare automation dict."""
    data = yaml.safe_load(path.read_text())
    if isinstance(data, dict) and "automation" in data:
        return data["automation"][0]
    return data


@pytest.fixture
def stale_config():
    return _unwrap_automation(STALE_FILE)


@pytest.fixture
def tou_config():
    return _unwrap_automation(TOU_FILE)


class TestStaleDataYaml:
    """Basic structure validation."""

    def test_yaml_is_valid(self, stale_config):
        assert stale_config is not None

    def test_has_alias_with_offline(self, stale_config):
        assert "alias" in stale_config
        assert "Offline" in stale_config["alias"]

    def test_mode_is_single(self, stale_config):
        assert stale_config.get("mode") == "single"


class TestStaleDataTriggers:
    """Trigger validation: 3 triggers, correct entity, correct IDs."""

    def test_has_three_triggers(self, stale_config):
        assert len(stale_config["trigger"]) == 3

    def test_all_triggers_reference_api_status(self, stale_config):
        for trigger in stale_config["trigger"]:
            assert trigger["entity_id"] == "binary_sensor.tublemetry_hot_tub_api_status"

    def test_offline_trigger_to_off(self, stale_config):
        triggers = stale_config["trigger"]
        off_triggers = [t for t in triggers if t.get("to") == "off"]
        assert len(off_triggers) == 1
        assert off_triggers[0]["id"] == "offline"

    def test_offline_trigger_to_unavailable(self, stale_config):
        triggers = stale_config["trigger"]
        unavail_triggers = [t for t in triggers if t.get("to") == "unavailable"]
        assert len(unavail_triggers) == 1
        assert unavail_triggers[0]["id"] == "offline"

    def test_online_trigger_to_on(self, stale_config):
        triggers = stale_config["trigger"]
        on_triggers = [t for t in triggers if t.get("to") == "on"]
        assert len(on_triggers) == 1
        assert on_triggers[0]["id"] == "online"

    def test_offline_triggers_both_have_id_offline(self, stale_config):
        triggers = stale_config["trigger"]
        offline_triggers = [t for t in triggers if t.get("id") == "offline"]
        assert len(offline_triggers) == 2


class TestStaleDataOfflineResponse:
    """Offline branch: choose block with notification (no TOU disable)."""

    def test_action_has_choose_block(self, stale_config):
        actions = stale_config["action"]
        choose_actions = [a for a in actions if "choose" in a]
        assert len(choose_actions) >= 1

    def test_offline_branch_has_notification(self, stale_config):
        choose = stale_config["action"][0]["choose"]
        # Find the offline branch (condition with trigger id "offline")
        offline_branch = None
        for branch in choose:
            conditions = branch.get("conditions", [])
            for cond in conditions:
                if cond.get("id") == "offline":
                    offline_branch = branch
                    break
        assert offline_branch is not None, "No offline branch found in choose"
        sequence = offline_branch["sequence"]
        notif_actions = [
            a for a in sequence
            if a.get("action") == "persistent_notification.create"
        ]
        assert len(notif_actions) >= 1

    def test_offline_notification_id_is_esp32_offline(self, stale_config):
        choose = stale_config["action"][0]["choose"]
        for branch in choose:
            conditions = branch.get("conditions", [])
            for cond in conditions:
                if cond.get("id") == "offline":
                    sequence = branch["sequence"]
                    for a in sequence:
                        if a.get("action") == "persistent_notification.create":
                            assert a["data"]["notification_id"] == "esp32_offline"
                            return
        pytest.fail("esp32_offline notification not found in offline branch")

    def test_offline_notification_title_contains_offline(self, stale_config):
        choose = stale_config["action"][0]["choose"]
        for branch in choose:
            conditions = branch.get("conditions", [])
            for cond in conditions:
                if cond.get("id") == "offline":
                    sequence = branch["sequence"]
                    for a in sequence:
                        if a.get("action") == "persistent_notification.create":
                            assert "OFFLINE" in a["data"]["title"]
                            return
        pytest.fail("OFFLINE not found in notification title")

    def test_offline_branch_does_not_disable_tou(self, stale_config):
        """Auto-recover redesign: offline must NOT disable the TOU automation.
        The schedule self-pauses via its api_status condition and resumes on
        reconnect."""
        raw = yaml.dump(stale_config)
        assert "automation.turn_off" not in raw, (
            "stale_data.yaml must no longer disable the TOU schedule"
        )


class TestStaleDataOnlineResponse:
    """Online branch (default): notification but NO auto-re-enable."""

    def test_online_default_has_notification(self, stale_config):
        choose_block = stale_config["action"][0]
        default = choose_block.get("default", [])
        assert len(default) > 0, "No default branch in choose"
        notif_actions = [
            a for a in default
            if a.get("action") == "persistent_notification.create"
        ]
        assert len(notif_actions) >= 1

    def test_online_notification_id_is_esp32_online(self, stale_config):
        choose_block = stale_config["action"][0]
        default = choose_block.get("default", [])
        for a in default:
            if a.get("action") == "persistent_notification.create":
                assert a["data"]["notification_id"] == "esp32_online"
                return
        pytest.fail("esp32_online notification not found in default branch")

    def test_online_notification_message_mentions_resumed(self, stale_config):
        choose_block = stale_config["action"][0]
        default = choose_block.get("default", [])
        for a in default:
            if a.get("action") == "persistent_notification.create":
                assert "resumed" in a["data"]["message"].lower()
                return
        pytest.fail("online notification message not found")

    def test_online_default_does_not_contain_turn_on(self, stale_config):
        """Per D-12: TOU must NOT be auto-re-enabled on ESP32 recovery."""
        choose_block = stale_config["action"][0]
        default = choose_block.get("default", [])
        for a in default:
            assert a.get("action") != "automation.turn_on", \
                "automation.turn_on found in default branch -- TOU must NOT be auto-re-enabled"


class TestStaleDataCrossCheck:
    """Auto-recover contract: stale_data no longer disables TOU; the TOU schedule
    gates on ESP32 status itself so it self-pauses and resumes."""

    def test_stale_data_has_no_turn_off(self, stale_config):
        raw = yaml.dump(stale_config)
        assert "automation.turn_off" not in raw, (
            "stale_data.yaml must not disable the TOU schedule"
        )

    def test_tou_gates_on_api_status(self, tou_config):
        conds = yaml.dump(tou_config.get("condition", []))
        assert "binary_sensor.tublemetry_hot_tub_api_status" in conds, (
            "TOU must gate on ESP32 online (this replaces stale_data disabling it)"
        )
