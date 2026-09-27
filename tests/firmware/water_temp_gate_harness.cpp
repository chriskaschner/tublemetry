// Host-side harness for esphome/components/tublemetry_display/water_temp_gate.h.
//
// Compiled and driven by tests/test_water_temp_gate.py. Reads one classified
// display frame per line from stdin:
//
//     <millis> <display string, may be blank or contain spaces>
//
// and prints one line per value the gate would publish:
//
//     PUBLISH <millis> <value>
//
// The harness mirrors the call sites in classify_display_state_(): numeric
// frames go to feed_numeric(), every other frame goes to interrupt().

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <string>

#include "water_temp_gate.h"

using esphome::tublemetry_display::WaterTempGate;

static bool is_numeric(const std::string &s) {
  if (s.length() < 2 || s.length() > 3) return false;
  for (char c : s)
    if (c < '0' || c > '9') return false;
  return true;
}

int main() {
  WaterTempGate gate;
  std::string line;
  while (std::getline(std::cin, line)) {
    size_t sp = line.find(' ');
    uint32_t now = static_cast<uint32_t>(std::strtoul(line.substr(0, sp).c_str(), nullptr, 10));
    std::string display = sp == std::string::npos ? "" : line.substr(sp + 1);
    std::string stripped;
    for (char c : display)
      if (c != ' ') stripped += c;

    if (is_numeric(stripped)) {
      float out;
      if (gate.feed_numeric(static_cast<float>(std::atoi(stripped.c_str())), now, &out))
        std::printf("PUBLISH %u %.0f\n", now, out);
    } else {
      gate.interrupt();
    }
  }
  return 0;
}
