# Domain Pitfalls

**Domain:** Hot tub automation via ESP32 button injection (Balboa VS300FL4)
**Researched:** 2026-03-13

---

## Critical Pitfalls

Mistakes that cause rewrites, hardware damage, or safety incidents.

### Pitfall 1: Phantom Button Presses from Noise Coupling on Analog Lines

**What goes wrong:** The Balboa VS300FL4 topside panel uses analog voltage sensing for buttons -- idle ~2.3V, pressed ~4.7V (bridged to +5V). These high-impedance analog lines are extremely sensitive to noise. Any capacitive coupling, ground bounce, or EMI from nearby wiring can push the line voltage above the detection threshold, causing unintended temperature changes, jet activations, or light toggles.

**Why it happens:** The VL-series panel has no microcontroller and no debounce logic. It is a purely passive device: resistor dividers set idle voltage, and button presses bridge to +5V. The control board reads these as analog thresholds. Even an unterminated Cat5 breakout cable caused phantom Temp Up presses during this project's initial testing -- documented in `485/rs485-status-2026-03-08.md`.

**Consequences:**
- Temperature silently drifts up or down without user knowledge
- Jets or heater activate when nobody is in the tub, increasing energy costs
- In worst case, temperature could climb to 104F maximum during an unintended period
- Destroys trust in the automation system, defeating the project's purpose

**Prevention:**
- Use photorelays (AQY212EH) for galvanic isolation between ESP32 and button lines. This is already the design choice -- do not compromise it. Never use bare MOSFETs or analog switches without isolation.
- Keep wiring between the RJ45 breakout and photorelays as short as physically possible (<6 inches).
- Route button injection wires away from the RS-485 data lines (pins 5/6) and away from the 240V heater/pump wiring.
- Verify with multimeter that photorelay off-leakage (spec: 1uA max) does not shift idle voltage enough to cross the detection threshold.
- Add 100nF ceramic capacitors across each button line to ground at the RJ45 breakout to suppress high-frequency noise.

**Detection:** Unexpected temperature changes when the ESP32 is powered off or idle. Monitor RS-485 display stream (Phase 2) for temperature values that differ from the last commanded setpoint.

**Phase:** Phase 1 (button injection MVP) -- must be validated during breadboard testing (Task 2/3).

**Confidence:** HIGH -- directly observed during this project's testing.

---

### Pitfall 2: ESP32 GPIO Strapping Pins Firing Photorelays During Boot/Reset

**What goes wrong:** During power-on, reset, or OTA update, certain ESP32 GPIO pins briefly change state (high/low pulses lasting milliseconds). If photorelay control lines are connected to strapping pins (GPIO 0, 2, 5, 12, 15) or other pins with boot-time behavior, the photorelays will actuate during every boot cycle, causing unintended button presses on the hot tub.

**Why it happens:** The ESP32 uses strapping pins to determine boot mode (flash vs. normal execution). During the ~100ms boot sequence, these pins are driven to specific states by internal pull-ups/pull-downs and the bootloader. GPIO 5 and 15 are pulled HIGH during boot. GPIO 12 has an internal pull-down. Pins connected to the flash (GPIO 6-11) are completely off-limits.

**Consequences:**
- Every ESP32 reboot, OTA update, or power cycle triggers 1-3 phantom button presses
- Temperature changes by 1-3 degrees each time the ESP32 reboots
- With ESPHome's watchdog and WiFi reconnect behavior, reboots happen more often than expected
- Cumulative drift makes open-loop control unreliable

**Prevention:**
- Use only safe GPIO pins for photorelay outputs: GPIO 13, 16, 17, 18, 19, 21, 22, 23, 25, 26, 27, 32, 33 are safe for output
- Specifically avoid GPIO 0, 2, 5, 12, 15 (strapping), GPIO 6-11 (flash), GPIO 34-39 (input-only, no output driver)
- Verify chosen pins with a logic analyzer or oscilloscope during boot before connecting to photorelays
- Consider adding a hardware enable gate: use a "safe" GPIO to enable photorelay power only after boot completes (on_boot priority 600 in ESPHome)

**Detection:** Temperature changes that correlate with ESP32 reboot events in the ESPHome log. Attach LED to photorelay output during testing and observe during power cycle.

**Phase:** Phase 1 (firmware config, Task 1) -- pin selection must happen before breadboard build.

**Confidence:** HIGH -- well-documented ESP32 hardware behavior, multiple community reports.

**Sources:**
- [ESP32 Strapping Pins Complete Guide](https://www.espboards.dev/blog/esp32-strapping-pins/)
- [ESPHome GPIO switch toggles on boot issue #3094](https://github.com/esphome/issues/issues/3094)
- [Random Nerd Tutorials ESP32 Pinout Reference](https://randomnerdtutorials.com/esp32-pinout-reference-gpios/)

---

### Pitfall 3: Open-Loop Temperature Drift from Missed or Extra Button Presses

**What goes wrong:** The "re-home" strategy (slam 25x to floor at 80F, then count up to target) assumes every simulated button press is registered by the control board. If even one press is missed (too short, noise rejected) or double-counted (press too long, auto-repeat triggered), the final setpoint is wrong by 1F or more per missed/extra press. Over multiple TOU transitions per day, errors accumulate.

**Why it happens:**
- Button press timing parameters are unknown. The minimum press duration, inter-press gap, and auto-repeat threshold for the VS300FL4 are not documented anywhere. They must be empirically measured.
- The photorelay has finite switching times (turn-on: ~0.5ms typical, turn-off: ~0.1ms for AQY212EH). If the firmware pulse duration is too close to the board's minimum detection threshold, some presses will be rejected.
- If the pulse is too long (e.g., >2 seconds), the board may interpret it as a "hold" and enter auto-repeat mode, adding extra increments.
- Manual panel interaction between automation cycles (user adjusts temp by hand) completely invalidates the assumed position.

**Consequences:**
- Target setpoint of 99F ends up at 97F or 101F
- Error compounds across 2 TOU transitions/day = potential 2-4F drift per day
- User discovers tub at wrong temperature, loses trust in automation
- No feedback mechanism to detect the error in Phase 1 (open-loop)

**Prevention:**
- Task 3 (timing characterization) is the critical gate: measure minimum press duration, maximum press rate, and auto-repeat threshold with empirical testing on the actual hardware
- Use conservative timing margins: if minimum press is measured at 100ms, use 200ms. If auto-repeat starts at 2s, cap press duration at 500ms.
- Always run the full re-home sequence (slam to floor + count up) rather than incremental adjustments. This bounds worst-case error to a single sequence rather than accumulating across multiple sequences.
- Add a "re-home interval" -- run the full re-home sequence before every setpoint change, not just on drift correction. The extra 15-30 seconds per transition is worth the reliability.
- Phase 2 (display reading) eliminates this class of error entirely by providing closed-loop feedback. Prioritize it.

**Detection:** In Phase 1, the only detection is manual verification (look at the tub display). In Phase 2, compare RS-485 display reading to commanded setpoint after each re-home sequence.

**Phase:** Phase 1 (Task 3 timing characterization), resolved fully in Phase 2 (closed-loop).

**Confidence:** HIGH -- inherent to open-loop control; the project design already acknowledges this.

---

### Pitfall 4: Interfering with Balboa Safety Systems (Freeze Protection, Overheat)

**What goes wrong:** The Balboa VS300FL4 has built-in safety systems: overheat protection (OH/OHH codes above 108-118F), freeze protection (activates all equipment when water drops below 45F), and high-limit switch (hardware thermal cutoff). Automation that fights these systems can create dangerous or expensive situations.

**Why it happens:**
- The automation lowers temperature to 99F during on-peak hours. If ambient temperature drops and freeze protection activates while the setpoint is low, the automation might fight it by sending "temp down" presses during a freeze event.
- The system cannot distinguish between "user changed the temp" and "board is in protection mode" without display reading.
- Rapid setpoint changes (25 presses down, then 24 presses up) during a protection event could confuse the board's state machine.

**Consequences:**
- Freeze protection disabled or interrupted: pipes freeze, pump and heater damaged, $2000+ repair
- Overheat protection circumvented: water exceeds safe temperature, burn hazard for humans
- High-limit switch trips repeatedly: nuisance, potential relay damage on control board
- The VS300FL4 is discontinued -- replacement boards are $400-800 (BP100G2 upgrade)

**Prevention:**
- Never automate during extreme weather without temperature verification (Phase 2)
- The setpoint range is 80F-104F. The board itself prevents going above 104F or below 80F, which provides a hardware safety floor. Do not attempt to bypass this.
- In Phase 1, add a "weather gate" to the HA automation: skip TOU transitions if outdoor temperature is below 35F (freeze risk) or above 100F (heater may be fighting ambient)
- The re-home sequence (slam to 80F) is safe because 80F is above the 45F freeze protection threshold and below the overheat threshold
- In Phase 2, read the display stream to detect OH/OHH/ICE error codes and suppress automation during error states

**Detection:** Look for the board displaying error codes (OH, OHH, ICE) or the high-limit tripping. In Phase 2, parse the display stream for these error patterns.

**Phase:** Phase 1 (HA automation, Task 4) must include weather gating. Phase 2 resolves with display reading.

**Confidence:** HIGH -- Balboa freeze protection documented at 45F trigger, overheat at 108-118F.

**Sources:**
- [Spa & Hot Tub Error Codes OH/OHH/OHS](https://lesliespool.com/blog/spa-hot-tub-error-codes-oh-ohh-omg.html)
- [Freeze Protection on Balboa Systems](https://www.spaguts.com/spagutsfaqs/support-freeze-protection-on-balboa-m7-systems)
- [Preventing Freeze Damage](https://lesliespool.com/blog/preventing-freeze-damage-to-a-spa-or-hot-tub.html)

---

### Pitfall 5: ESP32 WiFi Disconnects Causing Lost Automation Commands

**What goes wrong:** The ESP32 loses WiFi connectivity, Home Assistant cannot reach the device, and scheduled TOU transitions fail silently. The tub stays at whatever setpoint it was last commanded to, potentially running the 4kW heater at 104F through the entire on-peak rate period, costing the money the project was designed to save.

**Why it happens:** ESP32 WiFi stability is a known pain point in the ESPHome community. Common causes:
- Signal strength below -70dBm (hot tub is outdoors, potentially far from router)
- Router DHCP lease expiry causing reconnect storms
- Power save mode conflicts (ESP32 power save vs. connection keepalive)
- Mesh network handoff delays (10+ minutes in some cases)
- ESP32 watchdog resets triggered by WiFi stack hangs

**Consequences:**
- Missed TOU transitions -- tub heats at on-peak rates, $0.20/kWh instead of $0.05/kWh
- Stale setpoint persists for hours until WiFi recovers or human notices
- Multiple watchdog reboots can trigger phantom button presses (see Pitfall 2)
- Automation appears "working" in HA dashboard (last known state) while actually disconnected

**Prevention:**
- Measure WiFi signal strength at the tub location before deploying. Need better than -65dBm for reliability.
- In ESPHome config, set `power_save_mode: none` to prevent WiFi sleep
- Set static IP to avoid DHCP lease issues: `use_address`, `manual_ip` in ESPHome WiFi config
- Implement a fallback: if ESP32 loses HA connection for >30 minutes, execute a safe default (e.g., set temp to 99F as a compromise)
- Use the `on_disconnect` trigger in ESPHome's `api:` component to log disconnects and trigger fallback behavior
- Consider a WiFi range extender or dedicated access point near the tub

**Detection:** Monitor ESPHome device uptime and connection status in Home Assistant. Set up HA notification if device goes offline for more than 10 minutes.

**Phase:** Phase 1 (firmware config, Task 1; HA automation, Task 4). WiFi reliability testing during breadboard prototype.

**Confidence:** HIGH -- extensively documented in ESPHome community, multiple GitHub issues.

**Sources:**
- [ESPHome disconnects constantly issue #1237](https://github.com/esphome/issues/issues/1237)
- [ESP32 loses connection after 3h20m issue #1196](https://github.com/esphome/issues/issues/1196)
- [Dealing with ESPHome Disconnects](https://www.thefrankes.com/wp/?p=4693)
- [ESP32 Disconnects Randomly](https://www.espboards.dev/troubleshooting/issues/wifi/esp32-disconnects-randomly/)

---

## Moderate Pitfalls

### Pitfall 6: ESPHome Momentary Switch Race Conditions During Re-Home Sequence

**What goes wrong:** The re-home sequence fires 25 rapid button presses (slam to floor), then counts up to target. If each press is implemented as a `switch.turn_on` with `delay` + `switch.turn_off`, concurrent HA commands or ESPHome automations can interrupt the sequence mid-execution, leaving the setpoint at an unknown intermediate value.

**Why it happens:** ESPHome delays are asynchronous. While a delay is running, other code continues executing. If HA sends a new setpoint command while a re-home sequence is in progress, both sequences can interleave, producing unpredictable GPIO patterns. Additionally, ESPHome's `on_turn_on` automation can enter infinite loops if the switch receives multiple rapid triggers.

**Prevention:**
- Use a global boolean `is_rehoming` flag to gate all setpoint changes. Check it before starting any sequence.
- Implement the entire re-home sequence as a single ESPHome `script:` with `mode: single` (rejects new calls while running) or `mode: restart` (cancels in-progress and starts fresh).
- Never expose individual "Temp Up" / "Temp Down" buttons to HA -- only expose the target setpoint as a `climate` entity. The firmware should own the re-home logic entirely.
- Use `script.wait` before issuing the count-up sequence to ensure the slam-down is complete.

**Detection:** Setpoint ends up at unexpected values after automation triggers. ESPHome logs showing overlapping script executions.

**Phase:** Phase 1 (firmware config, Task 1).

**Confidence:** MEDIUM -- based on ESPHome automation architecture and documented race conditions in similar patterns.

**Sources:**
- [ESPHome race condition in modbus_controller issue #3885](https://github.com/esphome/issues/issues/3885)
- [Switch on_turn_on loop discussion](https://community.home-assistant.io/t/switch-on-turn-on-loop/761620)
- [ESPHome delay not properly working issue #5025](https://github.com/esphome/issues/issues/5025)

---

### Pitfall 7: Photorelay On-Resistance Not Low Enough to Trigger Button Detection

**What goes wrong:** The AQY212EH has 25 ohm on-resistance (per datasheet). The Balboa board's button detection circuit is a voltage divider: idle at ~2.3V, "pressed" means bridging to +5V. If the photorelay's 25 ohm series resistance drops enough voltage in the divider network that the button line doesn't reach the board's detection threshold, button presses won't register.

**Why it happens:** The board's internal pull-down resistor value on the button lines is unknown. If it is low (e.g., 1K ohm), the AQY212EH's 25 ohm is negligible (button sees ~4.95V). If the pull-down is higher impedance and the detection threshold is close to the idle voltage, the 25 ohm might matter. This is entirely dependent on the unknown internal circuit design.

**Prevention:**
- Measure with a multimeter during Task 2 (breadboard prototype): with photorelay actuated, measure voltage on the button line. Must be above the detection threshold (estimated >4.0V based on the manual test where bridging directly to +5V worked).
- The manual proof-of-concept (bridging Pin 1 to Pin 8 directly with wire) had ~0 ohm resistance. The photorelay adds 25 ohm. If the internal pull-down is >500 ohm, this is fine (voltage will be >4.7V).
- If 25 ohm is too much (unlikely but possible), the AQY210EH variant has 0.55 ohm on-resistance but lower voltage rating. Or use two AQY212EH outputs in parallel (12.5 ohm).

**Detection:** Button presses don't register during breadboard testing. Multimeter on button line shows voltage below expected threshold when photorelay is actuated.

**Phase:** Phase 1 (Task 2, breadboard prototype).

**Confidence:** LOW -- the 25 ohm is likely fine given the circuit topology, but cannot be confirmed without measurement. The existing CONCERNS.md already flags this.

---

### Pitfall 8: RS-485 Display Reading (Phase 2) is Harder Than Expected

**What goes wrong:** The VS-series uses a synchronous clock+data protocol that is completely undocumented. The closest reference (MagnusPer/Balboa-GS510SZ for GS-series) uses a similar but not identical protocol. Assumptions about frame structure, timing, or encoding that work for the GS510SZ may not transfer to the VS300FL4, requiring fresh reverse engineering.

**Why it happens:**
- 72 candidate 7-segment mappings remain unresolved (need physical temperature ladder capture)
- The display multiplexing (Pin 5 fires content, Pin 6 fires refresh at 60Hz with ~400us offset) is confirmed but the full state machine is not understood
- The Pin 5 data line carries both idle frames and button-response burst patterns, which need to be distinguished
- The GS510SZ protocol has 42 clock pulses per cycle (39 for display + 3 for buttons). The VS300FL4 may differ.
- No existing ESPHome custom component handles this protocol family

**Prevention:**
- The temperature ladder capture (Task 5) is non-negotiable. Do it before starting any Phase 2 code.
- Study the MagnusPer/Balboa-GS510SZ source code carefully, but treat it as a reference, not a specification. The VS300FL4 is a different board generation.
- Plan for writing a custom ESPHome component (C++) rather than trying to use existing UART or SPI components. The synchronous clock+data protocol does not match standard UART framing.
- Budget significant time: this is uncharted territory. No published automation exists for VS-series boards.

**Detection:** Decoded display values don't match the physical panel display. Timing misalignment causes corrupted readings. ESPHome custom component crashes or produces garbage data.

**Phase:** Phase 2 (display stream decoding). Phase 1.5 (temperature ladder capture) is the prerequisite.

**Confidence:** MEDIUM -- the protocol structure is partially understood from existing captures, but significant unknowns remain.

**Sources:**
- [MagnusPer/Balboa-GS510SZ](https://github.com/MagnusPer/Balboa-GS510SZ)
- [HA Community: Writing ESPHome custom component with proprietary synchronous serial protocol](https://community.home-assistant.io/t/expert-advice-sought-writing-an-esphome-custom-component-with-a-proprietary-synchronous-serial-protocol/735070)

---

### Pitfall 9: Manual Panel Interaction Invalidates Automation State

**What goes wrong:** A human presses Temp Up/Down on the physical panel while automation is running. The ESP32 has no knowledge of this change. Its internal model of the current setpoint is now wrong. The next re-home sequence will set the correct absolute temperature (because it re-homes to floor first), but until that happens, the ESP32's reported state in Home Assistant is stale.

**Why it happens:** The VL-series panel is purely analog. There is no digital feedback from button presses on the panel. The ESP32 cannot detect that someone pressed a button on the physical panel. In Phase 1, the ESP32 is completely blind to the actual setpoint.

**Prevention:**
- Accept this limitation in Phase 1. Document it clearly for users. The re-home strategy bounds the damage: the next scheduled transition will correct the setpoint.
- In Phase 2, display reading detects the actual current setpoint, eliminating this issue.
- Consider running a re-home sequence on a timer (e.g., every 2 hours) rather than only at TOU transition points, to correct for manual overrides faster.
- In the HA UI, display a caveat: "Reported temperature may be inaccurate if panel was used manually."

**Detection:** Only detectable in Phase 2 via display reading. In Phase 1, user must visually verify.

**Phase:** Acknowledged in Phase 1, resolved in Phase 2.

**Confidence:** HIGH -- inherent to the architecture.

---

### Pitfall 10: ESP32 Environmental Damage from Hot Tub Proximity

**What goes wrong:** The ESP32, breadboard, and wiring corrode, short, or fail due to humidity, chemical vapors (chlorine/bromine), water splashes, or temperature cycling. The hot tub environment combines high humidity, corrosive chemicals, and potential splash exposure -- the worst possible environment for bare electronics.

**Why it happens:** Breadboard contacts oxidize in humid environments. Chlorine vapor accelerates copper corrosion on PCB traces and jumper wire contacts. Temperature cycling (hot cover + cold outdoor air) causes condensation inside enclosures. Water splash from jets or cover removal can reach nearby electronics.

**Prevention:**
- Phase 1 (breadboard prototype) is explicitly temporary. Accept it will degrade. Plan to move to soldered protoboard or PCB within weeks, not months.
- Mount the ESP32 at least 3 feet from the tub edge and above the water line.
- Use an IP65-rated enclosure with cable glands for any permanent installation.
- Apply conformal coating to the final soldered board.
- Route the RJ45 cable (which goes to the tub) through a drip loop before entering the enclosure.
- Use silicone-sealed connectors, not bare screw terminals, for the final installation.

**Detection:** Intermittent WiFi disconnects, erratic GPIO behavior, visible corrosion on contacts, musty smell inside enclosure.

**Phase:** Phase 1 (breadboard is temporary), permanent enclosure should be planned for Phase 2/3 deployment.

**Confidence:** HIGH -- well-documented in outdoor ESP32 projects and hot tub electronics.

**Sources:**
- [How to Waterproof ESP32 for Outdoor IoT Applications](https://waterproofrd.com/how-to-waterproof-esp32-pk441/)
- [Hot tub control panel fogging/moisture damage](https://www.justanswer.com/pool-and-spa/tks7z-hot-tub-control-panel-fogging.html)

---

## Minor Pitfalls

### Pitfall 11: NVS Flash Wear from Frequent State Saves

**What goes wrong:** ESPHome's `restore_value: true` on globals writes to NVS flash on every state change. If the firmware logs temperature readings, counters, or timestamps to NVS on every sensor poll (e.g., every 60 seconds), it can wear the flash partition within months.

**Prevention:**
- Use `restore_value: true` only for the target setpoint and re-home state, not for rapidly changing values.
- Set ESPHome's `flash_write_interval` to at least 5 minutes (default is adequate for this use case).
- For Phase 2 display readings, store current temperature in RAM only, not NVS.

**Phase:** Phase 1 (firmware config, Task 1).

**Confidence:** MEDIUM -- ESP32 NVS wear leveling mitigates this significantly; mainly a concern if implementation is careless.

**Sources:**
- [Flash Memory Wear Effects of ESPHome Recovery](https://newscrewdriver.com/2022/03/25/flash-memory-wear-effects-of-esphome-recovery-esp8266-vs-esp32/)

---

### Pitfall 12: MAX485 Voltage Level Mismatch with ESP32

**What goes wrong:** The MAX485 modules (5x on hand for Phase 2 display reading) operate at 5V logic. The ESP32 GPIO pins are 3.3V. While ESP32 inputs are 5V-tolerant on some pins (undocumented, not officially supported), driving a 5V MAX485 from 3.3V ESP32 TX may produce marginal logic levels.

**Prevention:**
- For Phase 2 (read-only display tap), the MAX485 RX output goes to ESP32 input. Use a voltage divider (2K/3.3K) or a level shifter on the MAX485 RO pin.
- Power the MAX485 from the hot tub board's +5V (Pin 1), not from the ESP32's 3.3V.
- The B0505S-1W isolated DC-DC is already in the BOM for this exact purpose.
- The MAX485 DE/RE pins for read-only operation should be tied to GND (permanent receive mode), avoiding any GPIO control complexity.

**Phase:** Phase 2 (display reading).

**Confidence:** HIGH -- standard MAX485 + ESP32 integration concern, well-documented.

**Sources:**
- [MAX485 TTL to RS485 Interfacing with ESP32](https://hackatronic.com/max485-ttl-to-rs485-modbus-module-interfacing-with-esp32/)
- [ESP32 RS-485 Forum Discussion](https://esp32.com/viewtopic.php?t=36288)

---

### Pitfall 13: Home Assistant TOU Automation Edge Cases

**What goes wrong:** The HA automation for TOU scheduling (99F on-peak 10am-9pm weekdays, 104F off-peak) can fail on edge cases: holidays (rates may differ), DST transitions (spring forward creates a 23-hour day), HA restarts during a transition window, or concurrent automations racing to set different temperatures.

**Prevention:**
- Use HA's `time` trigger (not `time_pattern`) for precise scheduling
- Add a condition to check current setpoint before commanding a change (avoid redundant re-home sequences)
- Use `mode: single` on the automation to prevent concurrent execution
- For DST: test by temporarily shifting system clock
- For holidays: the $10/month savings is small enough that holiday exceptions are not worth the complexity. The worst case is heating at on-peak rate for one day (~$0.50 extra).
- Add a manual override input_boolean in HA to suppress automation (e.g., for parties, maintenance)

**Phase:** Phase 1 (Task 4, HA automation).

**Confidence:** MEDIUM -- standard HA automation concerns, not highly specific to this project.

---

### Pitfall 14: Overwriting Capture Data (Again)

**What goes wrong:** The project has already lost one critical capture file (`rs485_capture.txt` was overwritten with Pin 6 data, destroying the original Pin 5 button-press capture). As more captures are taken (especially the Phase 1.5 temperature ladder), files could be overwritten again without tracking what was lost.

**Prevention:**
- Create `485/CAPTURES_INDEX.md` before any new captures: filename, date, pin, test conditions, known temperature at capture time.
- Use descriptive filenames with dates: `rs485_pin5_templadder_104_to_99_2026-03-20.txt`
- Never reuse filenames. Append a suffix rather than overwriting.
- Commit captures to git immediately after taking them.

**Phase:** Phase 1.5 (temperature ladder capture, Task 5).

**Confidence:** HIGH -- already happened once in this project.

---

### Pitfall 15: Unsafe Temperature Command from Software Bug

**What goes wrong:** A firmware bug, HA automation error, or edge case causes the system to enter a loop that continuously presses Temp Up, or an integer overflow in the press counter produces an absurd number of presses.

**Why it happens:** Software bugs. A stuck GPIO, an off-by-one in the press counter, or an automation that fires twice could overshoot the target.

**Consequences:** The board itself clamps setpoint to 80-104F range, which is the hardware safety floor. The board also has a high-limit switch (110-120F hardware thermal cutoff). So the risk is bounded to 104F maximum setpoint, not runaway heating. But 104F during on-peak hours is the exact scenario the automation exists to prevent.

**Prevention:**
- Firmware-level hard clamp: reject any setpoint outside 80-104F range before generating button presses.
- Maximum press count limit: never send more than 24 presses in a single count-up cycle (104-80=24). Assert this in code.
- Watchdog timer: if the re-home script takes longer than expected (e.g., >2 minutes), abort.
- HA automation validation: use `input_number` with min/max constraints for setpoint targets.

**Detection:** HA logs showing commanded setpoints. Firmware logs showing press counts exceeding expected range.

**Phase:** Phase 1 (firmware config, Task 1; HA automation, Task 4).

**Confidence:** HIGH -- standard software safety concern; mitigated by the board's own 104F clamp.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Phase 1, Task 1: ESPHome firmware config | Wrong GPIO pin selection causes boot-time phantom presses (Pitfall 2) | Use only safe pins: GPIO 16, 17, 18, 19, 21, 22, 23, 25, 26, 27 |
| Phase 1, Task 1: ESPHome firmware config | Re-home sequence race conditions (Pitfall 6) | Use `script:` with `mode: single`; global `is_rehoming` flag |
| Phase 1, Task 2: Breadboard prototype | Photorelay on-resistance too high (Pitfall 7); loose breadboard contacts | Measure voltages empirically; use short, solid-core jumper wires |
| Phase 1, Task 3: Button timing characterization | Unknown timing causes missed/extra presses (Pitfall 3) | Measure with logic analyzer; use 2x safety margin on all timing params |
| Phase 1, Task 4: HA TOU automation | WiFi disconnect causes missed transition (Pitfall 5); edge cases (Pitfall 13) | Static IP, power_save_mode: none, fallback behavior on disconnect |
| Phase 1, Task 4: HA TOU automation | Fighting freeze protection (Pitfall 4) | Add outdoor temp weather gate; skip low-setpoint commands when ambient < 35F |
| Phase 1.5, Task 5: Temperature ladder capture | Data overwrite (Pitfall 14) | Descriptive filenames, capture index, immediate git commit |
| Phase 2: Display stream decoding | Protocol harder than expected (Pitfall 8); voltage mismatch (Pitfall 12) | Temperature ladder first; level shifter; budget extra time |
| Phase 2: Closed-loop control | Display reading errors cause wrong corrections | Validate decoded temp against expected range; require N consecutive matching reads before acting |
| Phase 3: Community publication | Publishing incorrect protocol documentation | Verify all claims against empirical data; include capture files as evidence |
| Long-term: Outdoor deployment | Environmental damage (Pitfall 10) | IP65 enclosure, conformal coating, drip loops |

---

## Sources

- [ESP32 Strapping Pins Complete Guide - espboards.dev](https://www.espboards.dev/blog/esp32-strapping-pins/)
- [ESP32 Pinout Reference - Random Nerd Tutorials](https://randomnerdtutorials.com/esp32-pinout-reference-gpios/)
- [How to Choose Safe GPIO Pins on ESP32 WROOM-32](https://www.samgalope.dev/2024/12/28/safe-and-unsafe-pins-to-use-in-an-esp32-wroom-32/)
- [ESPHome GPIO switch toggles on boot - GitHub issue #3094](https://github.com/esphome/issues/issues/3094)
- [ESPHome disconnects constantly - GitHub issue #1237](https://github.com/esphome/issues/issues/1237)
- [ESP32 loses connection after 3h20m - GitHub issue #1196](https://github.com/esphome/issues/issues/1196)
- [Dealing with ESPHome Disconnects - theFrankes.com](https://www.thefrankes.com/wp/?p=4693)
- [ESP32 Disconnects Randomly - espboards.dev](https://www.espboards.dev/troubleshooting/issues/wifi/esp32-disconnects-randomly/)
- [Spa & Hot Tub Error Codes OH/OHH/OHS - Leslie's](https://lesliespool.com/blog/spa-hot-tub-error-codes-oh-ohh-omg.html)
- [Freeze Protection on Balboa Systems - SpaGuts](https://www.spaguts.com/spagutsfaqs/support-freeze-protection-on-balboa-m7-systems)
- [Preventing Freeze Damage - Leslie's](https://lesliespool.com/blog/preventing-freeze-damage-to-a-spa-or-hot-tub.html)
- [MagnusPer/Balboa-GS510SZ - GitHub](https://github.com/MagnusPer/Balboa-GS510SZ)
- [ESPHome Custom Component for Synchronous Protocol - HA Community](https://community.home-assistant.io/t/expert-advice-sought-writing-an-esphome-custom-component-with-a-proprietary-synchronous-serial-protocol/735070)
- [Balboa Hot Tub Automation - HA Community](https://community.home-assistant.io/t/balboa-hot-tub-spa-automation-and-power-savings/353032)
- [Flash Memory Wear Effects of ESPHome - New Screwdriver](https://newscrewdriver.com/2022/03/25/flash-memory-wear-effects-of-esphome-recovery-esp8266-vs-esp32/)
- [MAX485 Interfacing with ESP32 - Hackatronic](https://hackatronic.com/max485-ttl-to-rs485-modbus-module-interfacing-with-esp32/)
- [How to Waterproof ESP32 for Outdoor IoT - Waterproofrd](https://waterproofrd.com/how-to-waterproof-esp32-pk441/)
- [ESP32 Noise Triggers Input Button Events - ESP32 Forum](https://esp32.com/viewtopic.php?t=23160)
- [ESPHome race condition in modbus_controller - GitHub issue #3885](https://github.com/esphome/issues/issues/3885)
- [ESPHome delay not properly working - GitHub issue #5025](https://github.com/esphome/issues/issues/5025)
- Project context: .planning/PROJECT.md, .planning/phases/01-button-injection-mvp/.continue-here.md, .planning/codebase/CONCERNS.md

---

*Pitfalls research: 2026-03-13*
