# S03: Status Bit Binary Sensors — Research

**Date:** 2026-04-03
**Risk:** Low

## Summary

S03 exposes heater, pump, and light state as HA binary sensors by extracting three bits from the `status` byte already computed in `process_frame_()`. The `status` byte (`frame_bits & 0x07`, bits 2-0 of the 24-bit frame) is already extracted and validated (bit 0 is the checksum sentinel, so valid frames have `status & 0x07` with bit 0 always clear — leaving bits 2 and 1 for pump and light, and heater comes from p1 bit 2).

The frame layout confirmed in S01:
- `p1 = (frame_bits >> 17) & 0x7F` — hundreds digit byte (bits 23-17)
- `status = frame_bits & 0x07` — 3 status bits (bits 2-0)

Per kgstorm's analysis (and the requirements):
- **Heater**: bit 2 of `p1` → `(p1 >> 2) & 0x01`
- **Pump**: bit 2 of `status` (p4) → `(status >> 2) & 0x01`
- **Light**: bit 1 of `status` (p4) → `(status >> 1) & 0x01`

Note: bit 0 of p4 is already the checksum sentinel (always 0 in valid frames), so pump=bit2 and light=bit1 of the 3-bit status are the only useful bits. The heater comes from the hundreds digit byte, not the status bits — this is the key detail from kgstorm's analysis.

This is straightforward wiring: add three `binary_sensor::BinarySensor*` pointers to the C++ class, extract their bits in `process_frame_()` after the stability gate, and add a `binary_sensor.py` ESPHome codegen file following the established sensor.py/text_sensor.py pattern.

## Recommendation

Three tasks:
1. **C++ changes** — add sensor pointers to header, extract bits and publish in `process_frame_()` after the stability gate passes
2. **ESPHome codegen** — add `binary_sensor.py`, update `AUTO_LOAD` in `__init__.py`, wire entries in `tublemetry.yaml`
3. **Tests + dashboard** — Python mirror tests for bit extraction, YAML test for new entity IDs, dashboard card update

Test the bit extraction logic in Python with known captured frames (the `digits_to_frame(p1, p2, p3, status)` helper from `test_mock_frames.py` constructs frames directly; status can encode heater=bit2-of-p1 and pump/light bits).

## Implementation Landscape

### Key Files

- `esphome/components/tublemetry_display/tublemetry_display.h` — Add three `binary_sensor::BinarySensor*` pointers (`heater_binary_sensor_`, `pump_binary_sensor_`, `light_binary_sensor_`) and setter methods to the protected section. Add `#include "esphome/components/binary_sensor/binary_sensor.h"`.
- `esphome/components/tublemetry_display/tublemetry_display.cpp` — In `process_frame_()`, after the stability gate block, extract status bits and publish. Pattern to follow: same change-only guard used for other sensors (`last_heater_` etc. booleans). Insert after the `classify_display_state_()` call (status bits aren't state-machine-dependent — they're frame-level data).
- `esphome/components/tublemetry_display/__init__.py` — Add `"binary_sensor"` to `AUTO_LOAD = ["sensor", "text_sensor", "number"]`.
- `esphome/components/tublemetry_display/binary_sensor.py` — New file. Multi-sensor pattern from msa3xx: three `cv.Optional` keys (`heater`, `pump`, `light`), each a `binary_sensor.binary_sensor_schema(...)` with an appropriate `device_class` and icon. `to_code()` calls `binary_sensor.new_binary_sensor()` for each and calls the setter on the parent.
- `esphome/tublemetry.yaml` — Add under `binary_sensor:` section (already exists for the API status sensor). Pattern: `- platform: tublemetry_display` with `tublemetry_id: hot_tub_display` and three optional keys.
- `ha/dashboard.yaml` — Add a new status card (entities card) for heater/pump/light.
- `tests/test_status_bits.py` — New test file. Python mirrors of bit extraction logic. Uses `digits_to_frame()` from `test_mock_frames.py` to construct frames with known status bits and verifies correct extraction. Also tests publish-on-change behavior.

### Build Order

1. **C++ header + implementation first** — adding pointer fields and extraction logic is self-contained and doesn't depend on the codegen. This is also what's compile-verified.
2. **ESPHome codegen second** — `binary_sensor.py` + `__init__.py` update + YAML entries. These are interdependent (wrong AUTO_LOAD → compile error), do them together.
3. **Tests + dashboard last** — Python tests verify the bit math; YAML tests verify entity IDs. Dashboard update is config-only, no compile risk.

### Bit Extraction Details

```cpp
// After stability gate passes — extract status bits for binary sensors
// p1 is already computed for the checksum gate; re-extract here
uint8_t p1_full = (frame_bits >> 17) & 0x7F;
bool heater_on = (p1_full >> 2) & 0x01;  // p1 bit 2
bool pump_on   = (status >> 2) & 0x01;   // p4 bit 2
bool light_on  = (status >> 1) & 0x01;   // p4 bit 1

if (this->heater_binary_sensor_ != nullptr) this->heater_binary_sensor_->publish_state(heater_on);
if (this->pump_binary_sensor_ != nullptr)   this->pump_binary_sensor_->publish_state(pump_on);
if (this->light_binary_sensor_ != nullptr)  this->light_binary_sensor_->publish_state(light_on);
```

Note: `status` is already extracted at the top of `process_frame_()` as `frame_bits & 0x07`. `p1` is extracted in a scoped block for the checksum gate — re-extract outside that scoped block for status bit use. The scoped block approach (from S01's pattern) was used to avoid variable name collision; re-extracting p1 outside the scope is intentional.

Publish-on-change pattern: add `last_heater_`, `last_pump_`, `last_light_` boolean members (initialized to false). Publish only when changed. This is consistent with how `last_display_string_` etc. are handled.

### ESPHome binary_sensor.py Pattern

```python
CONF_TUBLEMETRY_ID = "tublemetry_id"
CONF_HEATER = "heater"
CONF_PUMP = "pump"
CONF_LIGHT = "light"

CONFIG_SCHEMA = cv.Schema({
    cv.Required(CONF_TUBLEMETRY_ID): cv.use_id(TublemetryDisplay),
    cv.Optional(CONF_HEATER): binary_sensor.binary_sensor_schema(
        device_class="heat", icon="mdi:fire"
    ),
    cv.Optional(CONF_PUMP): binary_sensor.binary_sensor_schema(
        device_class="running", icon="mdi:pump"
    ),
    cv.Optional(CONF_LIGHT): binary_sensor.binary_sensor_schema(
        device_class="light", icon="mdi:lightbulb"
    ),
})
```

Check available ESPHome `device_class` values for binary sensors — confirmed valid values include `"heat"`, `"running"`, `"light"`. If `"running"` or `"light"` device classes don't exist in the installed ESPHome version, fall back to no `device_class` and use icon only. The tublemetry project uses ESPHome from `.venv`; can verify available device classes at runtime.

### YAML additions

Under the existing `binary_sensor:` section in `tublemetry.yaml`:

```yaml
  - platform: tublemetry_display
    tublemetry_id: hot_tub_display
    heater:
      name: "Hot Tub Heater"
    pump:
      name: "Hot Tub Pump"
    light:
      name: "Hot Tub Light"
```

Entity IDs will be: `binary_sensor.tublemetry_hot_tub_heater`, `binary_sensor.tublemetry_hot_tub_pump`, `binary_sensor.tublemetry_hot_tub_light`.

### Verification Approach

1. `uv run pytest tests/ --ignore=tests/test_ladder_capture.py` → all pass including new `test_status_bits.py`
2. `/Users/chriskaschner/Documents/GitHub/tubtron/.venv/bin/esphome compile esphome/tublemetry.yaml` → `[SUCCESS]`
3. Inspect compile output for binary_sensor entity IDs in generated C++

## Constraints

- Bit extraction must use already-decoded `status` (bits 2-0) and re-extracted `p1` — both already present in `process_frame_()`
- Binary sensor publish happens **after** the stability gate passes (same frame gate as all other publishes) — do not publish raw noisy frames
- No IRAM constraint on binary sensor publish — this runs in `loop()`, not ISR
- `p1` variable is scoped inside a `{ }` block for the checksum gate — must extract again outside that scope for status bit use

## Common Pitfalls

- **device_class values** — ESPHome binary_sensor device classes are validated at compile time. Use `rg` or check `.venv` source to confirm `"heat"`, `"running"`, `"light"` are valid before using them. If uncertain, omit `device_class` to avoid validation failure.
- **AUTO_LOAD missing binary_sensor** — Without `"binary_sensor"` in `AUTO_LOAD`, ESPHome won't include the binary_sensor headers and the C++ will fail to compile. See confirmed pattern from `hlk_fm22x/__init__.py`.
- **p1 scoping** — The checksum gate wraps p1 in a `{ }` block (S01 pattern). Don't try to use that p1 outside the scope — re-extract cleanly.
- **Publish-on-change initialization** — `last_heater_` etc. initialized to `false`. First frame after boot with heater=off will not trigger a publish (value unchanged). Consider initializing to a sentinel (e.g. `uint8_t` with 0xFF vs 0/1) or just accepting that the first frame always publishes (simplest approach, matches existing sensor pattern).
