# Phase 1: RS-485 Display Reading - Context

**Gathered:** 2026-03-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Decode the VS300FL4's RS-485 display stream (Pin 5 segment data + Pin 6 digit select) to create a full digital mirror of the topside panel in Home Assistant. Read-only -- no setpoint control or button injection in this phase.

Requirements: DISP-01, DISP-02

</domain>

<decisions>
## Implementation Decisions

### Decode Scope
- Full display mirror -- decode everything the panel shows, not just temperature
- Decode temperature, OH, ICE, filter, heating indicators, lights, all 7-segment states
- Two MAX485 modules on one ESP32 (UART1 + UART2), reading Pin 5 and Pin 6 simultaneously
- ESP32 has 3 hardware UARTs; UART0 for USB logging, UART1 for Pin 5, UART2 for Pin 6

### Architecture (Dumb Decoder)
- ESP32 is a faithful decoder only -- mirrors display state to HA with zero business logic
- All interpretation, filtering, and automation logic lives in HA (template sensors, automations)
- No suppression, no "is this a setpoint flash" logic on the firmware side
- If the display shows it, HA knows it -- no information loss
- Business logic mistakes fixable in HA YAML without reflashing firmware

### HA Entity Design
- Primary: read-only climate entity (`climate.hot_tub`) -- thermostat card showing current_temperature
- Setpoint controls visible but non-functional until Phase 2 enables button injection
- Diagnostic sensors exposed alongside: raw hex bytes, display state, individual digit values, decode confidence, last update timestamp
- Report both assembled display string ("104", "OH", "--") and per-digit breakdown as attributes
- Update HA on change only -- ESP32 decodes every frame internally (~60Hz), only pushes when value changes
- Entity name: "Hot Tub" -> `climate.hot_tub`

### Edge State Behavior
- Non-temperature displays (OH, ICE, startup "--", setpoint flash): keep last known temperature as current_temperature, set display_state attribute to describe what's actually showing
- Setpoint flashes during button presses: reported faithfully (dumb decoder principle), HA decides what to do with them
- No gaps in temperature history graphs -- last valid reading persists

### Claude's Discretion
- Specific GPIO pin assignments for UART1/UART2
- ESPHome component structure (custom component vs. external component vs. lambda)
- Diagnostic sensor naming conventions
- Frame parsing implementation details

</decisions>

<specifics>
## Specific Ideas

- "Having an exact mirror of the display is one of the only ways to accurately know what's going on"
- "The more business logic we put in the ESP32 layer, the less would be known at HA, and the more likely we miss something because of a mismatch"
- Dumb decoder principle is the core architectural decision -- ESP32 is a transparent bridge between the tub's display bus and HA

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `485/scripts/bruteforce_7seg.py`, `bruteforce_7seg_v2.py`, `bruteforce_3digit.py`: 7-segment brute-force analysis scripts -- methodology can inform the decode lookup table
- `485/scripts/decode_7seg.py`, `decode_oh.py`, `decode_csv.py`: Existing decode scripts for reference
- `485/scripts/rs485_capture.py`: Interactive capture script with button markers -- basis for the ladder capture script
- `485/scripts/analyze_protocol.py`: Protocol analysis script

### Established Patterns
- GS510SZ reference mapping confirmed: 0x30="1" and 0x70="7" match captured data -- MagnusPer/Balboa-GS510SZ is closest reference for synchronous clock+data protocol
- Pin 5 idle frame: `FE 06 70 XX 00 06 70 00` (8-byte, byte 3 varies with temp)
- Pin 6 refresh stream: `77 E6 E6` repeating at 60Hz (digit select/multiplexing)
- FE byte encodes status (present during idle, absent during lights toggle)
- 72 candidate 7-segment solutions identified across three temp pairs

### Integration Points
- ESPHome YAML config -> Home Assistant native API (local, no MQTT needed)
- Two MAX485 modules -> ESP32 UART1 (Pin 5) + UART2 (Pin 6)
- RJ45 screw terminal breakout (ordered) provides clean pin access

</code_context>

<capture_plan>
## Temperature Ladder Capture Plan

### Goal
Full protocol capture at every temperature the tub supports, plus all triggerable display states.

### Method
Logic analyzer (8-channel, Lonely Binary) on all RJ45 pins, stepping through temperatures.

### Sequence
1. Temperature sweep: 104 -> 80 (25 steps via Temp Down)
   - At each step: 2-3s stable frames, press button, record full transition (~5s), wait for new temp to stabilize, record 2-3s new stable frames
2. Lights toggle: on/off cycle
3. Jets toggle: on/off cycle
4. Wait for filter cycle indicator (if visible on display)

### Known Blocker
Line loading: previous T-splitter + analyzer tap caused display corruption on Pin 6 ("80" flashing). Must solve high-impedance tapping before capture session. Researcher should investigate:
- MAX485 input impedance characteristics (read-only, RO pin)
- Buffer IC options for non-invasive tap
- Whether new RJ45 screw terminal breakouts improve the situation

### Known Gaps (not safely triggerable)
- OH (overheat) frame pattern
- ICE (freeze protection) frame pattern
- Startup "--" pattern (would require power cycling the board)

### Output
- PulseView .sr files per temperature step
- Annotated CSV: timestamp, displayed temp, steady-state frame bytes (Pin 5 + Pin 6)
- Transition frame recordings between each step

</capture_plan>

<deferred>
## Deferred Ideas

None -- discussion stayed within phase scope.

</deferred>

---

*Phase: 01-rs485-display-reading*
*Context gathered: 2026-03-13*
