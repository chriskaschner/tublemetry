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
    case InjectorPhase::IDLE:      return "idle";
    case InjectorPhase::REHOMING:  return "rehoming";
    case InjectorPhase::ADJUSTING: return "adjusting";
    case InjectorPhase::VERIFYING: return "verifying";
    case InjectorPhase::COOLDOWN:  return "cooldown";
    default:                       return "unknown";
  }
}

const char *ButtonInjector::result_to_string(InjectorResult result) {
  switch (result) {
    case InjectorResult::NONE:    return "none";
    case InjectorResult::SUCCESS: return "success";
    case InjectorResult::TIMEOUT: return "timeout";
    case InjectorResult::ABORTED: return "aborted";
    default:                      return "unknown";
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

  // Round to nearest integer (tub only supports whole degrees)
  target = roundf(target);

  this->target_temp_ = target;
  this->sequence_count_++;

  uint8_t up_presses = static_cast<uint8_t>(target - TEMP_FLOOR);
  ESP_LOGI(TAG, "Starting sequence #%lu: target %.0fF — %d down + %d up presses",
           (unsigned long) this->sequence_count_, target,
           (int) REHOME_PRESSES, (int) up_presses);

  // Begin rehoming phase
  this->presses_remaining_ = REHOME_PRESSES;
  this->presses_total_ = REHOME_PRESSES;
  this->transition_to_(InjectorPhase::REHOMING);

  return true;
}

// --- Main loop ---

void ButtonInjector::loop() {
  switch (this->phase_) {
    case InjectorPhase::IDLE:
      return;  // Nothing to do
    case InjectorPhase::REHOMING:
      this->loop_rehoming_();
      break;
    case InjectorPhase::ADJUSTING:
      this->loop_adjusting_();
      break;
    case InjectorPhase::VERIFYING:
      this->loop_verifying_();
      break;
    case InjectorPhase::COOLDOWN:
      this->loop_cooldown_();
      break;
  }
}

// --- Phase loops ---

void ButtonInjector::loop_rehoming_() {
  uint32_t now = millis();
  uint32_t elapsed = now - this->last_action_ms_;

  if (this->pin_active_) {
    // Pin is pressed — wait for press duration then release
    if (elapsed >= this->press_duration_ms_) {
      this->release_pin_(this->temp_down_pin_);
      this->pin_active_ = false;
      this->last_action_ms_ = now;
      this->presses_remaining_--;

      uint8_t completed = this->presses_total_ - this->presses_remaining_;
      ESP_LOGD(TAG, "Rehome press %d/%d complete", (int) completed, (int) this->presses_total_);

      if (this->presses_remaining_ == 0) {
        // Rehoming done — move to adjusting
        uint8_t up_presses = static_cast<uint8_t>(this->target_temp_ - TEMP_FLOOR);
        if (up_presses == 0) {
          // Target is floor — skip adjusting, go straight to verify
          ESP_LOGI(TAG, "Target is floor (%.0fF) — skipping adjust phase", TEMP_FLOOR);
          this->transition_to_(InjectorPhase::VERIFYING);
        } else {
          this->presses_remaining_ = up_presses;
          this->presses_total_ = up_presses;
          ESP_LOGI(TAG, "Rehome complete — adjusting: %d up-presses to %.0fF",
                   (int) up_presses, this->target_temp_);
          this->transition_to_(InjectorPhase::ADJUSTING);
        }
      }
    }
  } else {
    // Pin is released — wait for inter-press delay then press again
    if (elapsed >= this->inter_press_delay_ms_) {
      this->press_pin_(this->temp_down_pin_);
      this->pin_active_ = true;
      this->last_action_ms_ = now;
    }
  }
}

void ButtonInjector::loop_adjusting_() {
  uint32_t now = millis();
  uint32_t elapsed = now - this->last_action_ms_;

  if (this->pin_active_) {
    // Pin is pressed — wait for press duration then release
    if (elapsed >= this->press_duration_ms_) {
      this->release_pin_(this->temp_up_pin_);
      this->pin_active_ = false;
      this->last_action_ms_ = now;
      this->presses_remaining_--;

      uint8_t completed = this->presses_total_ - this->presses_remaining_;
      ESP_LOGD(TAG, "Adjust press %d/%d complete", (int) completed, (int) this->presses_total_);

      if (this->presses_remaining_ == 0) {
        // Adjusting done — move to verify
        ESP_LOGI(TAG, "Adjust complete — verifying display shows %.0fF", this->target_temp_);
        this->transition_to_(InjectorPhase::VERIFYING);
      }
    }
  } else {
    // Pin is released — wait for inter-press delay then press again
    if (elapsed >= this->inter_press_delay_ms_) {
      this->press_pin_(this->temp_up_pin_);
      this->pin_active_ = true;
      this->last_action_ms_ = now;
    }
  }
}

void ButtonInjector::loop_verifying_() {
  uint32_t now = millis();
  uint32_t elapsed = now - this->phase_start_ms_;

  // Check if display has confirmed our target
  if (!std::isnan(this->last_verified_temp_) &&
      this->last_verified_temp_ == this->target_temp_) {
    ESP_LOGI(TAG, "Verified: display shows %.0fF — sequence successful", this->target_temp_);
    this->finish_sequence_(InjectorResult::SUCCESS);
    return;
  }

  // Check timeout
  if (elapsed >= this->verify_timeout_ms_) {
    ESP_LOGW(TAG, "Verification timeout after %dms — display shows %.0fF, expected %.0fF",
             (int) elapsed,
             std::isnan(this->last_verified_temp_) ? -1.0f : this->last_verified_temp_,
             this->target_temp_);
    this->finish_sequence_(InjectorResult::TIMEOUT, "verification timeout");
    return;
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

// --- Feed display temperature ---

void ButtonInjector::feed_display_temperature(float temp) {
  this->last_verified_temp_ = temp;
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
}

void ButtonInjector::finish_sequence_(InjectorResult result, const std::string &error) {
  this->release_all_pins_();
  this->last_result_ = result;
  this->last_error_ = error;

  if (result == InjectorResult::SUCCESS) {
    this->success_count_++;
  }

  ESP_LOGI(TAG, "Sequence #%lu finished: %s (total: %lu success, %lu total)",
           (unsigned long) this->sequence_count_,
           result_to_string(result),
           (unsigned long) this->success_count_,
           (unsigned long) this->sequence_count_);

  if (!error.empty()) {
    ESP_LOGW(TAG, "Last error: %s", error.c_str());
  }

  // Enter cooldown before accepting new requests
  this->transition_to_(InjectorPhase::COOLDOWN);
}

}  // namespace tublemetry_display
}  // namespace esphome
