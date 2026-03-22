# S03: Button Injection + Closed-Loop Control

**Goal:** Home Assistant climate entity controls hot tub temperature via photorelay button injection, with closed-loop verification from the display stream.
**Demo:** User sets target temperature in HA → ESP32 executes re-home sequence (slam to 80F floor, count up to target) → display stream confirms new setpoint → climate entity shows both current and target temperature.

## Must-Haves

- GPIO output control for Temp Up and Temp Down photorelays (AQY212EH)
- Re-home algorithm: 25 presses to floor (80F), then count up to target
- Climate entity `control()` accepts setpoint and triggers button sequence
- Closed-loop verification: display stream confirms setpoint reached
- Safety clamp: 80-104F range enforced in firmware
- Button press timing parameters (press duration, inter-press delay) configurable
- State machine prevents concurrent button sequences
- Diagnostic logging of every button press and sequence outcome

## Proof Level

- This slice proves: integration (firmware logic complete, hardware verification deferred to installation)
- Real runtime required: yes (at installation — bench testing proves compile + boot + state machine logic)
- Human/UAT required: yes (physical tub needed for closed-loop verification)

## Verification

- `uv run pytest` — all existing tests pass + new button injection tests
- `tests/test_button_injection.py` — re-home algorithm, safety clamps, state machine, timing
- `uv run esphome config esphome/tublemetry.yaml` — YAML validates clean
- `uv run esphome compile esphome/tublemetry.yaml` — firmware compiles clean
- Serial boot log shows "Button injection ready" and GPIO pin numbers

## Observability / Diagnostics

- Runtime signals: log each button press (direction, count, sequence phase), sequence start/complete/abort
- Inspection surfaces: HA text sensor for injection state (idle/rehoming/adjusting/verifying), HA sensor for last sequence result
- Failure visibility: last error reason (timeout, display mismatch, sequence aborted), retry count, phase at failure
- Redaction constraints: none

## Integration Closure

- Upstream surfaces consumed: `TublemetryDisplay` (display stream reading, current temperature), `TublemetryClimate` (climate entity shell)
- New wiring introduced: `TublemetryClimate::control()` now triggers button sequences via `ButtonInjector`, GPIO outputs added to YAML
- What remains before the milestone is truly usable end-to-end: physical installation, real display stream verification, photorelay wiring confirmation

## Tasks

- [x] **T01: ButtonInjector C++ class with re-home algorithm** `est:45m`
  - Why: Core logic for simulating button presses via GPIO and executing the re-home strategy. This is pure firmware logic, fully testable at compile level.
  - Files: `esphome/components/tublemetry_display/button_injector.h`, `esphome/components/tublemetry_display/button_injector.cpp`
  - Do:
    - Create `ButtonInjector` class with GPIO pin setters for temp_up and temp_down
    - Implement non-blocking state machine: IDLE → REHOMING → ADJUSTING → VERIFYING → IDLE
    - Re-home phase: fire temp_down 25x with configurable press duration (200ms default) and inter-press delay (300ms default)
    - Adjust phase: fire temp_up N times where N = (target - 80)
    - Verify phase: wait for display stream to show expected temperature (timeout 10s)
    - `request_temperature(float target)` entry point — validates range, starts sequence
    - `loop()` method drives state machine (non-blocking, called from TublemetryDisplay::loop)
    - Safety: clamp target to 80-104F, reject if sequence already in progress
    - Log every press and state transition at INFO level
    - Track diagnostic state: phase, press count, target, last error, start time
  - Verify: `uv run esphome compile esphome/tublemetry.yaml` compiles clean
  - Done when: ButtonInjector class compiles with complete state machine, re-home algorithm, and safety clamps

- [x] **T02: Wire ButtonInjector into climate entity and YAML config** `est:30m`
  - Why: Connect the button injector to the existing climate entity so HA setpoint changes trigger button sequences, and add GPIO output pins to YAML.
  - Files: `esphome/components/tublemetry_display/tublemetry_display.h`, `esphome/components/tublemetry_display/tublemetry_display.cpp`, `esphome/components/tublemetry_display/__init__.py`, `esphome/components/tublemetry_display/climate.py`, `esphome/tublemetry.yaml`
  - Do:
    - Add `ButtonInjector` pointer to `TublemetryDisplay`, with setter
    - Add `set_button_injector()` to `TublemetryClimate` — climate control() delegates to injector
    - Update `TublemetryClimate::control()` to call `injector->request_temperature(target)`
    - Update climate traits to include target temperature support (not just read-only)
    - Add `temp_up_pin` and `temp_down_pin` config keys in `__init__.py` (optional — component works read-only without them)
    - Call `injector->loop()` from `TublemetryDisplay::loop()`
    - Feed display temperature updates to injector for closed-loop verification
    - Add GPIO output pins to `tublemetry.yaml` (GPIO18 temp_up, GPIO19 temp_down — TBD based on wiring)
    - Add diagnostic text sensor for injection state
  - Verify: `uv run esphome config esphome/tublemetry.yaml && uv run esphome compile esphome/tublemetry.yaml`
  - Done when: Climate entity accepts setpoint, YAML validates and compiles, injector wired into display loop

- [x] **T03: Python tests for button injection logic** `est:30m`
  - Why: Test the re-home algorithm, safety clamps, state machine transitions, and timing logic in Python (mirroring the C++ logic, same pattern as test_mock_frames.py).
  - Files: `tests/test_button_injection.py`
  - Do:
    - Test re-home calculation: target 95 → 25 down-presses + 15 up-presses
    - Test safety clamp: reject targets outside 80-104F
    - Test edge cases: target exactly 80 (0 up-presses), target exactly 104 (24 up-presses)
    - Test concurrent rejection: second request while sequence in progress returns error
    - Test state machine transitions: IDLE→REHOMING→ADJUSTING→VERIFYING→IDLE
    - Test timing: press duration and inter-press delay defaults
    - Test YAML config: new GPIO pins and injection-related sensors present
  - Verify: `uv run pytest tests/test_button_injection.py -v`
  - Done when: All button injection tests pass, covering algorithm, safety, state machine, and config

- [x] **T04: Flash firmware and verify clean boot** `est:15m`
  - Why: Confirm the full firmware (display reading + button injection) boots without crashes on the real ESP32 while still on the bench.
  - Files: (no new files — serial verification only)
  - Do:
    - Compile and flash via serial: `uv run esphome run esphome/tublemetry.yaml --device /dev/cu.usbserial-*`
    - Monitor serial output for boot sequence
    - Confirm: "Clock interrupt attached, waiting for frames..."
    - Confirm: "Button injection ready" with correct GPIO pin numbers
    - Confirm: no crash loops, no watchdog resets
    - Confirm: WiFi connects (if available) and HA entities appear
    - Confirm: climate entity shows in HA with target temperature slider (if HA connected)
  - Verify: Serial log shows clean boot with both display decoder and button injector initialized
  - Done when: ESP32 boots cleanly with full firmware, no crashes after 60 seconds

## Files Likely Touched

- `esphome/components/tublemetry_display/button_injector.h` (new)
- `esphome/components/tublemetry_display/button_injector.cpp` (new)
- `esphome/components/tublemetry_display/tublemetry_display.h` (modified)
- `esphome/components/tublemetry_display/tublemetry_display.cpp` (modified)
- `esphome/components/tublemetry_display/__init__.py` (modified)
- `esphome/components/tublemetry_display/climate.py` (modified)
- `esphome/tublemetry.yaml` (modified)
- `tests/test_button_injection.py` (new)
