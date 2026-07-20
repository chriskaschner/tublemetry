# Setpoint Injection Undershoot — Root Cause Investigation

Date: 2026-07-19
Scope: investigation and proposed fix ONLY. No firmware was reflashed, no live HA
was changed, no device was touched, and no source files were modified. All code
changes below are proposals presented as diffs.

Firmware under investigation: `tublemetry_display` component v0.2.0 (built 2026-04-12).

## Symptom

- HA commands `number.tublemetry_hot_tub_setpoint = 102`.
- The physical Balboa panel lands on 101 (one degree short).
- `sensor.tublemetry_hot_tub_detected_setpoint` reads 101.
- `sensor.tublemetry_hot_tub_last_command_result` reads `success`.
- `sensor.tublemetry_hot_tub_injection_phase` returns to `idle`.
- Re-driving from the known baseline (command 101, which already matches the
  panel, then command 102) STILL leaves the panel at 101.

Two independent defects combine to produce this: (1) a real one-degree undershoot,
and (2) a verification bug that reports `success` even though the panel never
reached the target.

---

## How the injection logic works (as built)

Entry point when HA writes the setpoint number:

- `TublemetrySetpoint::control()` -> `ButtonInjector::request_temperature(target)`
  (`esphome/components/tublemetry_display/tublemetry_setpoint.cpp:9-29`).

`request_temperature()` has two paths
(`esphome/components/tublemetry_display/button_injector.cpp:90-102`):

- Known-setpoint fast path: if `known_setpoint_` is not NAN, go straight to
  `start_adjusting_(known_setpoint_)` — no probe.
- Probe path: if `known_setpoint_` is NAN, enter `PROBING` (one down press to
  reveal the current setpoint from the display), then adjust.

`known_setpoint_` is populated frequently, so the fast path is the common path:

- On every successful sequence: `finish_sequence_()` sets
  `known_setpoint_ = target_temp_` (`button_injector.cpp:500`).
- Passively, whenever the decoder confirms a setpoint from the display:
  `set_known_setpoint(detected_setpoint_)`
  (`esphome/components/tublemetry_display/tublemetry_display.cpp:407`).

The press count is computed in `start_adjusting_()`
(`button_injector.cpp:151-174`):

```cpp
int delta = round(target_temp_) - round(from_setpoint);   // line 152
...
uint8_t abs_delta = std::abs(delta);                       // line 161
this->press_budget_ = abs_delta + 2;   // D-06: N+2 budget    line 162
...
this->presses_remaining_ = abs_delta;  // EXACTLY abs(delta)   line 166
this->presses_total_ = presses_remaining_;                 // line 167
```

So the `ADJUSTING` phase fires exactly `abs(target - from_setpoint)` presses.
There is no accounting anywhere for a display wake press (grep for
`wake|first press|n+1|dummy press` across the component returns nothing relevant —
the only "first press" comments are for the unrelated `REFRESHING` net-zero
sequence).

After the presses, `VERIFYING` decides success/failure
(`button_injector.cpp:290-308`):

```cpp
if (!std::isnan(last_display_temp_) &&
    last_display_temp_ == target_temp_) {      // lines 294-295
  finish_sequence_(InjectorResult::SUCCESS);
  return;
}
```

`last_display_temp_` is fed for EVERY numeric display frame, unconditionally,
BEFORE the set-mode branch (`tublemetry_display.cpp:366-369`):

```cpp
// Feed raw value to button injector for closed-loop verification
if (this->injector_ != nullptr) {
  this->injector_->feed_display_temperature(temp);   // fed for water temp AND setpoint flashes
}
```

---

## Balboa GL/ML wake-press behavior (confirmed)

The wake-press hypothesis is CONFIRMED by three independent sources.

1. Balboa's own user documentation: the first press of a temperature button
   "wakes up" the display and reveals the current Set Temperature WITHOUT
   changing it; only subsequent presses (while the value is flashing) adjust it.
   If you wait too long after the first press, the display stops flashing and
   reverts to showing the ACTUAL water temperature, and the next press just wakes
   it again. (Balboa TP-series / Spa Touch user guides.)

2. This project's own protocol capture notes:
   - `protocol/rs485-status-2026-03-08.md:172` and `:232-235`: "Balboa panels
     display actual water temperature in idle mode (not setpoint) ... Setpoint is
     only shown briefly after pressing temp up/down."
   - `:133,143`: a temp button press triggers the panel's "setpoint flash"
     display mode (`0x77` replaces `0x70`), i.e. the panel enters a
     blank->value->blank set-mode flash cycle when a button is pressed.

3. `github.com/netmindz/balboa_GL_ML_spa_control` describes the GL2000 <-> ML
   panel protocol; the specific wake behavior above is the standard Balboa panel
   UX, matching (1).

Implication: the FIRST injected press, when the panel is idle (which it almost
always is at command time — the set-mode flash times out after ~1-2s and the tub
sits in idle showing water temperature), is consumed as a wake/flash and does NOT
move the setpoint. N presses therefore produce N-1 increments.

---

## Root cause

### Defect 1 — one-degree undershoot on the known-setpoint fast path

`start_adjusting_()` sends exactly `abs(delta)` presses
(`button_injector.cpp:161-167`) with zero compensation for the Balboa wake press.
On the known-setpoint fast path (`request_temperature`
`button_injector.cpp:90-95`), `from_setpoint = known_setpoint_`, so:

- known 101, target 102 -> delta 1 -> ONE up press.
- Panel is idle, so that single press is the wake/flash: it shows "101" and does
  not increment. Panel stays at 101. Undershoot by exactly 1.

This matches the report exactly, including "re-drive 101 then 102 still lands
101": commanding 101 while the panel is at 101 is a delta-0 no-op that leaves the
panel idle and asleep, so the subsequent 102 command's single press is again
eaten as a wake press.

Why the PROBE path does NOT have this bug (and why the fast path does): the probe
fires one down press first and then RE-DERIVES the reference from what the display
shows afterward (`loop_probing_` `button_injector.cpp:231-237`). Whether that
probe press woke the panel (setpoint unchanged, reads 101) or genuinely
decremented it (reads 100), the subsequent `start_adjusting_(probed)` delta math
lands on target either way. The probe press absorbs the wake. The fast path skips
the probe, so nothing absorbs the wake, and it undershoots. This is the concrete,
cited evidence confirming the wake-press hypothesis.

### Defect 2 — false `success` (correctness gap)

`VERIFYING` declares success when `last_display_temp_ == target_temp_`
(`button_injector.cpp:294-295`), but `last_display_temp_` is fed EVERY numeric
frame including the idle WATER TEMPERATURE
(`tublemetry_display.cpp:366-369`), not only confirmed setpoint flashes. So when
the panel is short at 101 but the tub WATER happens to read 102 during the 10s
verify window (very common right after the tub had been held at a 102 setpoint,
or while coasting), verification matches water temp against target and reports
`success` — while the actual confirmed setpoint (`detected_setpoint_`, captured
by the blank->value->blank state machine at `tublemetry_display.cpp:400-411`)
never equaled the target. This is precisely why the live entities show
`last_command_result = success` alongside `detected_setpoint = 101`.

The component already computes the trustworthy signal (`detected_setpoint_`) but
`VERIFYING` ignores it and trusts raw display temperature instead.

---

## Proposed fix (primary recommendation)

Preferred approach: closed-loop verification gated on the CONFIRMED detected
setpoint, with bounded re-pressing to make up any shortfall. This is more robust
than a blind "N+1 wake press" because it self-corrects regardless of whether the
panel happened to already be awake:

- If the panel was idle (normal case): the first press is eaten as a wake, the
  batch lands one short, VERIFYING sees the confirmed setpoint is short by 1 and
  fires exactly one more press (within the existing N+2 budget). Final = target.
- If the panel was already awake (rare, back-to-back commands): the batch lands
  exactly on target, confirmed == target, no extra press fired. No overshoot.

A blind N+1 would OVERSHOOT in the second case; the closed loop does not. The
existing `press_budget_ = abs_delta + 2` (`button_injector.cpp:162`) already
reserves the slack this needs — the current code simply never uses it.

Trade-offs:
- Requires a real confirmed-setpoint feed into the injector (small plumbing
  change) and reuses the existing `ADJUSTING` phase for the make-up press.
- Verification now depends on the panel emitting a setpoint flash within the
  10s `verify_timeout_ms_`. The injected presses themselves trigger that flash,
  so this holds; if no flash is captured it falls through to the existing
  timeout+retry path (safe).
- Latency: at most one extra 500ms press-cycle per command in the common case.

### Patch

Diff 1 — feed the CONFIRMED setpoint into the injector (separate from raw display
temperature):

```diff
--- a/esphome/components/tublemetry_display/tublemetry_display.cpp
+++ b/esphome/components/tublemetry_display/tublemetry_display.cpp
@@ -403,8 +403,11 @@ void TublemetryDisplay::classify_display_state_(const std::string &display_str) {
         this->detected_setpoint_ = this->set_temp_potential_;
         if (this->detected_setpoint_sensor_ != nullptr)
           this->detected_setpoint_sensor_->publish_state(this->detected_setpoint_);
-        if (this->injector_ != nullptr)
+        if (this->injector_ != nullptr) {
           this->injector_->set_known_setpoint(this->detected_setpoint_);
+          // Closed-loop verification: only a CONFIRMED setpoint flash counts.
+          this->injector_->feed_confirmed_setpoint(this->detected_setpoint_);
+        }
         ESP_LOGI(TAG, "Setpoint detected: %.0fF", this->detected_setpoint_);
         this->last_setpoint_capture_ms_ = millis();
       }
```

Diff 2 — injector header: add the confirmed-setpoint feed and state:

```diff
--- a/esphome/components/tublemetry_display/button_injector.h
+++ b/esphome/components/tublemetry_display/button_injector.h
@@ -93,6 +93,10 @@ class ButtonInjector {
   /// Feed the current display temperature from the decode pipeline.
   /// Used during PROBING and VERIFYING to read the current setpoint.
   void feed_display_temperature(float temp);
+
+  /// Feed a CONFIRMED setpoint (captured via the panel's set-mode flash).
+  /// Used by VERIFYING as the sole source of truth — unlike raw display
+  /// temperature, this cannot be the idle water-temperature reading.
+  void feed_confirmed_setpoint(float temp);
@@ -143,6 +147,9 @@ class ButtonInjector {
   float last_display_temp_{NAN};   // last temperature fed from display stream
   float probed_setpoint_{NAN};     // setpoint captured during PROBING phase
+  // Confirmed setpoint (set-mode flash) used for closed-loop verification.
+  float confirmed_setpoint_{NAN};
+  uint32_t confirmed_setpoint_seen_ms_{0};
```

Diff 3 — injector cpp: implement the feed and rewrite `VERIFYING` to gate on the
confirmed setpoint and re-press any shortfall within budget:

```diff
--- a/esphome/components/tublemetry_display/button_injector.cpp
+++ b/esphome/components/tublemetry_display/button_injector.cpp
@@ -290,18 +290,55 @@ void ButtonInjector::loop_adjusting_() {
 void ButtonInjector::loop_verifying_() {
   uint32_t now = millis();
   uint32_t elapsed = now - this->phase_start_ms_;
 
-  if (!std::isnan(this->last_display_temp_) &&
-      this->last_display_temp_ == this->target_temp_) {
-    ESP_LOGI(TAG, "Verified: display shows %.0fF — sequence successful", this->target_temp_);
-    this->finish_sequence_(InjectorResult::SUCCESS);
-    return;
+  // Verification MUST use a CONFIRMED setpoint captured during THIS sequence.
+  // Raw display temperature is the idle WATER temperature in normal mode and can
+  // coincidentally equal the target, producing a false success.
+  bool have_fresh_confirm =
+      !std::isnan(this->confirmed_setpoint_) &&
+      this->confirmed_setpoint_seen_ms_ >= this->phase_start_ms_;
+
+  if (have_fresh_confirm) {
+    if (this->confirmed_setpoint_ == this->target_temp_) {
+      ESP_LOGI(TAG, "Verified: confirmed setpoint %.0fF == target — success",
+               this->target_temp_);
+      this->finish_sequence_(InjectorResult::SUCCESS);
+      return;
+    }
+
+    // Panel is short of (or past) target — e.g. the Balboa wake/flash press was
+    // consumed without changing the setpoint. Drive the remaining delta, staying
+    // within the N+2 press budget. This closed loop is immune to the wake press.
+    int remaining = static_cast<int>(roundf(this->target_temp_)) -
+                    static_cast<int>(roundf(this->confirmed_setpoint_));
+    if (remaining != 0 && this->presses_consumed_ < this->press_budget_) {
+      uint8_t budget_left = this->press_budget_ - this->presses_consumed_;
+      uint8_t more = static_cast<uint8_t>(std::abs(remaining));
+      if (more > budget_left) more = budget_left;
+      this->adjusting_up_ = (remaining > 0);
+      this->presses_remaining_ = more;
+      this->presses_total_ = more;   // NOTE: do NOT reset presses_consumed_/press_budget_
+      ESP_LOGW(TAG, "Setpoint short: confirmed %.0fF, target %.0fF — %d more %s-press(es)",
+               this->confirmed_setpoint_, this->target_temp_, (int) more,
+               this->adjusting_up_ ? "up" : "down");
+      this->transition_to_(InjectorPhase::ADJUSTING);
+      return;
+    }
   }
 
   if (elapsed >= this->verify_timeout_ms_) {
-    ESP_LOGW(TAG, "Verification timeout after %dms — display shows %.0fF, expected %.0fF",
-             (int) elapsed,
-             std::isnan(this->last_display_temp_) ? -1.0f : this->last_display_temp_,
-             this->target_temp_);
+    ESP_LOGW(TAG, "Verification timeout after %dms — confirmed setpoint %.0fF, expected %.0fF",
+             (int) elapsed,
+             std::isnan(this->confirmed_setpoint_) ? -1.0f : this->confirmed_setpoint_,
+             this->target_temp_);
     this->finish_sequence_(InjectorResult::TIMEOUT, "verification timeout");
   }
 }
@@ -426,6 +463,11 @@ void ButtonInjector::feed_display_temperature(float temp) {
   this->last_display_temp_ = temp;
 }
 
+void ButtonInjector::feed_confirmed_setpoint(float temp) {
+  this->confirmed_setpoint_ = temp;
+  this->confirmed_setpoint_seen_ms_ = millis();
+}
+
 // --- Abort ---
```

Budget accounting check (delta = 1, common case): `press_budget_ = 3`. ADJUSTING
fires 1 press (`presses_consumed_ = 1`), wake press eats it, panel still 101.
VERIFYING: confirmed 101, remaining +1, `presses_consumed_ (1) < press_budget_
(3)`, `budget_left = 2`, fire 1 more. That press increments 101 -> 102.
`presses_consumed_ = 2`. VERIFYING: confirmed 102 == target -> success. The
`loop_adjusting_` budget guard (`presses_consumed_ > press_budget_`,
`button_injector.cpp:263`) never trips (2 <= 3). Overshoot case is handled
symmetrically (`remaining < 0` -> down presses).

### Alternative fixes considered

- Blind N+1 (fire one extra "wake" press, count the rest): simplest, but
  OVERSHOOTS whenever the panel is already awake (back-to-back commands, or
  immediately after an auto-refresh). Rejected as not robust.
- Route every command through `PROBING` (drop the fast path): the probe press is
  already wake-immune (see Root Cause), so this removes the undershoot with
  well-tested code and minimal change. Good interim mitigation, but it still
  needs Defect 2's verification fix, and it relies on the probe's fixed 300ms
  read timing rather than a confirmed flash. Acceptable fallback; the closed-loop
  fix above is strictly more robust and also cures Defect 2.

Either way, Defect 2 (gating `success` on the confirmed `detected_setpoint_`
rather than raw display temperature) must be fixed — otherwise the injector keeps
reporting `success` without proving the panel reached the target.

---

## Testing

### Why the current tests missed this

`tests/test_button_injection.py` does NOT exercise the C++ at all — it contains a
Python re-implementation, `SimulatedInjector`, that mirrors the same buggy
assumptions:

- `SimulatedInjector.feed_temperature()` (`test_button_injection.py:167-176`)
  declares success whenever `temp == target_temp`. It models the display feed as
  "always the setpoint" and never models the idle water temperature — so it can
  never reproduce Defect 2.
- The model has NO concept of a wake press. `_start_adjusting`
  (`:149-159`) sets `presses_needed = abs(delta)` and `run_to_verify`
  (`:161-165`) jumps straight to VERIFYING assuming every press landed — so it
  can never reproduce Defect 1.
- `test_wrong_temperature_doesnt_verify` (`:537-543`) only checks that feeding a
  wrong temp stays in VERIFYING; it never asserts the panel's TRUE setpoint, and
  it never feeds a coincidental water temp equal to target.

In short, the tests validate the simulation against its own assumptions, not
against real Balboa panel semantics. The tests pass while the firmware is wrong.

### Proposed test cases (would have caught the bug)

Add a physical-panel model that encodes the real Balboa semantics, and drive the
injector logic against it, asserting the PANEL'S true setpoint — not the injector's
self-reported result. Suggested `tests/test_injection_wake_press.py`:

Panel model (`FakeBalboaPanel`):
- Holds `true_setpoint` and `water_temp` independently.
- `press(up)`: if the display is idle/asleep, the press only wakes it and flashes
  the current setpoint (no change); if awake (within the flash window), the press
  changes `true_setpoint` by +/-1. A flash timeout returns the display to showing
  `water_temp`.
- Exposes the frame stream the injector would see: setpoint value during the
  flash window, `water_temp` otherwise.

Test cases:
1. `test_known_setpoint_delta_one_reaches_target_when_idle`: panel idle, true
   setpoint 101, water 102, command 102. Assert final `panel.true_setpoint == 102`.
   (Fails today: lands 101.)
2. `test_no_false_success_from_water_temp`: panel short at 101 while water reads
   102 during the verify window; assert the sequence does NOT report `success`
   and/or reports `success` ONLY when the confirmed setpoint equals target.
   (Fails today: reports success.)
3. `test_closed_loop_repress_makes_up_shortfall`: after the wake press eats one,
   assert exactly one additional press is issued within the N+2 budget and the
   panel reaches target.
4. `test_already_awake_no_overshoot`: panel already awake, command +1; assert the
   panel lands exactly on target (guards against a naive N+1 overshoot).
5. `test_overshoot_correction_symmetric`: if the confirmed setpoint overshoots by
   1, assert one down press corrects it, within budget.
6. `test_verify_gated_on_confirmed_not_display_temp`: feed water temp == target
   with confirmed setpoint != target; assert VERIFYING does not succeed; then feed
   confirmed == target; assert success.
7. `test_budget_bounds_repress`: contrive a stuck panel (presses never land);
   assert the make-up loop stops at `press_budget_` and routes to TIMEOUT/retry
   rather than pressing forever.

Also update `SimulatedInjector` (or better, replace its verify model) so
`feed_temperature` no longer equals success — success must come from a confirmed
setpoint feed — keeping the Python model faithful to the corrected firmware.

Run with: `uv run python -m pytest tests/test_injection_wake_press.py -v`
(full suite: `uv run python -m pytest tests/`).

Note: these are logic-level tests against a faithful panel model. They catch the
off-by-one and the false-success deterministically; final confirmation still
requires a hardware smoke test after any reflash (explicitly out of scope here).

---

## Summary of cited evidence

- Undershoot source: `button_injector.cpp:161-167` (`presses_remaining_ =
  abs_delta`, no wake compensation) on the fast path `button_injector.cpp:90-95`.
- Wake-press immunity of the probe (proves the mechanism):
  `button_injector.cpp:231-237`.
- False success: `button_injector.cpp:294-295` compares against
  `last_display_temp_`, which is fed the idle water temperature at
  `tublemetry_display.cpp:366-369`; the trustworthy confirmed setpoint is computed
  but ignored at `tublemetry_display.cpp:400-411`.
- Balboa wake behavior corroborated by `protocol/rs485-status-2026-03-08.md:172,
  :232-235, :133, :143` and Balboa user documentation.
- Test blind spot: `tests/test_button_injection.py:167-176` and `:149-165`.
</content>
</invoke>
