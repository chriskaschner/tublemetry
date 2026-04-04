# S01: Frame Integrity — Checksum + Stability Filter

**Goal:** Add a checksum gate and stability filter to process_frame_() so the firmware rejects corrupt frames and requires 3 consecutive matching decoded frames before publishing any value to HA.
**Demo:** After this: After this: firmware rejects corrupt frames via checksum validation and requires 3 consecutive matching frames before publishing. Temperature history is cleaner with no single-frame noise spikes. Verified by tests + compile + existing HA entities unchanged.

## Tasks
- [x] **T01: Added checksum gate (CHECKSUM_MASK=0x4B on p1, bit0 on status) and 3-frame stability filter to process_frame_(); firmware compiles clean** — Add two new class members to the header and implement both integrity checks in process_frame_().

### Steps

1. Read `esphome/components/tublemetry_display/tublemetry_display.h` in full.
2. In the `protected:` section, after the existing state-tracking members (`last_confidence_`, etc.), add:
   - `std::string candidate_display_string_;`  — last decoded frame for stability comparison
   - `uint8_t stable_count_{0};`               — consecutive matching frames
   - `static constexpr uint8_t STABLE_THRESHOLD = 3;`  — publish threshold
3. Read `esphome/components/tublemetry_display/tublemetry_display.cpp` in full.
4. In `process_frame_()`, immediately after the digit_bytes[] extraction block (after `digit_bytes[2] = ...` and the commented-out `status` line), extract the actual status byte and add the checksum gate:
   ```cpp
   uint8_t p1 = digit_bytes[0];  // hundreds digit byte (bits 6,3,1,0 always zero in valid frames)
   uint8_t status = frame_bits & 0x07;  // bits 2-0 (p4)
   static constexpr uint8_t CHECKSUM_MASK = 0x4B;  // bits 6,3,1,0 of p1
   if ((p1 & CHECKSUM_MASK) != 0x00 || (status & 0x01) != 0x00) {
     ESP_LOGW(TAG, "Frame checksum failed (p1=0x%02X p4=0x%X), dropping", p1, status);
     return;
   }
   ```
   Note: the existing `// uint8_t status = frame_bits & 0x07;` comment must be replaced with the real extraction used here.
5. After the existing partial-frame drop block (`if (known_count < DIGITS_PER_FRAME) { ... return; }`), add the stability filter:
   ```cpp
   // Stability filter — require STABLE_THRESHOLD consecutive identical decoded frames
   if (display_str == this->candidate_display_string_) {
     if (this->stable_count_ < 255) this->stable_count_++;
   } else {
     this->candidate_display_string_ = display_str;
     this->stable_count_ = 1;
   }
   if (this->stable_count_ < STABLE_THRESHOLD) {
     ESP_LOGD(TAG, "Stability: %d/%d for '%s', holding",
              this->stable_count_, STABLE_THRESHOLD, display_str.c_str());
     return;
   }
   ```
6. Verify the code compiles with `uv run esphome compile esphome/tublemetry.yaml`.
  - Estimate: 45m
  - Files: esphome/components/tublemetry_display/tublemetry_display.h, esphome/components/tublemetry_display/tublemetry_display.cpp
  - Verify: uv run esphome compile esphome/tublemetry.yaml 2>&1 | tail -5
- [x] **T02: Created tests/test_frame_integrity.py with 25 tests mirroring C++ checksum gate and stability filter; 274/274 tests pass, zero regressions** — Write Python tests that mirror the C++ checksum and stability logic, then run the full test suite to confirm no regressions.

### Steps

1. Read `tests/test_mock_frames.py` to understand the available helpers (`frame_to_digits`, `frame_to_display_string`, `digits_to_frame`).
2. Create `tests/test_frame_integrity.py`. The tests mirror the C++ logic in Python — they do not invoke a C++ binary. Import helpers from `test_mock_frames` via direct import (both files are in the `tests/` package).
3. Implement a Python `passes_checksum(frame_bits)` helper that mirrors the C++ gate:
   ```python
   CHECKSUM_MASK = 0x4B
   def passes_checksum(frame_bits: int) -> bool:
       p1 = (frame_bits >> 17) & 0x7F
       p4 = frame_bits & 0x07
       return (p1 & CHECKSUM_MASK) == 0x00 and (p4 & 0x01) == 0x00
   ```
4. Implement a Python `StabilityFilter` class (or simple function) that mirrors the C++ filter:
   ```python
   STABLE_THRESHOLD = 3
   class StabilityFilter:
       def __init__(self): self.candidate = None; self.count = 0
       def feed(self, display_str: str) -> bool:  # returns True if should publish
           if display_str == self.candidate:
               if self.count < 255: self.count += 1
           else:
               self.candidate = display_str; self.count = 1
           return self.count >= STABLE_THRESHOLD
   ```
5. Write checksum tests:
   - `test_checksum_valid_blank`: `digits_to_frame(0x00, 0x7E, 0x79, 0)` → passes (blank hundreds, valid)
   - `test_checksum_valid_1_as_hundreds`: `digits_to_frame(0x30, 0x7E, 0x5B, 0)` → passes (p1='1')
   - `test_checksum_valid_1_variant`: `digits_to_frame(0x34, 0x7E, 0x5B, 0)` → passes (p1='1' alternate encoding)
   - `test_checksum_rejects_zero_display`: `digits_to_frame(0x7E, 0x7E, 0x7E, 0)` → fails (p1=0x7E has bits set in mask)
   - `test_checksum_rejects_startup_dash`: `digits_to_frame(0x01, 0x01, 0x01, 0)` → fails (p1=0x01 has bit0 set in mask)
   - `test_checksum_rejects_p4_bit0`: `digits_to_frame(0x00, 0x7E, 0x79, 1)` → fails (p4 bit0 set)
   - `test_checksum_allows_p4_bit1_bit2`: `digits_to_frame(0x00, 0x7E, 0x79, 6)` → passes (p4 bits 1,2 free)
6. Write stability filter tests:
   - `test_stability_two_frames_hold`: feed same string twice → returns False, False
   - `test_stability_three_frames_publish`: feed same string 3x → False, False, True
   - `test_stability_reset_on_change`: feed 'A' twice then 'B' → False, False, False (reset on 'B')
   - `test_stability_new_streak`: feed 'A' twice, 'B' three times → first B=False, second B=False, third B=True
   - `test_stability_saturation`: feed same string 300 times → count caps at 255, still publishes
7. Run `uv run pytest tests/ --ignore=tests/test_ladder_capture.py -v` and confirm all tests pass (249 + new).
  - Estimate: 30m
  - Files: tests/test_frame_integrity.py, tests/test_mock_frames.py
  - Verify: uv run pytest tests/ --ignore=tests/test_ladder_capture.py -v 2>&1 | tail -10
