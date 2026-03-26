#pragma once

#include "esphome/core/component.h"
#include "esphome/core/gpio.h"
#include "esphome/components/text_sensor/text_sensor.h"

#include <string>

namespace esphome {
namespace tublemetry_display {

/// State machine phases for button injection sequence.
enum class InjectorPhase : uint8_t {
  IDLE = 0,       // No sequence in progress
  REHOMING,       // Pressing temp_down to reach floor (80F)
  ADJUSTING,      // Pressing temp_up to reach target
  VERIFYING,      // Waiting for display stream to confirm setpoint
  COOLDOWN,       // Brief pause after sequence before accepting new requests
  TEST_PRESS,     // Single raw press for hardware testing (bypasses re-home)
};

/// Result of the last completed sequence.
enum class InjectorResult : uint8_t {
  NONE = 0,       // No sequence has run yet
  SUCCESS,        // Display confirmed target temperature
  TIMEOUT,        // Verification timed out waiting for display confirmation
  ABORTED,        // Sequence was aborted (e.g. new request while verifying)
};

/// Non-blocking button injection via photorelay GPIO outputs.
///
/// Implements the "re-home" strategy:
///   1. Press temp_down 25 times to guarantee floor (80F)
///   2. Press temp_up N times where N = (target - 80)
///   3. Wait for display stream to confirm the setpoint
///
/// All timing is non-blocking — call loop() from the parent component's loop.
class ButtonInjector {
 public:
  // --- Configuration (called from codegen) ---
  void set_temp_up_pin(GPIOPin *pin) { this->temp_up_pin_ = pin; }
  void set_temp_down_pin(GPIOPin *pin) { this->temp_down_pin_ = pin; }

  /// Press duration in milliseconds (how long the relay closes).
  void set_press_duration_ms(uint32_t ms) { this->press_duration_ms_ = ms; }

  /// Delay between presses in milliseconds (relay open between presses).
  void set_inter_press_delay_ms(uint32_t ms) { this->inter_press_delay_ms_ = ms; }

  /// Verification timeout in milliseconds (how long to wait for display confirmation).
  void set_verify_timeout_ms(uint32_t ms) { this->verify_timeout_ms_ = ms; }

  /// Cooldown period after sequence completes before accepting new requests.
  void set_cooldown_ms(uint32_t ms) { this->cooldown_ms_ = ms; }

  // --- Diagnostic sensor setters ---
  void set_injection_state_sensor(text_sensor::TextSensor *s) { this->injection_state_sensor_ = s; }

  // --- Setup (called once from parent setup) ---
  void setup();

  // --- Runtime ---

  /// Request a temperature change. Returns true if accepted, false if rejected
  /// (out of range, sequence in progress, no pins configured).
  bool request_temperature(float target);

  /// Fire a single raw button press for hardware validation. Only works when IDLE.
  void press_once(bool temp_up);

  /// Drive the state machine. Call every loop() iteration.
  void loop();

  /// Feed the current display temperature from the decode pipeline.
  /// Used during VERIFYING phase to confirm the setpoint was reached.
  void feed_display_temperature(float temp);

  /// Abort any in-progress sequence and return to IDLE.
  void abort();

  // --- Status queries ---
  InjectorPhase phase() const { return this->phase_; }
  InjectorResult last_result() const { return this->last_result_; }
  float target_temperature() const { return this->target_temp_; }
  bool is_busy() const { return this->phase_ != InjectorPhase::IDLE; }
  bool is_configured() const { return this->temp_up_pin_ != nullptr && this->temp_down_pin_ != nullptr; }

  // --- Constants ---
  static constexpr float TEMP_FLOOR = 80.0f;
  static constexpr float TEMP_CEILING = 104.0f;
  static constexpr uint8_t REHOME_PRESSES = 25;

  // --- String helpers ---
  static const char *phase_to_string(InjectorPhase phase);
  static const char *result_to_string(InjectorResult result);

 protected:
  // GPIO pins (nullptr = not configured = read-only mode)
  GPIOPin *temp_up_pin_{nullptr};
  GPIOPin *temp_down_pin_{nullptr};

  // Timing configuration (defaults)
  uint32_t press_duration_ms_{200};
  uint32_t inter_press_delay_ms_{300};
  uint32_t verify_timeout_ms_{10000};
  uint32_t cooldown_ms_{1000};

  // State machine
  InjectorPhase phase_{InjectorPhase::IDLE};
  InjectorResult last_result_{InjectorResult::NONE};

  // Sequence state
  float target_temp_{0.0f};
  uint8_t presses_remaining_{0};
  uint8_t presses_total_{0};
  bool pin_active_{false};         // true = relay is currently closed (button pressed)
  bool test_press_up_{false};      // direction for TEST_PRESS phase
  uint32_t phase_start_ms_{0};     // millis() when current phase began
  uint32_t last_action_ms_{0};     // millis() of last pin state change
  float last_verified_temp_{NAN};  // last temperature fed from display during verify

  // Diagnostics
  uint32_t sequence_count_{0};
  uint32_t success_count_{0};
  std::string last_error_;

  // Diagnostic sensors
  text_sensor::TextSensor *injection_state_sensor_{nullptr};

  // Internal methods
  void transition_to_(InjectorPhase new_phase);
  void loop_rehoming_();
  void loop_adjusting_();
  void loop_verifying_();
  void loop_cooldown_();
  void loop_test_press_();
  void press_pin_(GPIOPin *pin);
  void release_pin_(GPIOPin *pin);
  void release_all_pins_();
  void publish_state_();
  void finish_sequence_(InjectorResult result, const std::string &error = "");
};

}  // namespace tublemetry_display
}  // namespace esphome
