#include "tublemetry_setpoint.h"
#include "esphome/core/log.h"

namespace esphome {
namespace tublemetry_display {

static const char *const TAG = "tublemetry_setpoint";

void TublemetrySetpoint::control(float value) {
  // D-14: Do NOT publish_state here -- wait for injection result
  this->pending_target_ = value;
  this->last_confirmed_setpoint_ = this->state;  // Capture current state for revert

  if (this->injector_ != nullptr && this->injector_->is_configured()) {
    // Pass last_confirmed_setpoint to injector for revert on FAILED
    this->injector_->set_last_confirmed_setpoint(this->last_confirmed_setpoint_);

    if (!this->injector_->request_temperature(value)) {
      ESP_LOGW(TAG, "Setpoint request rejected: %.0fF", value);
      // Request rejected -- publish current state back (no change)
      if (!std::isnan(this->state)) {
        this->publish_state(this->state);
      }
    }
  } else {
    // No injector or not configured -- publish directly (read-only mode)
    this->publish_state(value);
  }
}

}  // namespace tublemetry_display
}  // namespace esphome
