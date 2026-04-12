---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: Closed-Loop Trust
status: defining_requirements
stopped_at: Milestone v2.0 started -- defining requirements
last_updated: "2026-04-12"
last_activity: 2026-04-12
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-12)

**Core value:** The tub automatically lowers its setpoint during on-peak hours and raises it before evening use -- no human involvement required.
**Current focus:** Milestone v2.0 -- Closed-Loop Trust

## Current Position

Phase: Not started (defining requirements)
Plan: --
Status: Defining requirements
Last activity: 2026-04-12 -- Milestone v2.0 started

## Accumulated Context

### Decisions

- [v1.0 Phase 01]: 0x73="9" on VS300FL4 (NOT 0x7B as GS510SZ -- no bottom segment d).
- [v1.0 Phase 01]: Dp bit (bit 7) masked before lookup.
- [v1.0 Phase 01]: Dumb decoder principle: DisplayState reports display content faithfully, zero business logic on firmware side.
- [v1.0 Phase 01]: Frame boundary detection uses micros() gap > 500us. Min pulse 10us for noise rejection.
- [v1.0 Phase 02]: Number entity over climate entity (climate forces F->C->F conversion).
- [v1.0 Phase 02]: probe+cache over always-rehome -- delta presses only.
- [v2.0 pre-work]: Auto-refresh keepalive removed -- caused setpoint drift from lost presses.
- [v2.0 pre-work]: Thermal runaway automation deployed -- 2F threshold, 5 min sustain, disables TOU and drops to floor.
- [v2.0 pre-work]: Heater status bit may not be trustworthy -- user observed heating at 80F setpoint with heater status "off".
- [v2.0 pre-work]: Enphase power monitoring in HA can serve as independent heater ground truth (4kW spike = heater on).

### Pending Todos

None.

### Blockers/Concerns

- Button press reliability from HA: sometimes requires 2-3 attempts to register on physical display.
- HA SQLite DB only accessible on RPi -- blocks thermal model iteration from dev machine.
- Heater status bit accuracy unknown -- need independent validation via power monitoring.

## Session Continuity

Last session: 2026-04-12
Stopped at: Milestone v2.0 started -- defining requirements
Resume file: None
