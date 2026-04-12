#pragma once

#include "esphome/core/component.h"
#include "esphome/core/gpio.h"
#include "esphome/components/text_sensor/text_sensor.h"
#include "esphome/components/number/number.h"
#include "esphome/components/sensor/sensor.h"

#include <string>

namespace esphome {
namespace tublemetry_display {

/// State machine phases for button injection sequence.
enum class InjectorPhase : uint8_t {
  IDLE = 0,       // No sequence in progress
  PROBING,        // One down press to reveal current setpoint from display
  ADJUSTING,      // Pressing up or down to reach target from known setpoint
  VERIFYING,      // Waiting for display stream to confirm setpoint
  RETRYING,       // Backoff wait before re-probe attempt
  COOLDOWN,       // Brief pause after sequence before accepting new requests
  TEST_PRESS,     // Single raw press for hardware testing (bypasses sequence)
  REFRESHING,     // Net-zero two-press sequence (down then up) to force setpoint flash
};

/// Result of the last completed sequence.
enum class InjectorResult : uint8_t {
  NONE = 0,           // No sequence has run yet
  SUCCESS,            // Display confirmed target temperature
  TIMEOUT,            // Verification timed out waiting for display confirmation
  ABORTED,            // Sequence was aborted (e.g. new request while verifying)
  FAILED,             // All retries exhausted
  BUDGET_EXCEEDED,    // Attempt exceeded press budget (triggers retry)
};

/// Non-blocking button injection via photorelay GPIO outputs.
///
/// Strategy:
///   - If the current setpoint is known (cached from last success): calculate
///     the exact delta and press up or down accordingly. No sweep.
///   - If the setpoint is unknown (first boot or reset): press down once to
///     reveal the setpoint on the display (PROBING), then adjust from there.
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
  void set_last_command_result_sensor(text_sensor::TextSensor *s) { this->last_command_result_sensor_ = s; }
  void set_injection_phase_sensor(text_sensor::TextSensor *s) { this->injection_phase_sensor_ = s; }
  void set_retry_count_sensor(sensor::Sensor *s) { this->retry_count_sensor_ = s; }

  // --- Deferred setpoint publish (D-14) ---
  void set_setpoint_number(number::Number *n) { this->setpoint_number_ = n; }
  void set_last_confirmed_setpoint(float sp) { this->last_confirmed_setpoint_ = sp; }

  // --- Setup (called once from parent setup) ---
  void setup();

  // --- Runtime ---

  /// Request a temperature change. Returns true if accepted, false if rejected
  /// (out of range, sequence in progress, no pins configured).
  bool request_temperature(float target);

  /// Fire a single raw button press for hardware validation. Only works when IDLE.
  void press_once(bool temp_up);

  /// Fire a net-zero two-press sequence (down then up) to force the display to flash
  /// the current setpoint. Rejected if busy or not configured. Does NOT modify
  /// known_setpoint_. Use for auto-refresh keepalive.
  void refresh();

  /// Drive the state machine. Call every loop() iteration.
  void loop();

  /// Feed the current display temperature from the decode pipeline.
  /// Used during PROBING and VERIFYING to read the current setpoint.
  void feed_display_temperature(float temp);

  /// Abort any in-progress sequence and return to IDLE.
  void abort();

  /// Feed the display-detected setpoint so PROBING phase can be skipped.
  void set_known_setpoint(float sp) { this->known_setpoint_ = sp; }

  // --- Status queries ---
  InjectorPhase phase() const { return this->phase_; }
  InjectorResult last_result() const { return this->last_result_; }
  float target_temperature() const { return this->target_temp_; }
  bool is_busy() const { return this->phase_ != InjectorPhase::IDLE; }
  bool is_configured() const { return this->temp_up_pin_ != nullptr && this->temp_down_pin_ != nullptr; }

  // --- Constants ---
  static constexpr float TEMP_FLOOR = 80.0f;
  static constexpr float TEMP_CEILING = 104.0f;

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
  float known_setpoint_{NAN};      // cached setpoint after successful sequences; NAN = unknown
  uint8_t presses_remaining_{0};
  uint8_t presses_total_{0};
  bool pin_active_{false};         // true = relay is currently closed (button pressed)
  bool adjusting_up_{true};        // direction for ADJUSTING phase
  bool test_press_up_{false};      // direction for TEST_PRESS phase
  uint32_t phase_start_ms_{0};     // millis() when current phase began
  uint32_t last_action_ms_{0};     // millis() of last pin state change
  float last_display_temp_{NAN};   // last temperature fed from display stream
  float probed_setpoint_{NAN};     // setpoint captured during PROBING phase

  // Diagnostics
  uint32_t sequence_count_{0};
  uint32_t success_count_{0};
  std::string last_error_;

  // Retry state
  uint8_t retry_count_{0};
  uint8_t max_retries_{3};          // D-02: 3 retries = 4 total attempts
  uint32_t retry_backoff_ms_{0};    // Current backoff delay

  // Press budget (D-06)
  uint8_t press_budget_{0};         // N+2 for current attempt
  uint8_t presses_consumed_{0};     // Presses fired in current ADJUSTING phase

  // Deferred setpoint publish (D-14)
  number::Number *setpoint_number_{nullptr};
  float last_confirmed_setpoint_{NAN};

  // Diagnostic sensors
  text_sensor::TextSensor *injection_state_sensor_{nullptr};
  text_sensor::TextSensor *last_command_result_sensor_{nullptr};
  text_sensor::TextSensor *injection_phase_sensor_{nullptr};
  sensor::Sensor *retry_count_sensor_{nullptr};

  // Internal methods
  void transition_to_(InjectorPhase new_phase);
  void start_adjusting_(float from_setpoint);
  void loop_probing_();
  void loop_adjusting_();
  void loop_verifying_();
  void loop_retrying_();
  void loop_cooldown_();
  void loop_test_press_();
  void loop_refreshing_();
  void press_pin_(GPIOPin *pin);
  void release_pin_(GPIOPin *pin);
  void release_all_pins_();
  void publish_state_();
  void finish_sequence_(InjectorResult result, const std::string &error = "");
  void attempt_failed_(bool budget_exceeded);
  uint32_t calculate_backoff_ms_(uint8_t retry_num);
};

}  // namespace tublemetry_display
}  // namespace esphome
