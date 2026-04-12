---
phase: 05-safety-and-power-validation
plan: 02
subsystem: safety-automations
tags: [stale-data, esp32-offline, tou-gating, safety]
dependency_graph:
  requires: []
  provides: [ha/stale_data.yaml, tests/test_stale_data.py]
  affects: [automation.hot_tub_tou_schedule]
tech_stack:
  added: []
  patterns: [state-trigger-choose, persistent-notification-gating, trigger-id-branching]
key_files:
  created:
    - ha/stale_data.yaml
    - tests/test_stale_data.py
  modified: []
decisions:
  - "Online trigger uses default branch (not explicit condition) for cleaner YAML"
  - "Both off and unavailable states share trigger id 'offline' for single choose branch"
  - "No re-enable grace period -- user must manually re-enable TOU after verifying state (D-12)"
metrics:
  duration: 92s
  completed: "2026-04-12T19:49:04Z"
  tasks: 1
  tests_added: 19
  tests_total: 436
---

# Phase 05 Plan 02: Stale Data Gating Summary

ESP32 offline detection automation that disables TOU and notifies on disconnect, notifies but does NOT auto-re-enable TOU on reconnect, with 19 structural validation tests.

## Task Results

| Task | Name | Commit(s) | Files | Tests |
|------|------|-----------|-------|-------|
| 1 | Stale data gating automation (SAFE-03) | b994b11 (RED), ad36922 (GREEN) | ha/stale_data.yaml, tests/test_stale_data.py | 19 pass |

## Implementation Details

### ha/stale_data.yaml

Three state triggers on `binary_sensor.tublemetry_hot_tub_api_status`:
- `to: "off"` (id: offline) -- clean ESP32 disconnect
- `to: "unavailable"` (id: offline) -- network failure / HA can't reach ESP32
- `to: "on"` (id: online) -- ESP32 reconnected

Offline response (choose branch):
1. `system_log.write` -- warning-level log entry
2. `persistent_notification.create` -- notification_id `esp32_offline`, title contains "OFFLINE"
3. `automation.turn_off` -- disables `automation.hot_tub_tou_schedule`

Online response (default branch):
1. `system_log.write` -- info-level log entry
2. `persistent_notification.create` -- notification_id `esp32_online`, message explicitly states TOU was "NOT auto-re-enabled"

Key safety property: TOU is never auto-re-enabled. User must manually verify hot tub state and re-enable TOU after any connectivity gap.

### tests/test_stale_data.py

Five test classes, 19 tests total:
- `TestStaleDataYaml` (3 tests): valid YAML, alias contains "Offline", mode is single
- `TestStaleDataTriggers` (6 tests): 3 triggers, all reference api_status entity, correct trigger IDs
- `TestStaleDataOfflineResponse` (5 tests): choose block, notification with esp32_offline ID, title contains OFFLINE, TOU disable targeting correct entity
- `TestStaleDataOnlineResponse` (4 tests): default branch notification with esp32_online ID, message contains NOT, no automation.turn_on present
- `TestStaleDataCrossCheck` (1 test): TOU entity ID matches TOU automation alias

## Threat Mitigations

| Threat ID | Disposition | Implementation |
|-----------|-------------|----------------|
| T-05-05 | mitigated | Both "off" and "unavailable" states trigger offline response -- covers clean disconnect and network failure |
| T-05-06 | mitigated | Online response explicitly does NOT re-enable TOU; user must manually verify and re-enable |

## Deviations from Plan

None -- plan executed exactly as written.

## Verification

```
uv run pytest tests/test_stale_data.py -x    -- 19 passed
uv run pytest tests/ --ignore=tests/test_ladder_capture.py  -- 436 passed
```

## Self-Check: PASSED

- ha/stale_data.yaml: FOUND
- tests/test_stale_data.py: FOUND
- 05-02-SUMMARY.md: FOUND
- b994b11 (RED commit): FOUND
- ad36922 (GREEN commit): FOUND
