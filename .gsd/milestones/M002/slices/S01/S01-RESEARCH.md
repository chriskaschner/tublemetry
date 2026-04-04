# S01: Frame Integrity — Checksum + Stability Filter — Research

**Date:** 2026-04-03
**Status:** Ready for planning

## Summary

S01 adds two integrity layers to `process_frame_()` in `tublemetry_display.cpp`: a **checksum gate** (reject frames whose p1 bits 6,3,1,0 or p4 bit 0 are non-zero) and a **stability filter** (accumulate a consecutive-match counter, publish only after 3 matching frames). Both patterns are directly ported from kgstorm's `esp32-spa.h`. The codebase is clean and well-structured for this work — both changes land entirely in `process_frame_()` and the class header, with matching Python-side tests in a new `tests/test_frame_integrity.py` file.

The checksum exploits a physical constraint: the hundreds digit of a 3-digit hot-tub temperature can only ever be blank (0x00) or "1" (0x30 / 0x34). Both values happen to have zeros in the same 4 bit positions (bits 6, 3, 1, 0 of the 7-bit segment byte), so any corrupted frame that flips those bits fails immediately. Startup dashes (0x01) also fail — this is correct per R001.

The stability filter is a straightforward counter: keep `candidate_frame` and `stable_count_` as class members. Each call to `process_frame_()` compares the newly decoded display string against the candidate. Match → increment count. Mismatch → reset candidate and count to 1. Only when count reaches `STABLE_THRESHOLD` (3) is the frame forwarded to the existing publish logic. This operates at the decoded-display-string level, not the raw 24-bit level, to avoid false resets from innocuous bit variation in unused positions.

This is well-understood work. No new libraries, no new ESPHome platform files, no new HA entities. All changes are self-contained C++ and Python.

## Recommendation

Implement in two sequential steps:
1. **Checksum gate** — add immediately before digit extraction in `process_frame_()`, log dropped frames at WARN level.
2. **Stability filter** — add after digit extraction and decode, before the publish logic, comparing decoded display strings with STABLE_THRESHOLD=3.

Write Python tests that simulate the same logic (helper functions in the test already exist in `tests/test_mock_frames.py` — new tests go in a separate file or extend existing).

## Implementation Landscape

### Key Files

- `esphome/components/tublemetry_display/tublemetry_display.cpp` — `process_frame_()` is the sole insertion point for both checksum and stability logic. All changes fit here.
- `esphome/components/tublemetry_display/tublemetry_display.h` — needs two new class members: `candidate_display_string_` (std::string) and `stable_count_` (uint8_t), plus `STABLE_THRESHOLD` constant.
- `tests/test_mock_frames.py` — existing frame tests. Extend or add `tests/test_frame_integrity.py` with checksum and stability filter tests using the already-defined `frame_to_display_string()` and `digits_to_frame()` helpers.
- `src/tublemetry/decode.py` — no changes needed (7-seg table is stable).

### Exact Checksum Logic (from kgstorm)

```cpp
// After extracting p1, p2, p3, p4:
uint8_t p1 = (frame_bits >> 17) & 0x7F;
uint8_t p4 = frame_bits & 0x07;

static constexpr uint8_t CHECKSUM_MASK = 0x4B;  // bits 6,3,1,0 of p1
if ((p1 & CHECKSUM_MASK) != 0x00 || (p4 & 0x01) != 0x00) {
    ESP_LOGW(TAG, "Frame checksum failed (p1=0x%02X p4=0x%X), dropping", p1, p4);
    return;
}
```

Verification: `0x00 & 0x4B = 0x00` ✓, `0x30 & 0x4B = 0x00` ✓, `0x34 & 0x4B = 0x00` ✓, `0x7E & 0x4B = 0x4A` ✗ (corrupt hundreds-digit). The startup dash 0x01 → `0x01 & 0x4B = 0x01 ≠ 0x00` → rejected as documented in R001.

### Exact Stability Filter Logic

In the .h file — new member variables:
```cpp
std::string candidate_display_string_;  // last decoded frame for comparison
uint8_t stable_count_{0};               // consecutive matching frames
static constexpr uint8_t STABLE_THRESHOLD = 3;
```

In `process_frame_()`, after the partial-frame drop but before the publish logic:
```cpp
// Stability filter — require STABLE_THRESHOLD consecutive identical decoded frames
if (display_str == this->candidate_display_string_) {
    if (this->stable_count_ < 255) this->stable_count_++;
} else {
    this->candidate_display_string_ = display_str;
    this->stable_count_ = 1;
}
if (this->stable_count_ < STABLE_THRESHOLD) {
    ESP_LOGD(TAG, "Stability: %d/%d for '%s', holding", this->stable_count_, STABLE_THRESHOLD, display_str.c_str());
    return;
}
```

### Current `process_frame_()` Flow (insertion points marked)

```
process_frame_(frame_bits)
  1. Extract digit_bytes[3] and status — CHECKSUM GATE GOES HERE (on p1 and status)
  2. Decode each digit to char
  3. Build display_str, raw_hex, digit_values
  4. Calculate confidence
  5. Drop partial frames (known_count < 3) — STABILITY FILTER GOES HERE (after #5)
  6. Publish on change (display_string, raw_hex, digit_values, confidence)
  7. classify_display_state_()
  8. publish_timestamp_()
```

### Build Order

1. Add class members to `.h` (candidate_display_string_, stable_count_, STABLE_THRESHOLD constant)
2. Add checksum gate to `process_frame_()` — first change, verify all existing tests still pass
3. Add stability filter to `process_frame_()` — second change
4. Write `tests/test_frame_integrity.py` — test both features in Python via the existing `frame_to_display_string()` and `digits_to_frame()` helpers (no C++ test runner needed; logic mirrors C++ exactly)
5. Run `uv run pytest tests/ --ignore=tests/test_ladder_capture.py` — must pass all 249 existing tests + new ones

### Verification Approach

```bash
# Python tests (contract):
uv run pytest tests/ --ignore=tests/test_ladder_capture.py -v

# ESPHome compile (build gate):
uv run esphome compile esphome/tublemetry.yaml
```

Observable behaviors to test:
- Frame with p1=0x7E (hundreds digit = '0', impossible in valid temperature) is dropped
- Frame with p4 bit0=1 is dropped  
- Startup dashes (p1=0x01) are dropped
- Frame with p1=0x00 (blank hundreds, valid) passes checksum
- Frame with p1=0x30 (hundreds='1', valid) passes checksum
- 2 identical frames in a row: not published
- 3 identical frames in a row: published
- 2 identical then 1 different: counter resets; 3rd frame starts new candidate streak

## Constraints

- All new code in `process_frame_()` runs in `loop()` context — NOT in ISR. Safe to use `std::string`, `ESP_LOG*`, and instance members.
- ISR code (`clock_isr_()`) must not be touched for S01 — it's already correct.
- `STABLE_THRESHOLD` should be a `constexpr` in the class, not a runtime-configurable option (per R002, configurable threshold is "nice-to-have but not required").
- Stability comparison operates on the **decoded display string** (e.g. "104"), not raw 24-bit frame bits — this matches kgstorm's approach and avoids resets from status-bit variation between otherwise identical display states.
- The existing "publish on change" logic (`if (display_str != this->last_display_string_)`) already deduplicates — stability filtering is an additional upstream gate, not a replacement.

## Common Pitfalls

- **Comparing raw frame bits instead of decoded strings** — raw 24-bit frames can differ in status bits even when the display shows the same value. Compare decoded `display_str` for stability.
- **Placing checksum gate after digit extraction** — the checksum only needs `p1` and `p4` (the status byte), both available immediately. Gate first, save work on bad frames.
- **Forgetting that startup dashes fail checksum** — this is intentional (R001 explicitly notes it). Do NOT special-case them to pass.
- **stable_count_ saturation** — cap at 255 to prevent uint8_t overflow (same as kgstorm).

## Sources

- kgstorm `esp32-spa.h`: checksum mask 0x4B, STABLE_THRESHOLD=3, stability comparison on decoded temperature values. (source: [kgstorm/Balboa-GS100-with-VL260-topside](https://github.com/kgstorm/Balboa-GS100-with-VL260-topside))
