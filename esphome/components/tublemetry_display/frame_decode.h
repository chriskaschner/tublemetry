#pragma once

// Pure decoding of one 24-bit panel frame: three 7-segment digits, the
// checksum, and the heater / pump / light status bits.
//
// Frame layout (MSB first): [digit1:7][digit2:7][digit3:7][status:3]
//   p1 = digit1 byte. Checksum: p1 bits 6,3,1,0 must be 0, status bit 0 must be 0.
//   heater = p1 bit 2, pump = status bit 2, light = status bit 1.
//
// Kept free of ESPHome headers so tests/test_frame_decode.py can compile it on
// the host, the same way tests/test_water_temp_gate.py tests water_temp_gate.h.

#include <cstddef>
#include <cstdint>

namespace esphome {
namespace tublemetry_display {

// 7-segment lookup table entry
struct SegEntry {
  uint8_t segments;  // 7-bit value (dp masked off)
  char character;    // decoded character
};

// 7-segment lookup table.
// Ported from Python src/tublemetry/decode.py SEVEN_SEG_TABLE.
// Segment mapping: bit6=a, bit5=b, bit4=c, bit3=d, bit2=e, bit1=f, bit0=g
// Values are masked to 7 bits (dp bit 7 stripped before lookup).
//
// Format: {hex_value, 'character'}, // status
// Cross-check test (tests/test_cross_check.py) parses this table to verify
// it matches the Python reference.
//
// SEVEN_SEG_TABLE_START
static constexpr SegEntry SEVEN_SEG_TABLE[] = {
    {0x7E, '0'},  // confirmed (ladder capture 2026-03-20)
    {0x30, '1'},  // confirmed (ladder capture 2026-03-20)
    {0x34, '1'},  // confirmed (setpoint display mode — "1" with lower-left foot segment e)
    {0x6D, '2'},  // confirmed (ladder capture 2026-03-20)
    {0x79, '3'},  // confirmed (ladder capture 2026-03-20)
    {0x33, '4'},  // confirmed (ladder capture 2026-03-20)
    {0x5B, '5'},  // confirmed (ladder capture 2026-03-20)
    {0x5F, '6'},  // confirmed (ladder capture 2026-03-20)
    {0x70, '7'},  // confirmed (ladder capture 2026-03-20)
    {0x7F, '8'},  // confirmed (ladder capture 2026-03-20)
    {0x73, '9'},  // confirmed (ladder capture 2026-03-20) -- NOT 0x7B, no bottom segment
    {0x00, ' '},  // confirmed (blank)
    {0x37, 'H'},  // confirmed (OH.csv decode)
    {0x0E, 'L'},  // confirmed (SL mode capture 2026-03-20)
    {0x4F, 'E'},  // confirmed (Ec mode capture 2026-03-20)
    {0x0D, 'c'},  // confirmed (Ec mode capture 2026-03-20)
    {0x0F, 't'},  // confirmed (St mode capture 2026-03-20)
    {0x67, 'P'},  // unverified (GS510SZ reference)
    {0x01, '-'},  // unverified (GS510SZ reference)
    {0x03, '-'},  // unverified (alternate dash encoding)
    {0x05, 'r'},  // unverified (GS510SZ reference)
    {0x1D, 'o'},  // unverified (GS510SZ reference)
};
// SEVEN_SEG_TABLE_END

static constexpr size_t SEVEN_SEG_TABLE_SIZE = sizeof(SEVEN_SEG_TABLE) / sizeof(SEVEN_SEG_TABLE[0]);

static constexpr uint8_t FRAME_DIGITS = 3;
static constexpr uint8_t P1_CHECKSUM_MASK = 0x4B;  // p1 bits 6,3,1,0
static constexpr uint8_t P1_HEATER_BIT = 0x04;     // p1 bit 2

/// Decode a 7-segment byte to its character. Masks off bit 7 (decimal point).
/// Returns '?' for unknown byte patterns.
inline char decode_7seg(uint8_t byte_val) {
  uint8_t segments = byte_val & 0x7F;
  for (size_t i = 0; i < SEVEN_SEG_TABLE_SIZE; i++) {
    if (SEVEN_SEG_TABLE[i].segments == segments) return SEVEN_SEG_TABLE[i].character;
  }
  return '?';
}

struct DecodedFrame {
  uint8_t raw[FRAME_DIGITS];  // digit bytes exactly as received (for raw_hex)
  char chars[FRAME_DIGITS];   // decoded characters, '?' where unknown
  int known;                  // how many of chars are not '?'
  bool checksum_ok;
  bool heater;
  bool pump;
  bool light;
};

inline DecodedFrame decode_frame(uint32_t frame_bits) {
  DecodedFrame f{};
  f.raw[0] = (frame_bits >> 17) & 0x7F;  // bits 23-17 (p1)
  f.raw[1] = (frame_bits >> 10) & 0x7F;  // bits 16-10
  f.raw[2] = (frame_bits >> 3) & 0x7F;   // bits 9-3
  const uint8_t status = frame_bits & 0x07;  // bits 2-0 (p4)

  f.checksum_ok = (f.raw[0] & P1_CHECKSUM_MASK) == 0 && (status & 0x01) == 0;

  // The heater flag lives INSIDE the first digit byte (segment e of digit 1).
  // The checksum leaves digit 1 only segments b, c and e, so it is blank or
  // "1" and segment e is never a real segment there. Strip the flag before the
  // lookup: otherwise blank + heater (0x04) is unknown, the whole frame is
  // dropped as partial, and display / water temp / heater / pump all freeze
  // whenever the heater runs with the water at 99F or below (2026-11-06).
  // "1" + heater (0x34) only ever worked because it had its own table entry.
  f.known = 0;
  for (int i = 0; i < FRAME_DIGITS; i++) {
    const uint8_t seg = i == 0 ? static_cast<uint8_t>(f.raw[i] & ~P1_HEATER_BIT) : f.raw[i];
    f.chars[i] = decode_7seg(seg);
    if (f.chars[i] != '?') f.known++;
  }

  f.heater = (f.raw[0] & P1_HEATER_BIT) != 0;
  f.pump = (status >> 2) & 0x01;
  f.light = (status >> 1) & 0x01;
  return f;
}

}  // namespace tublemetry_display
}  // namespace esphome
