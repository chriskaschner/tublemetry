"""Tests for stale data gating HA automation YAML.

Validates that ha/stale_data.yaml has correct structure for ESP32 offline
detection and TOU gating per SAFE-03 (D-09 through D-12).

When ESP32 goes offline:
- TOU schedule is disabled
- User is notified via persistent notification

When ESP32 comes back online:
- User is notified
- TOU is NOT auto-re-enabled (user must verify state first, per D-12)
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
    """Offline branch: choose block with notification and TOU disable."""

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

    def test_offline_branch_disables_tou(self, stale_config):
        choose = stale_config["action"][0]["choose"]
        for branch in choose:
            conditions = branch.get("conditions", [])
            for cond in conditions:
                if cond.get("id") == "offline":
                    sequence = branch["sequence"]
                    turn_off_actions = [
                        a for a in sequence
                        if a.get("action") == "automation.turn_off"
                    ]
                    assert len(turn_off_actions) >= 1
                    # Verify it targets the TOU automation
                    target = turn_off_actions[0].get("target", {})
                    assert target.get("entity_id") == "automation.hot_tub_tou_schedule"
                    return
        pytest.fail("automation.turn_off not found in offline branch")


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

    def test_online_notification_message_contains_not(self, stale_config):
        choose_block = stale_config["action"][0]
        default = choose_block.get("default", [])
        for a in default:
            if a.get("action") == "persistent_notification.create":
                assert "NOT" in a["data"]["message"]
                return
        pytest.fail("NOT not found in online notification message")

    def test_online_default_does_not_contain_turn_on(self, stale_config):
        """Per D-12: TOU must NOT be auto-re-enabled on ESP32 recovery."""
        choose_block = stale_config["action"][0]
        default = choose_block.get("default", [])
        for a in default:
            assert a.get("action") != "automation.turn_on", \
                "automation.turn_on found in default branch -- TOU must NOT be auto-re-enabled"


class TestStaleDataCrossCheck:
    """Cross-check: TOU entity ID matches TOU automation alias."""

    def test_tou_entity_matches_automation_alias(self, stale_config, tou_config):
        """The entity_id used in stale_data.yaml should correspond to the TOU alias."""
        # TOU automation alias is "Hot Tub TOU Schedule"
        # HA converts this to automation.hot_tub_tou_schedule
        tou_alias = tou_config["alias"]
        expected_entity = "automation." + tou_alias.lower().replace(" ", "_")

        # Find the turn_off target in the offline branch
        choose = stale_config["action"][0]["choose"]
        for branch in choose:
            conditions = branch.get("conditions", [])
            for cond in conditions:
                if cond.get("id") == "offline":
                    sequence = branch["sequence"]
                    for a in sequence:
                        if a.get("action") == "automation.turn_off":
                            target = a.get("target", {})
                            assert target.get("entity_id") == expected_entity
                            return
        pytest.fail("Could not find automation.turn_off in offline branch for cross-check")
