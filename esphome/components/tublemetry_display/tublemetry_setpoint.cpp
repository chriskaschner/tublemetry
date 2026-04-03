#include "tublemetry_setpoint.h"
#include "esphome/core/log.h"

namespace esphome {
namespace tublemetry_display {

static const char *const TAG = "tublemetry_setpoint";

void TublemetrySetpoint::control(float value) {
  this->publish_state(value);
  if (this->injector_ != nullptr && this->injector_->is_configured()) {
    if (!this->injector_->request_temperature(value)) {
      ESP_LOGW(TAG, "Setpoint request rejected: %.0fF", value);
    }
  }
}

}  // namespace tublemetry_display
}  // namespace esphome
