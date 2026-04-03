#pragma once

#include "esphome/core/component.h"
#include "esphome/core/gpio.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/number/number.h"
#include "esphome/components/text_sensor/text_sensor.h"
#include "button_injector.h"

#include <string>

namespace esphome {
namespace tublemetry_display {

// Component version — update on each meaningful firmware change
static const char *const TUBLEMETRY_VERSION = "0.2.0";

// 7-segment lookup table entry
struct SegEntry {
  uint8_t segments;  // 7-bit value (dp masked off)
  char character;    // decoded character
};

// Frame constants
static const uint8_t BITS_PER_FRAME = 24;
static const uint8_t DIGITS_PER_FRAME = 3;
static const uint8_t BITS_PER_DIGIT = 7;

// ISR-shared frame data (volatile, accessed from interrupt context)
struct FrameData {
  volatile uint32_t bits;          // accumulated bits (MSB-first)
  volatile uint8_t bit_count;      // bits collected in current frame
  volatile uint32_t last_frame;    // last completed frame (24 bits)
  volatile bool frame_ready;       // new frame available for processing
  volatile uint32_t last_edge_us;  // micros() of last clock rising edge
  volatile uint32_t frame_count;   // total frames decoded (diagnostic)
};

/// Main component: reads synchronous clock+data GPIO and decodes display frames.
class TublemetryDisplay : public Component {
 public:
  void setup() override;
  void loop() override;
  float get_setup_priority() const override;

  // GPIO pin setters (called from Python codegen)
  void set_clock_pin(InternalGPIOPin *pin) { this->clock_pin_ = pin; }
  void set_data_pin(InternalGPIOPin *pin) { this->data_pin_ = pin; }

  // Button injector setter
  void set_button_injector(ButtonInjector *injector) { this->injector_ = injector; }

  // Diagnostic sensor setters
  void set_display_string_sensor(text_sensor::TextSensor *s) { this->display_string_sensor_ = s; }
  void set_raw_hex_sensor(text_sensor::TextSensor *s) { this->raw_hex_sensor_ = s; }
  void set_display_state_sensor(text_sensor::TextSensor *s) { this->display_state_sensor_ = s; }
  void set_decode_confidence_sensor(sensor::Sensor *s) { this->decode_confidence_sensor_ = s; }
  void set_temperature_sensor(sensor::Sensor *s) { this->temperature_sensor_ = s; }
  void set_setpoint_number(number::Number *n) { this->setpoint_number_ = n; }
  void set_digit_values_sensor(text_sensor::TextSensor *s) { this->digit_values_sensor_ = s; }
  void set_last_update_sensor(text_sensor::TextSensor *s) { this->last_update_sensor_ = s; }
  void set_version_sensor(text_sensor::TextSensor *s) { this->version_sensor_ = s; }

  // Test helpers — single raw button press for hardware validation
  void test_press_up() { if (this->injector_ != nullptr) this->injector_->press_once(true); }
  void test_press_down() { if (this->injector_ != nullptr) this->injector_->press_once(false); }

  // ISR handler (must be public for static trampoline)
  void IRAM_ATTR clock_isr_();

 protected:
  // GPIO pins
  InternalGPIOPin *clock_pin_{nullptr};
  InternalGPIOPin *data_pin_{nullptr};

  // Button injector (optional — nullptr if no output pins configured)
  ButtonInjector *injector_{nullptr};

  // ISR-shared data
  FrameData isr_data_{};

  // Data pin GPIO number (cached for fast ISR access)
  uint8_t data_gpio_num_{0};

  // State tracking (publish only on change)
  float last_confidence_{-1.0f};
  std::string last_display_string_;
  std::string last_display_state_;
  std::string last_raw_hex_;
  std::string last_digit_values_;

  // Diagnostic sensor pointers
  text_sensor::TextSensor *display_string_sensor_{nullptr};
  text_sensor::TextSensor *raw_hex_sensor_{nullptr};
  text_sensor::TextSensor *display_state_sensor_{nullptr};
  sensor::Sensor *decode_confidence_sensor_{nullptr};
  sensor::Sensor *temperature_sensor_{nullptr};
  number::Number *setpoint_number_{nullptr};
  text_sensor::TextSensor *digit_values_sensor_{nullptr};
  text_sensor::TextSensor *last_update_sensor_{nullptr};
  text_sensor::TextSensor *version_sensor_{nullptr};

  // Internal methods
  void process_frame_(uint32_t frame_bits);
  char decode_7seg_(uint8_t byte_val);
  void classify_display_state_(const std::string &display_str);
  void publish_timestamp_();
};

}  // namespace tublemetry_display
}  // namespace esphome
