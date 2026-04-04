---
id: S01
parent: M002
milestone: M002
provides:
  - Checksum-validated frame stream: process_frame_() rejects structurally corrupt frames before any decode work
  - Stability-filtered publish gate: only values stable for 3 consecutive frames reach HA sensors
  - candidate_display_string_ and stable_count_ members available for S02 setpoint detection logic
  - 25 frame integrity tests establishing the Python mirror pattern for C++ logic verification
requires:
  []
affects:
  - S02 — stability filter state (candidate_display_string_, stable_count_) is directly visible; setpoint detection builds on the same pattern
key_files:
  - esphome/components/tublemetry_display/tublemetry_display.h
  - esphome/components/tublemetry_display/tublemetry_display.cpp
  - tests/test_frame_integrity.py
key_decisions:
  - Checksum gate placed before digit decode loop to skip decode work on corrupt frames
  - Scoped block for p1 variable keeps checksum gate self-contained without polluting function scope
  - stable_count_ saturates at 255 to prevent uint8_t wraparound on long-stable display
  - ESPHome worktree compile: symlink secrets.yaml + use venv binary directly (uv run does not resolve esphome in worktrees)
  - TestChecksumRealFrames added to verify checksum is structurally compatible with actual captured wire data
patterns_established:
  - Checksum gate pattern: extract reserved bits with mask, early return on mismatch — applied before decode work to avoid wasted effort
  - Stability filter pattern: candidate + saturating counter + threshold — reusable for setpoint detection in S02
  - Python mirroring pattern for C++ logic: implement identical constants and functions in test file, verify against real captured frame values — enables fast regression testing without ESP32
observability_surfaces:
  - ESP_LOGW for checksum failures (p1 and p4 values logged)
  - ESP_LOGD for stability hold (current count, threshold, and display string logged)
drill_down_paths:
  - milestones/M002/slices/S01/tasks/T01-SUMMARY.md
  - milestones/M002/slices/S01/tasks/T02-SUMMARY.md
duration: ""
verification_result: passed
completed_at: 2026-04-04T13:39:50.036Z
blocker_discovered: false
---

# S01: Frame Integrity — Checksum + Stability Filter

**Added checksum gate (CHECKSUM_MASK=0x4B) and 3-frame stability filter to process_frame_(); 274 tests pass, firmware compiles clean.**

## What Happened

Two tasks, no blockers. T01 modified tublemetry_display.h and tublemetry_display.cpp to add three new class members (candidate_display_string_, stable_count_{0}, STABLE_THRESHOLD=3) and two new gates in process_frame_(). The checksum gate (placed before digit decode for efficiency) checks p1 reserved bits via CHECKSUM_MASK=0x4B and p4 bit 0; corrupt frames are logged at WARN and dropped. The stability filter (placed after partial-frame drop) tracks the last candidate and a consecutive-match count — frames below STABLE_THRESHOLD are logged at DEBUG and held. stable_count_ saturates at 255 to prevent uint8_t wraparound on long-stable displays. T01 needed two environment workarounds: symlink secrets.yaml from project root into the worktree esphome/ directory, and invoke the venv esphome binary directly rather than via `uv run`. Firmware compiled in 59.55s at SUCCESS with 51.3% flash utilization. T02 created tests/test_frame_integrity.py with 25 tests (4 classes: TestChecksumValid, TestChecksumRejects, TestChecksumRealFrames, TestStabilityFilter) mirroring the C++ logic in Python. The TestChecksumRealFrames class went beyond the plan spec to verify known captured frames (105°F, 104°F, 80°F, economy mode, blank) all pass the gate — confirming the checksum is structurally compatible with real wire data. Full suite: 274/274 pass, zero regressions.

## Verification

Slice-level verification run immediately before summary: `uv run pytest tests/ --ignore=tests/test_ladder_capture.py -v` → 274 passed in 0.34s. ESPHome compile (via .venv/bin/esphome compile esphome/tublemetry.yaml) → [SUCCESS], flash 51.3%. Code inspection confirmed: checksum gate placed before decode loop, stability filter placed after partial-frame drop, STABLE_THRESHOLD=3 matches D002, saturating counter prevents overflow.

## Requirements Advanced

None.

## Requirements Validated

- R001 — C++ gate implemented with CHECKSUM_MASK=0x4B; 11 tests verify rejection of structurally invalid frames (0x7E hundreds, startup dashes, p4 bit0 set) and passage of known good captured frames. Firmware compiles clean.
- R002 — STABLE_THRESHOLD=3 implemented; 10 StabilityFilter tests verify 3-frame requirement, streak reset, saturation at 255, and independence. 274/274 pass.
- R010 — uv run pytest tests/ --ignore=tests/test_ladder_capture.py → 274 passed in 0.34s, zero regressions.
- R011 — .venv/bin/esphome compile esphome/tublemetry.yaml → [SUCCESS] in 59.55s, flash 51.3%.

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Deviations

T01: Used scoped block `{ uint8_t p1 = ...; }` for the checksum gate variable (minor style choice to avoid collision with future code). Used venv esphome binary directly and symlinked secrets.yaml — both required by worktree environment. T02: Added TestChecksumRealFrames class and extra edge-case tests (bit3/bit1 rejection, 4th-frame still publishes, alternating strings, blank+temp pattern) — 25 tests vs 12 minimum in plan.

## Known Limitations

Checksum gate is a structural filter only — it cannot detect corruption in the actual segment data bits (p2, p3). That would require a full CRC, which the VS300FL4 protocol doesn't provide. The gate catches structurally malformed frames; content corruption is handled downstream by partial-frame drop and stability filter.

## Follow-ups

S02 will need to build on the stability filter state machine — the candidate_display_string_ and stable_count_ members will be visible to the setpoint detection logic being added in S02.

## Files Created/Modified

- `esphome/components/tublemetry_display/tublemetry_display.h` — Added candidate_display_string_, stable_count_{0}, STABLE_THRESHOLD=3 to protected section
- `esphome/components/tublemetry_display/tublemetry_display.cpp` — Added checksum gate (before decode loop) and stability filter (after partial-frame drop) to process_frame_()
- `tests/test_frame_integrity.py` — New: 25 tests mirroring C++ checksum gate and stability filter logic in Python
