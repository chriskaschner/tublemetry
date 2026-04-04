---
estimated_steps: 35
estimated_files: 2
skills_used: []
---

# T01: Add checksum gate and stability filter to process_frame_()

Add two new class members to the header and implement both integrity checks in process_frame_().

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

## Inputs

- ``esphome/components/tublemetry_display/tublemetry_display.h` — existing class definition to extend`
- ``esphome/components/tublemetry_display/tublemetry_display.cpp` — process_frame_() implementation to modify`

## Expected Output

- ``esphome/components/tublemetry_display/tublemetry_display.h` — updated with candidate_display_string_, stable_count_, STABLE_THRESHOLD`
- ``esphome/components/tublemetry_display/tublemetry_display.cpp` — process_frame_() with checksum gate and stability filter`

## Verification

uv run esphome compile esphome/tublemetry.yaml 2>&1 | tail -5

## Observability Impact

ESP_LOGW emitted for each checksum-failed frame (p1 and p4 values). ESP_LOGD emitted for each stability-held frame (count, threshold, display string). Both signals are grep-able from the ESPHome log stream.
