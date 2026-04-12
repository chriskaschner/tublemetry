#include "button_injector.h"
#include "esphome/core/log.h"
#include "esphome/core/hal.h"

#include <cmath>

namespace esphome {
namespace tublemetry_display {

static const char *const TAG = "button_injector";

// --- String helpers ---

const char *ButtonInjector::phase_to_string(InjectorPhase phase) {
  switch (phase) {
    case InjectorPhase::IDLE:       return "idle";
    case InjectorPhase::PROBING:    return "probing";
    case InjectorPhase::ADJUSTING:  return "adjusting";
    case InjectorPhase::VERIFYING:  return "verifying";
    case InjectorPhase::RETRYING:   return "retrying";
    case InjectorPhase::COOLDOWN:   return "cooldown";
    case InjectorPhase::TEST_PRESS: return "test_press";
    case InjectorPhase::REFRESHING: return "refreshing";
    default:                        return "unknown";
  }
}

const char *ButtonInjector::result_to_string(InjectorResult result) {
  switch (result) {
    case InjectorResult::NONE:            return "none";
    case InjectorResult::SUCCESS:         return "success";
    case InjectorResult::TIMEOUT:         return "timeout";
    case InjectorResult::ABORTED:         return "aborted";
    case InjectorResult::FAILED:          return "failed";
    case InjectorResult::BUDGET_EXCEEDED: return "budget_exceeded";
    default:                              return "unknown";
  }
}

// --- Setup ---

void ButtonInjector::setup() {
  if (this->temp_up_pin_ == nullptr || this->temp_down_pin_ == nullptr) {
    ESP_LOGW(TAG, "Button injection pins not configured — read-only mode");
    return;
  }

  this->temp_up_pin_->setup();
  this->temp_down_pin_->setup();

  // Ensure relays start open (pins LOW = relay off for AQY212EH)
  this->temp_up_pin_->digital_write(false);
  this->temp_down_pin_->digital_write(false);

  ESP_LOGI(TAG, "Button injection ready — pins configured");
  ESP_LOGI(TAG, "Timing: press=%dms, gap=%dms, verify_timeout=%dms, cooldown=%dms",
           (int) this->press_duration_ms_, (int) this->inter_press_delay_ms_,
           (int) this->verify_timeout_ms_, (int) this->cooldown_ms_);

  this->publish_state_();
}

// --- Request temperature ---

bool ButtonInjector::request_temperature(float target) {
  if (!this->is_configured()) {
    ESP_LOGW(TAG, "Cannot set temperature — injection pins not configured");
    return false;
  }

  if (this->is_busy()) {
    ESP_LOGW(TAG, "Cannot set temperature — sequence in progress (phase: %s)",
             phase_to_string(this->phase_));
    return false;
  }

  // Safety clamp
  if (target < TEMP_FLOOR || target > TEMP_CEILING) {
    ESP_LOGW(TAG, "Target %.0fF outside safe range (%.0f-%.0fF) — rejected",
             target, TEMP_FLOOR, TEMP_CEILING);
    return false;
  }

  target = roundf(target);
  this->target_temp_ = target;
  this->sequence_count_++;
  this->retry_count_ = 0;
  this->presses_consumed_ = 0;

  if (!std::isnan(this->known_setpoint_)) {
    // Setpoint is known — go directly to adjusting (no probe needed)
    ESP_LOGI(TAG, "Starting sequence #%lu: %.0fF -> %.0fF (known setpoint)",
             (unsigned long) this->sequence_count_,
             this->known_setpoint_, target);
    this->start_adjusting_(this->known_setpoint_);
  } else {
    // Setpoint unknown — probe with one down press to discover it
    ESP_LOGI(TAG, "Starting sequence #%lu: target %.0fF — probing setpoint",
             (unsigned long) this->sequence_count_, target);
    this->probed_setpoint_ = NAN;
    this->transition_to_(InjectorPhase::PROBING);
  }

  return true;
}

// --- Single test press ---

void ButtonInjector::press_once(bool temp_up) {
  if (!this->is_configured()) {
    ESP_LOGW(TAG, "Cannot test press — pins not configured");
    return;
  }
  if (this->is_busy()) {
    ESP_LOGW(TAG, "Cannot test press — sequence in progress (phase: %s)",
             phase_to_string(this->phase_));
    return;
  }
  this->test_press_up_ = temp_up;
  this->known_setpoint_ = NAN;  // test press changes real setpoint — probe on next sequence
  ESP_LOGI(TAG, "Test press: %s (setpoint cache cleared)", temp_up ? "temp_up" : "temp_down");
  this->transition_to_(InjectorPhase::TEST_PRESS);
}

// --- Refresh (net-zero keepalive) ---

void ButtonInjector::refresh() {
  if (!this->is_configured()) {
    ESP_LOGW(TAG, "Cannot refresh — injection pins not configured");
    return;
  }

  if (this->is_busy()) {
    ESP_LOGW(TAG, "Cannot refresh — sequence in progress (phase: %s)",
             phase_to_string(this->phase_));
    return;
  }

  // Set up two presses: first down (presses_remaining_==2), then up (presses_remaining_==1).
  // adjusting_up_ starts false so first press is down.
  // known_setpoint_ is intentionally NOT touched.
  this->presses_remaining_ = 2;
  this->presses_total_ = 2;
  this->adjusting_up_ = false;
  ESP_LOGI(TAG, "Refresh: triggering net-zero REFRESHING phase (down+up)");
  this->transition_to_(InjectorPhase::REFRESHING);
}

// --- start_adjusting_ helper ---

void ButtonInjector::start_adjusting_(float from_setpoint) {
  int delta = static_cast<int>(roundf(this->target_temp_)) - static_cast<int>(roundf(from_setpoint));

  if (delta == 0) {
    // Already at target — skip straight to verify
    ESP_LOGI(TAG, "Already at %.0fF — skipping adjust, verifying", this->target_temp_);
    this->transition_to_(InjectorPhase::VERIFYING);
    return;
  }

  uint8_t abs_delta = static_cast<uint8_t>(std::abs(delta));
  this->press_budget_ = abs_delta + 2;  // D-06: N+2 budget
  this->presses_consumed_ = 0;

  this->adjusting_up_ = (delta > 0);
  this->presses_remaining_ = abs_delta;
  this->presses_total_ = this->presses_remaining_;

  ESP_LOGI(TAG, "Adjusting: %d %s-presses from %.0fF to %.0fF",
           (int) this->presses_total_,
           this->adjusting_up_ ? "up" : "down",
           from_setpoint, this->target_temp_);
  this->transition_to_(InjectorPhase::ADJUSTING);
}

// --- Main loop ---

void ButtonInjector::loop() {
  switch (this->phase_) {
    case InjectorPhase::IDLE:
      return;
    case InjectorPhase::PROBING:
      this->loop_probing_();
      break;
    case InjectorPhase::ADJUSTING:
      this->loop_adjusting_();
      break;
    case InjectorPhase::VERIFYING:
      this->loop_verifying_();
      break;
    case InjectorPhase::RETRYING:
      this->loop_retrying_();
      break;
    case InjectorPhase::COOLDOWN:
      this->loop_cooldown_();
      break;
    case InjectorPhase::TEST_PRESS:
      this->loop_test_press_();
      break;
    case InjectorPhase::REFRESHING:
      this->loop_refreshing_();
      break;
  }
}

// --- Phase loops ---

void ButtonInjector::loop_probing_() {
  uint32_t now = millis();
  uint32_t elapsed = now - this->last_action_ms_;

  if (this->pin_active_) {
    // Press is active — wait for press duration then release
    if (elapsed >= this->press_duration_ms_) {
      this->release_pin_(this->temp_down_pin_);
      this->pin_active_ = false;
      this->last_action_ms_ = now;
    }
  } else if (std::isnan(this->probed_setpoint_)) {
    if (elapsed < this->inter_press_delay_ms_) {
      // Still waiting after release for display to update
      return;
    }

    // Time to fire the probe press or read the result
    if (this->phase_start_ms_ == this->last_action_ms_) {
      // Haven't pressed yet — fire the probe down press
      this->press_pin_(this->temp_down_pin_);
      this->pin_active_ = true;
      this->last_action_ms_ = now;
    } else {
      // Press has been released and we've waited — read the display
      if (!std::isnan(this->last_display_temp_)) {
        // Display shows the new setpoint (old - 1) after our down press
        this->probed_setpoint_ = this->last_display_temp_;
        ESP_LOGI(TAG, "Probed setpoint: %.0fF (display after down press)", this->probed_setpoint_);
        this->start_adjusting_(this->probed_setpoint_);
      } else {
        // No display reading yet — keep waiting (verify timeout will catch runaway)
        uint32_t total_elapsed = now - this->phase_start_ms_;
        if (total_elapsed >= this->verify_timeout_ms_) {
          this->finish_sequence_(InjectorResult::TIMEOUT, "probe: no display reading");
        }
      }
    }
  }
}

void ButtonInjector::loop_adjusting_() {
  uint32_t now = millis();
  uint32_t elapsed = now - this->last_action_ms_;
  GPIOPin *pin = this->adjusting_up_ ? this->temp_up_pin_ : this->temp_down_pin_;

  if (this->pin_active_) {
    if (elapsed >= this->press_duration_ms_) {
      this->release_pin_(pin);
      this->pin_active_ = false;
      this->last_action_ms_ = now;
      this->presses_remaining_--;
      this->presses_consumed_++;

      // D-06: Budget enforcement
      if (this->presses_consumed_ > this->press_budget_) {
        ESP_LOGW(TAG, "Press budget exceeded (%d/%d) -- aborting attempt",
                 (int)this->presses_consumed_, (int)this->press_budget_);
        this->release_all_pins_();
        this->attempt_failed_(/* budget_exceeded = */ true);
        return;
      }

      uint8_t completed = this->presses_total_ - this->presses_remaining_;
      ESP_LOGD(TAG, "Adjust press %d/%d complete (%s)",
               (int) completed, (int) this->presses_total_,
               this->adjusting_up_ ? "up" : "down");

      if (this->presses_remaining_ == 0) {
        ESP_LOGI(TAG, "Adjust complete — verifying display shows %.0fF", this->target_temp_);
        this->transition_to_(InjectorPhase::VERIFYING);
      }
    }
  } else {
    if (elapsed >= this->inter_press_delay_ms_) {
      this->press_pin_(pin);
      this->pin_active_ = true;
      this->last_action_ms_ = now;
    }
  }
}

void ButtonInjector::loop_verifying_() {
  uint32_t now = millis();
  uint32_t elapsed = now - this->phase_start_ms_;

  if (!std::isnan(this->last_display_temp_) &&
      this->last_display_temp_ == this->target_temp_) {
    ESP_LOGI(TAG, "Verified: display shows %.0fF — sequence successful", this->target_temp_);
    this->finish_sequence_(InjectorResult::SUCCESS);
    return;
  }

  if (elapsed >= this->verify_timeout_ms_) {
    ESP_LOGW(TAG, "Verification timeout after %dms — display shows %.0fF, expected %.0fF",
             (int) elapsed,
             std::isnan(this->last_display_temp_) ? -1.0f : this->last_display_temp_,
             this->target_temp_);
    this->finish_sequence_(InjectorResult::TIMEOUT, "verification timeout");
  }
}

void ButtonInjector::loop_cooldown_() {
  uint32_t now = millis();
  uint32_t elapsed = now - this->phase_start_ms_;

  if (elapsed >= this->cooldown_ms_) {
    ESP_LOGD(TAG, "Cooldown complete — ready for next sequence");
    this->transition_to_(InjectorPhase::IDLE);
  }
}

void ButtonInjector::loop_test_press_() {
  uint32_t now = millis();
  uint32_t elapsed = now - this->last_action_ms_;
  GPIOPin *pin = this->test_press_up_ ? this->temp_up_pin_ : this->temp_down_pin_;

  if (this->pin_active_) {
    if (elapsed >= this->press_duration_ms_) {
      this->release_pin_(pin);
      this->pin_active_ = false;
      ESP_LOGI(TAG, "Test press complete (%s)", this->test_press_up_ ? "up" : "down");
      this->transition_to_(InjectorPhase::COOLDOWN);
    }
  } else {
    if (elapsed >= this->inter_press_delay_ms_) {
      this->press_pin_(pin);
      this->pin_active_ = true;
      this->last_action_ms_ = now;
    }
  }
}

// --- Retry logic ---

void ButtonInjector::loop_retrying_() {
  uint32_t now = millis();
  uint32_t elapsed = now - this->phase_start_ms_;

  if (elapsed >= this->retry_backoff_ms_) {
    ESP_LOGI(TAG, "Retry %d/%d: backoff complete (%dms), re-probing",
             (int)this->retry_count_, (int)this->max_retries_,
             (int)this->retry_backoff_ms_);
    // D-01: Always re-probe from scratch -- invalidate cache
    this->known_setpoint_ = NAN;
    this->probed_setpoint_ = NAN;
    this->transition_to_(InjectorPhase::PROBING);
  }
}

void ButtonInjector::attempt_failed_(bool budget_exceeded) {
  if (this->retry_count_ < this->max_retries_) {
    this->retry_count_++;
    this->retry_backoff_ms_ = this->calculate_backoff_ms_(this->retry_count_);
    ESP_LOGW(TAG, "Attempt failed (%s) -- retry %d/%d in %dms",
             budget_exceeded ? "budget exceeded" : "timeout",
             (int)this->retry_count_, (int)this->max_retries_,
             (int)this->retry_backoff_ms_);
    this->known_setpoint_ = NAN;  // D-01
    this->transition_to_(InjectorPhase::RETRYING);
  } else {
    ESP_LOGE(TAG, "All %d retries exhausted -- marking FAILED",
             (int)this->max_retries_);
    this->finish_sequence_(InjectorResult::FAILED,
                           budget_exceeded ? "budget exceeded, retries exhausted"
                                           : "timeout, retries exhausted");
  }
}

uint32_t ButtonInjector::calculate_backoff_ms_(uint8_t retry_num) {
  // D-03: 5s, 15s, 45s exponential backoff
  static const uint32_t BACKOFF_TABLE[] = {5000, 15000, 45000};
  if (retry_num == 0 || retry_num > 3) return 5000;
  return BACKOFF_TABLE[retry_num - 1];
}

// --- Feed display temperature ---

void ButtonInjector::loop_refreshing_() {
  uint32_t now = millis();
  uint32_t elapsed = now - this->last_action_ms_;

  // Direction: first press (presses_remaining_==2) is DOWN, second (presses_remaining_==1) is UP.
  // adjusting_up_ starts false (set in refresh()); flip to true after first press completes.
  GPIOPin *pin = this->adjusting_up_ ? this->temp_up_pin_ : this->temp_down_pin_;

  if (this->pin_active_) {
    if (elapsed >= this->press_duration_ms_) {
      this->release_pin_(pin);
      this->pin_active_ = false;
      this->last_action_ms_ = now;
      this->presses_remaining_--;

      ESP_LOGD(TAG, "Refresh press complete (%s), %d remaining",
               this->adjusting_up_ ? "up" : "down",
               (int) this->presses_remaining_);

      if (this->presses_remaining_ == 0) {
        ESP_LOGI(TAG, "Refresh complete -- net-zero, transitioning to COOLDOWN");
        // known_setpoint_ is intentionally NOT modified here
        this->transition_to_(InjectorPhase::COOLDOWN);
        return;
      }

      // Flip direction for the next press (down->up)
      this->adjusting_up_ = !this->adjusting_up_;
    }
  } else {
    if (elapsed >= this->inter_press_delay_ms_) {
      // Re-read pin after possible direction flip
      GPIOPin *next_pin = this->adjusting_up_ ? this->temp_up_pin_ : this->temp_down_pin_;
      this->press_pin_(next_pin);
      this->pin_active_ = true;
      this->last_action_ms_ = now;
    }
  }
}

void ButtonInjector::feed_display_temperature(float temp) {
  this->last_display_temp_ = temp;
}

// --- Abort ---

void ButtonInjector::abort() {
  if (this->phase_ == InjectorPhase::IDLE) {
    return;
  }

  ESP_LOGW(TAG, "Aborting sequence in phase: %s", phase_to_string(this->phase_));
  this->release_all_pins_();
  this->finish_sequence_(InjectorResult::ABORTED, "manually aborted");
}

// --- Internal helpers ---

void ButtonInjector::transition_to_(InjectorPhase new_phase) {
  ESP_LOGD(TAG, "Phase: %s -> %s", phase_to_string(this->phase_), phase_to_string(new_phase));
  this->phase_ = new_phase;
  this->phase_start_ms_ = millis();
  this->last_action_ms_ = millis();
  this->pin_active_ = false;
  this->publish_state_();
}

void ButtonInjector::press_pin_(GPIOPin *pin) {
  if (pin != nullptr) {
    pin->digital_write(true);
  }
}

void ButtonInjector::release_pin_(GPIOPin *pin) {
  if (pin != nullptr) {
    pin->digital_write(false);
  }
}

void ButtonInjector::release_all_pins_() {
  this->release_pin_(this->temp_up_pin_);
  this->release_pin_(this->temp_down_pin_);
  this->pin_active_ = false;
}

void ButtonInjector::publish_state_() {
  if (this->injection_state_sensor_ != nullptr) {
    std::string state = phase_to_string(this->phase_);
    if (this->phase_ != InjectorPhase::IDLE && this->target_temp_ > 0) {
      char buf[32];
      snprintf(buf, sizeof(buf), "%s:%.0f", state.c_str(), this->target_temp_);
      state = std::string(buf);
    }
    this->injection_state_sensor_->publish_state(state);
  }

  // injection_phase sensor (clean phase name without target suffix)
  if (this->injection_phase_sensor_ != nullptr) {
    this->injection_phase_sensor_->publish_state(phase_to_string(this->phase_));
  }

  // retry_count sensor
  if (this->retry_count_sensor_ != nullptr) {
    this->retry_count_sensor_->publish_state(static_cast<float>(this->retry_count_));
  }
}

void ButtonInjector::finish_sequence_(InjectorResult result, const std::string &error) {
  this->release_all_pins_();
  this->last_result_ = result;
  this->last_error_ = error;

  if (result == InjectorResult::SUCCESS) {
    this->success_count_++;
    this->known_setpoint_ = this->target_temp_;
    this->last_confirmed_setpoint_ = this->target_temp_;

    // D-14: Publish confirmed setpoint
    if (this->setpoint_number_ != nullptr) {
      this->setpoint_number_->publish_state(this->target_temp_);
    }
  } else if (result == InjectorResult::TIMEOUT || result == InjectorResult::BUDGET_EXCEEDED) {
    // Route through retry logic
    this->known_setpoint_ = NAN;
    this->attempt_failed_(result == InjectorResult::BUDGET_EXCEEDED);
    // attempt_failed_ handles transition (RETRYING or COOLDOWN+FAILED)

    // Publish result sensor
    if (this->last_command_result_sensor_ != nullptr) {
      this->last_command_result_sensor_->publish_state(result_to_string(this->last_result_));
    }
    return;  // attempt_failed_ already handled transition
  } else if (result == InjectorResult::FAILED) {
    this->known_setpoint_ = NAN;

    // D-14: Revert setpoint to last known on FAILED
    if (this->setpoint_number_ != nullptr && !std::isnan(this->last_confirmed_setpoint_)) {
      this->setpoint_number_->publish_state(this->last_confirmed_setpoint_);
    }
  } else {
    // ABORTED
    this->known_setpoint_ = NAN;
  }

  ESP_LOGI(TAG, "Sequence #%lu finished: %s (total: %lu success, %lu total)",
           (unsigned long) this->sequence_count_,
           result_to_string(result),
           (unsigned long) this->success_count_,
           (unsigned long) this->sequence_count_);

  if (!error.empty()) {
    ESP_LOGW(TAG, "Last error: %s", error.c_str());
  }

  // Publish result sensor
  if (this->last_command_result_sensor_ != nullptr) {
    this->last_command_result_sensor_->publish_state(result_to_string(result));
  }

  this->transition_to_(InjectorPhase::COOLDOWN);
}

}  // namespace tublemetry_display
}  // namespace esphome
