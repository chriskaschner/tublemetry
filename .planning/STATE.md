# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-13)

**Core value:** The tub automatically lowers its setpoint during on-peak hours and raises it before evening use -- no human involvement required.
**Current focus:** Phase 1: RS-485 Display Reading

## Current Position

Phase: 1 of 2 (RS-485 Display Reading)
Plan: 0 of 2 in current phase
Status: Ready to plan
Last activity: 2026-03-13 -- Roadmap revised, phases reordered (display reading first, button injection second)

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**
- Total plans completed: 0
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**
- Last 5 plans: -
- Trend: -

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap revision]: Reversed phase order -- display reading first (Phase 1), button injection second (Phase 2). Reading the display is independently valuable (temp monitoring in HA) and makes Phase 2 closed-loop from day one.
- [Roadmap revision]: DISP-03 (drift correction) moved to Phase 2 because it requires both reading AND writing.
- [Roadmap revision]: ENRG-01 (energy tracking) stays in Phase 2 because it benefits from both paths.
- [Roadmap]: Temperature ladder capture folded into Phase 1 as prerequisite task (resolves 72-solution 7-segment encoding ambiguity).

### Pending Todos

None yet.

### Blockers/Concerns

- Parts on AliExpress (2-4 week lead time). Temperature ladder capture and display decoding firmware can begin now with existing MAX485 boards.
- Temperature ladder capture (physical tub access + RS-485 adapter) is the critical first task in Phase 1 -- unblocks all display decoding work.
- RJ45 splitter interference and loose cable ends observed during initial testing -- photorelay isolation should resolve in Phase 2, but must verify.

## Session Continuity

Last session: 2026-03-13
Stopped at: Roadmap revised, ready to plan Phase 1
Resume file: .planning/phases/01-button-injection-mvp/.continue-here.md
