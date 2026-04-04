---
id: T01
parent: S01
milestone: M002
provides: []
requires: []
affects: []
key_files: ["esphome/components/tublemetry_display/tublemetry_display.h", "esphome/components/tublemetry_display/tublemetry_display.cpp"]
key_decisions: ["Checksum gate placed before digit decode to skip decode work on corrupt frames", "Scoped block used for p1 variable in checksum gate to keep it self-contained", "stable_count_ saturates at 255 to prevent uint8_t wraparound on long-stable display", "Symlinked root secrets.yaml into worktree for compilation (gitignored, absent in worktree)"]
patterns_established: []
drill_down_paths: []
observability_surfaces: []
duration: ""
verification_result: "Ran `/Users/chriskaschner/Documents/GitHub/tubtron/.venv/bin/esphome compile esphome/tublemetry.yaml` — completed in 59.55s with [SUCCESS] and 'Successfully compiled program.' Flash usage 51.3% (940943/1835008 bytes)."
completed_at: 2026-04-04T13:35:38.417Z
blocker_discovered: false
---

# T01: Added checksum gate (CHECKSUM_MASK=0x4B on p1, bit0 on status) and 3-frame stability filter to process_frame_(); firmware compiles clean

> Added checksum gate (CHECKSUM_MASK=0x4B on p1, bit0 on status) and 3-frame stability filter to process_frame_(); firmware compiles clean

## What Happened
---
id: T01
parent: S01
milestone: M002
key_files:
  - esphome/components/tublemetry_display/tublemetry_display.h
  - esphome/components/tublemetry_display/tublemetry_display.cpp
key_decisions:
  - Checksum gate placed before digit decode to skip decode work on corrupt frames
  - Scoped block used for p1 variable in checksum gate to keep it self-contained
  - stable_count_ saturates at 255 to prevent uint8_t wraparound on long-stable display
  - Symlinked root secrets.yaml into worktree for compilation (gitignored, absent in worktree)
duration: ""
verification_result: passed
completed_at: 2026-04-04T13:35:38.419Z
blocker_discovered: false
---

# T01: Added checksum gate (CHECKSUM_MASK=0x4B on p1, bit0 on status) and 3-frame stability filter to process_frame_(); firmware compiles clean

**Added checksum gate (CHECKSUM_MASK=0x4B on p1, bit0 on status) and 3-frame stability filter to process_frame_(); firmware compiles clean**

## What Happened

Added three new members to TublemetryDisplay header: candidate_display_string_, stable_count_{0}, and STABLE_THRESHOLD=3. In process_frame_(): replaced the commented-out status extraction with the real one, added a checksum gate block checking p1 reserved bits via mask 0x4B and p4 bit 0, then added the stability filter after the partial-frame drop. Frames failing either check return early with appropriate log output. Needed to symlink secrets.yaml from project root into worktree and use venv esphome binary directly (not available via uv run in this environment).

## Verification

Ran `/Users/chriskaschner/Documents/GitHub/tubtron/.venv/bin/esphome compile esphome/tublemetry.yaml` — completed in 59.55s with [SUCCESS] and 'Successfully compiled program.' Flash usage 51.3% (940943/1835008 bytes).

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `/Users/chriskaschner/Documents/GitHub/tubtron/.venv/bin/esphome compile esphome/tublemetry.yaml 2>&1 | tail -20` | 0 | ✅ pass | 65400ms |


## Deviations

Used scoped block for p1 variable (minor style choice). Used venv esphome binary directly instead of `uv run esphome` — uv cannot find esphome in this environment. Symlinked secrets.yaml from project root into worktree esphome/ directory.

## Known Issues

None.

## Files Created/Modified

- `esphome/components/tublemetry_display/tublemetry_display.h`
- `esphome/components/tublemetry_display/tublemetry_display.cpp`


## Deviations
Used scoped block for p1 variable (minor style choice). Used venv esphome binary directly instead of `uv run esphome` — uv cannot find esphome in this environment. Symlinked secrets.yaml from project root into worktree esphome/ directory.

## Known Issues
None.
