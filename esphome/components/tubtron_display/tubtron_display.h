#pragma once

#include "esphome/core/component.h"
#include "esphome/components/climate/climate.h"
#include "esphome/components/sensor/sensor.h"
#include "esphome/components/text_sensor/text_sensor.h"
#include "esphome/components/uart/uart.h"

#include <string>

namespace esphome {
namespace tubtron_display {

// 7-segment lookup table entry
struct SegEntry {
  uint8_t segments;  // 7-bit value (dp masked off)
  char character;    // decoded character
};

// Forward declaration
class TubtronClimate;

/// Main component: reads dual UARTs and decodes display frames.
class TubtronDisplay : public Component {
 public:
  void setup() override;
  void loop() override;
  float get_setup_priority() const override;

  // UART setters (called from Python codegen)
  void set_uart_pin5(uart::UARTComponent *uart) { this->pin5_uart_ = uart; }
  void set_uart_pin6(uart::UARTComponent *uart) { this->pin6_uart_ = uart; }

  // Climate setter
  void set_climate(TubtronClimate *climate) { this->climate_ = climate; }

  // Diagnostic sensor setters
  void set_display_string_sensor(text_sensor::TextSensor *s) { this->display_string_sensor_ = s; }
  void set_raw_hex_sensor(text_sensor::TextSensor *s) { this->raw_hex_sensor_ = s; }
  void set_display_state_sensor(text_sensor::TextSensor *s) { this->display_state_sensor_ = s; }
  void set_decode_confidence_sensor(sensor::Sensor *s) { this->decode_confidence_sensor_ = s; }
  void set_digit_values_sensor(text_sensor::TextSensor *s) { this->digit_values_sensor_ = s; }
  void set_last_update_sensor(text_sensor::TextSensor *s) { this->last_update_sensor_ = s; }

 protected:
  // UART components (not inherited -- we have two)
  uart::UARTComponent *pin5_uart_{nullptr};
  uart::UARTComponent *pin6_uart_{nullptr};

  // Climate entity
  TubtronClimate *climate_{nullptr};

  // Pin 5 frame buffer
  uint8_t pin5_buffer_[16];
  uint8_t pin5_index_{0};
  uint32_t pin5_last_byte_time_{0};

  // State tracking (publish only on change)
  float last_temperature_{NAN};
  std::string last_display_string_;
  std::string last_display_state_;
  std::string last_raw_hex_;
  std::string last_digit_values_;

  // Diagnostic sensor pointers
  text_sensor::TextSensor *display_string_sensor_{nullptr};
  text_sensor::TextSensor *raw_hex_sensor_{nullptr};
  text_sensor::TextSensor *display_state_sensor_{nullptr};
  sensor::Sensor *decode_confidence_sensor_{nullptr};
  text_sensor::TextSensor *digit_values_sensor_{nullptr};
  text_sensor::TextSensor *last_update_sensor_{nullptr};

  // Internal methods
  void process_pin5_data_();
  void decode_pin5_frame_(const uint8_t *frame, size_t len);
  char decode_7seg_(uint8_t byte_val);
  void update_temperature_(const std::string &display_str);
  bool is_valid_temperature_(const std::string &str);
  void publish_timestamp_();
};

/// Read-only climate entity backed by TubtronDisplay.
class TubtronClimate : public climate::Climate, public Component {
 public:
  void setup() override {}
  float get_setup_priority() const override;

  climate::ClimateTraits traits() override;
  void control(const climate::ClimateCall &call) override;
};

}  // namespace tubtron_display
}  // namespace esphome
