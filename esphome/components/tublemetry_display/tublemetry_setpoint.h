#pragma once

#include "esphome/components/number/number.h"
#include "button_injector.h"

namespace esphome {
namespace tublemetry_display {

class TublemetrySetpoint : public number::Number {
 public:
  void set_button_injector(ButtonInjector *injector) { this->injector_ = injector; }

 protected:
  void control(float value) override;
  ButtonInjector *injector_{nullptr};
  float pending_target_{NAN};
  float last_confirmed_setpoint_{NAN};
};

}  // namespace tublemetry_display
}  // namespace esphome
