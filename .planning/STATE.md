---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: in_progress
stopped_at: "Full button injection hardware validated. Full re-home sequence + TOU automation next."
last_updated: "2026-03-26T14:30:00Z"
last_activity: 2026-03-26 -- Hardware validated end-to-end (display reading + button injection both directions), pin swap fixed, 0x34 lookup added, test buttons in HA, 203 tests passing
progress:
  total_phases: 2
  completed_phases: 1
  total_plans: 3
  completed_plans: 3
  percent: 75
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-13)

**Core value:** The tub automatically lowers its setpoint during on-peak hours and raises it before evening use -- no human involvement required.
**Current focus:** Hardware fully validated. Next: full re-home sequence test, then TOU automation in HA.

## Current Position

Phase: 1 of 2 (Button Injection MVP) -- hardware validated, full sequence + HA automation remain
Plan: 3 of 3 in current phase -- ALL PLANS COMPLETE (hardware validation done ad-hoc this session)
Status: Display reading live, button injection confirmed both directions, test buttons in HA diagnostic section.
Last activity: 2026-03-26 -- Pin swap fixed (GPIO18=down, GPIO19=up), 0x34="1" added, test buttons validated, 203 tests pass

Progress: [███████░░░] 75%

## Performance Metrics

**Velocity:**
- Total plans completed: 3
- Average duration: 5min
- Total execution time: 14min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 3/3 | 14min | 5min |

*Updated after each plan completion*

## Accumulated Context

### Decisions

- [Roadmap revision]: Reversed phase order -- display reading first, button injection second.
- [01-01]: 0x73="9" on VS300FL4 (NOT 0x7B as GS510SZ -- no bottom segment d).
- [01-01]: Dp bit (bit 7) masked before lookup.
- [01-01]: Dumb decoder principle: DisplayState reports display content faithfully, zero business logic on firmware side.
- [01-02]: Frame boundary detection uses micros() gap > 500us. Min pulse 10us for noise rejection.
- [01-02]: ESPHome compile verified -- deprecated APIs fixed (CLIMATE_SCHEMA, ClimateTraits, platform/board).
- [01-02]: Timestamp sensor uses millis() uptime.
- [Hardware validation 2026-03-26]: GPIO18=temp_down, GPIO19=temp_up (swapped from original wiring assumption -- confirmed via test press).
- [Hardware validation 2026-03-26]: 0x34="1" in setpoint display mode (Balboa briefly shows setpoint after button press using different segment pattern for "1").
- [Hardware validation 2026-03-26]: Partial frames dropped silently (unknown bytes -> LOGV, early return if any '?' digit).
- [Hardware validation 2026-03-26]: Confidence sensor publish-on-change only (last_confidence_ tracking added).
- [Hardware validation 2026-03-26]: TEST_PRESS phase added for single raw press (bypasses re-home, for hardware debug).
- [Hardware validation 2026-03-26]: Restart/SafeMode buttons moved to entity_category=diagnostic in HA.

### Pending Todos

None.

### Blockers/Concerns

- Setpoint display frames decoded as current temp (Balboa shows setpoint ~1s after button press -- no way to distinguish from raw 7-seg data). Not blocking for TOU automation.
- ISR can flood WiFi if clock pin gets noise -- pulldowns help. Serial flash required if OTA fails.

## Session Continuity

Last session: 2026-03-26T14:30:00Z
Stopped at: Hardware validated, saving context before /clear
Resume file: .planning/phases/01-button-injection-mvp/.continue-here.md
