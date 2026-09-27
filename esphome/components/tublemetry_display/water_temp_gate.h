#pragma once

// Decides which numeric display frames are real water temperature.
//
// The panel shows the same digits for water temperature and for setpoint
// flashes, so the value alone cannot tell them apart. Duration can: a setpoint
// flash alternates with a blank frame about every 0.5 s, while real water
// temperature holds for minutes. A value is published only after it has been
// shown continuously for STABLE_MS with no interrupting frame.
//
// This replaces relying on in_set_mode_ for the temperature sensor. A flash
// begins with a value frame BEFORE the first blank, so in_set_mode_ is still
// false for it; that frame used to be published as water temperature (HA saw
// 90.0 at 2026-09-27 10:00:01 and 80.0 at 2026-09-26 02:21:32).
//
// Kept free of ESPHome headers so tests/test_water_temp_gate.py can compile it
// on the host.

#include <cmath>
#include <cstdint>

namespace esphome {
namespace tublemetry_display {

class WaterTempGate {
 public:
  // Longer than SET_MODE_TIMEOUT_MS (2000) and several flash periods, far
  // shorter than any real temperature change (fastest observed: ~1F / 13 min).
  static constexpr uint32_t STABLE_MS = 3000;

  // Feed every classified numeric frame. Returns true, with the value in *out,
  // when a newly qualified value should be published. Each value is published
  // once; an unchanged reading after an interruption is not re-sent.
  bool feed_numeric(float temp, uint32_t now_ms, float *out) {
    if (std::isnan(this->candidate_) || temp != this->candidate_) {
      this->candidate_ = temp;
      this->since_ms_ = now_ms;
      return false;
    }
    // Unsigned subtraction stays correct across the millis() wrap.
    if (now_ms - this->since_ms_ < STABLE_MS)
      return false;
    if (!std::isnan(this->published_) && temp == this->published_)
      return false;
    this->published_ = temp;
    *out = temp;
    return true;
  }

  // Feed every non-numeric frame (blank, OH, Ec, ...). Breaks the current run.
  void interrupt() { this->candidate_ = NAN; }

 protected:
  float candidate_{NAN};
  uint32_t since_ms_{0};
  float published_{NAN};
};

}  // namespace tublemetry_display
}  // namespace esphome
