// Host-side harness for esphome/components/tublemetry_display/frame_decode.h.
//
// Compiled and driven by tests/test_frame_decode.py. Reads one 24-bit panel
// frame per line from stdin, as hex (e.g. "0x08E7F8"), and prints one line per
// frame:
//
//     <3 decoded chars>|<checksum_ok>|<known>|<heater>|<pump>|<light>
//
// The decoded characters can contain spaces, so fields are '|'-separated.

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <string>

#include "frame_decode.h"

using esphome::tublemetry_display::decode_frame;
using esphome::tublemetry_display::DecodedFrame;

int main() {
  std::string line;
  while (std::getline(std::cin, line)) {
    if (line.empty()) continue;
    uint32_t bits = static_cast<uint32_t>(std::strtoul(line.c_str(), nullptr, 16));
    DecodedFrame f = decode_frame(bits);
    std::printf("%c%c%c|%d|%d|%d|%d|%d\n", f.chars[0], f.chars[1], f.chars[2],
                f.checksum_ok ? 1 : 0, f.known, f.heater ? 1 : 0, f.pump ? 1 : 0,
                f.light ? 1 : 0);
  }
  return 0;
}
