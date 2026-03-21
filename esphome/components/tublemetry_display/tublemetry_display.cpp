#include "tublemetry_display.h"
#include "esphome/core/log.h"
#include "esphome/core/hal.h"

#include <cmath>
#include <cstdio>
#include <cstring>

namespace esphome {
namespace tublemetry_display {

static const char *const TAG = "tublemetry_display";

// 7-segment lookup table.
// Ported from Python src/tublemetry/decode.py SEVEN_SEG_TABLE.
// Segment mapping: bit6=a, bit5=b, bit4=c, bit3=d, bit2=e, bit1=f, bit0=g
// Values are masked to 7 bits (dp bit 7 stripped before lookup).
//
// Format: {hex_value, 'character'}, // status
// Cross-check test (tests/test_cross_check.py) parses this table to verify
// it matches the Python reference.
//
// SEVEN_SEG_TABLE_START
static const SegEntry SEVEN_SEG_TABLE[] = {
    {0x7E, '0'},  // confirmed (ladder capture 2026-03-20)
    {0x30, '1'},  // confirmed (ladder capture 2026-03-20)
    {0x6D, '2'},  // confirmed (ladder capture 2026-03-20)
    {0x79, '3'},  // confirmed (ladder capture 2026-03-20)
    {0x33, '4'},  // confirmed (ladder capture 2026-03-20)
    {0x5B, '5'},  // confirmed (ladder capture 2026-03-20)
    {0x5F, '6'},  // confirmed (ladder capture 2026-03-20)
    {0x70, '7'},  // confirmed (ladder capture 2026-03-20)
    {0x7F, '8'},  // confirmed (ladder capture 2026-03-20)
    {0x73, '9'},  // confirmed (ladder capture 2026-03-20) -- NOT 0x7B, no bottom segment
    {0x00, ' '},  // confirmed (blank)
    {0x37, 'H'},  // confirmed (OH.csv decode)
    {0x0E, 'L'},  // confirmed (SL mode capture 2026-03-20)
    {0x4F, 'E'},  // confirmed (Ec mode capture 2026-03-20)
    {0x0D, 'c'},  // confirmed (Ec mode capture 2026-03-20)
    {0x0F, 't'},  // confirmed (St mode capture 2026-03-20)
    {0x67, 'P'},  // unverified (GS510SZ reference)
    {0x01, '-'},  // unverified (GS510SZ reference)
    {0x03, '-'},  // unverified (alternate dash encoding)
    {0x05, 'r'},  // unverified (GS510SZ reference)
    {0x1D, 'o'},  // unverified (GS510SZ reference)
};
// SEVEN_SEG_TABLE_END

static const size_t SEVEN_SEG_TABLE_SIZE = sizeof(SEVEN_SEG_TABLE) / sizeof(SEVEN_SEG_TABLE[0]);

// Frame gap threshold in microseconds.
// At 60Hz, frames are 16.7ms apart. Clock pulses within a frame are ~37us apart.
// A gap > 500us between clock edges means a new frame.
static const uint32_t FRAME_GAP_US = 500;

// Temperature range for valid readings (Fahrenheit)
static const float TEMP_MIN = 80.0f;
static const float TEMP_MAX = 120.0f;

// Static instance pointer for ISR trampoline
static TublemetryDisplay *isr_instance_ = nullptr;

/// ISR trampoline -- static function that calls instance method
static void IRAM_ATTR clock_isr_trampoline() {
  if (isr_instance_ != nullptr) {
    isr_instance_->clock_isr_();
  }
}

/// ISR: called on every clock rising edge. Samples data pin and accumulates bits.
void IRAM_ATTR TublemetryDisplay::clock_isr_() {
  uint32_t now = micros();

  // Detect frame boundary: gap > FRAME_GAP_US means new frame
  if (this->isr_data_.bit_count > 0 && (now - this->isr_data_.last_edge_us) > FRAME_GAP_US) {
    // Previous bits form a complete frame if we got 24
    if (this->isr_data_.bit_count == BITS_PER_FRAME) {
      this->isr_data_.last_frame = this->isr_data_.bits;
      this->isr_data_.frame_ready = true;
      this->isr_data_.frame_count++;
    }
    // Reset for new frame
    this->isr_data_.bits = 0;
    this->isr_data_.bit_count = 0;
  }

  this->isr_data_.last_edge_us = now;

  // Sample data pin and shift into frame buffer (MSB-first)
  uint8_t data_bit = gpio_get_level(static_cast<gpio_num_t>(this->data_gpio_num_));
  this->isr_data_.bits = (this->isr_data_.bits << 1) | data_bit;
  this->isr_data_.bit_count++;

  // If we've collected a full frame, make it available immediately
  if (this->isr_data_.bit_count == BITS_PER_FRAME) {
    this->isr_data_.last_frame = this->isr_data_.bits;
    this->isr_data_.frame_ready = true;
    this->isr_data_.frame_count++;
    // Don't reset yet -- let the gap detection handle the boundary
  }
}

/// Decode a 7-segment byte value to its character.
/// Masks off bit 7 (decimal point) before lookup.
/// Returns '?' for unknown byte patterns.
char TublemetryDisplay::decode_7seg_(uint8_t byte_val) {
  uint8_t segments = byte_val & 0x7F;  // mask off dp (bit 7)

  for (size_t i = 0; i < SEVEN_SEG_TABLE_SIZE; i++) {
    if (SEVEN_SEG_TABLE[i].segments == segments) {
      return SEVEN_SEG_TABLE[i].character;
    }
  }

  ESP_LOGW(TAG, "Unknown 7-segment byte: 0x%02X (masked: 0x%02X)", byte_val, segments);
  return '?';
}

// --- TublemetryDisplay (main component) ---

void TublemetryDisplay::setup() {
  ESP_LOGI(TAG, "Tublemetry display decoder starting (GPIO interrupt mode)");

  if (this->clock_pin_ == nullptr || this->data_pin_ == nullptr) {
    ESP_LOGE(TAG, "Clock or data pin not configured");
    this->mark_failed();
    return;
  }

  // Configure pins
  this->clock_pin_->setup();
  this->data_pin_->setup();

  // Cache data pin GPIO number for fast ISR access
  this->data_gpio_num_ = this->data_pin_->get_pin();

  ESP_LOGI(TAG, "Clock pin: GPIO%d, Data pin: GPIO%d",
           this->clock_pin_->get_pin(), this->data_gpio_num_);
  ESP_LOGI(TAG, "7-segment table entries: %d", (int) SEVEN_SEG_TABLE_SIZE);

  // Initialize ISR data
  memset((void *) &this->isr_data_, 0, sizeof(this->isr_data_));

  // Set up ISR trampoline
  isr_instance_ = this;
  this->clock_pin_->attach_interrupt(clock_isr_trampoline, gpio::INTERRUPT_RISING_EDGE);

  ESP_LOGI(TAG, "Clock interrupt attached, waiting for frames...");
}

void TublemetryDisplay::loop() {
  // Check if ISR has a new frame ready
  if (!this->isr_data_.frame_ready) {
    return;
  }

  // Copy frame data and clear flag (minimize time with shared state)
  uint32_t frame_bits = this->isr_data_.last_frame;
  this->isr_data_.frame_ready = false;

  this->process_frame_(frame_bits);
}

float TublemetryDisplay::get_setup_priority() const {
  return setup_priority::DATA;
}

/// Process a complete 24-bit frame: extract 3 digits and 3 status bits.
void TublemetryDisplay::process_frame_(uint32_t frame_bits) {
  // Extract 3 x 7-bit digits (MSB-first from bit 23 down)
  // Frame layout: [digit1:7][digit2:7][digit3:7][status:3]
  uint8_t digit_bytes[DIGITS_PER_FRAME];
  digit_bytes[0] = (frame_bits >> 17) & 0x7F;  // bits 23-17
  digit_bytes[1] = (frame_bits >> 10) & 0x7F;  // bits 16-10
  digit_bytes[2] = (frame_bits >> 3) & 0x7F;   // bits 9-3
  // uint8_t status = frame_bits & 0x07;        // bits 2-0 (reserved for future use)

  // Decode each digit
  char decoded[DIGITS_PER_FRAME + 1];
  for (int i = 0; i < DIGITS_PER_FRAME; i++) {
    decoded[i] = this->decode_7seg_(digit_bytes[i]);
  }
  decoded[DIGITS_PER_FRAME] = '\0';

  std::string display_str(decoded, DIGITS_PER_FRAME);

  // Build raw hex string
  char hex_buf[16];
  snprintf(hex_buf, sizeof(hex_buf), "%02X %02X %02X",
           digit_bytes[0], digit_bytes[1], digit_bytes[2]);
  std::string raw_hex(hex_buf);

  // Build digit values (pipe-separated)
  std::string digit_values;
  for (int i = 0; i < DIGITS_PER_FRAME; i++) {
    if (i > 0)
      digit_values += '|';
    digit_values += decoded[i];
  }

  // Calculate decode confidence (percentage of known characters)
  int known_count = 0;
  for (int i = 0; i < DIGITS_PER_FRAME; i++) {
    if (decoded[i] != '?')
      known_count++;
  }
  float confidence = (static_cast<float>(known_count) / DIGITS_PER_FRAME) * 100.0f;

  // Only publish on change
  bool changed = false;

  if (display_str != this->last_display_string_) {
    this->last_display_string_ = display_str;
    if (this->display_string_sensor_ != nullptr) {
      this->display_string_sensor_->publish_state(display_str);
    }
    changed = true;
    ESP_LOGD(TAG, "Display: '%s' (raw: %s, frame #%lu)",
             display_str.c_str(), raw_hex.c_str(),
             (unsigned long) this->isr_data_.frame_count);
  }

  if (raw_hex != this->last_raw_hex_) {
    this->last_raw_hex_ = raw_hex;
    if (this->raw_hex_sensor_ != nullptr) {
      this->raw_hex_sensor_->publish_state(raw_hex);
    }
    changed = true;
  }

  if (digit_values != this->last_digit_values_) {
    this->last_digit_values_ = digit_values;
    if (this->digit_values_sensor_ != nullptr) {
      this->digit_values_sensor_->publish_state(digit_values);
    }
    changed = true;
  }

  if (this->decode_confidence_sensor_ != nullptr) {
    this->decode_confidence_sensor_->publish_state(confidence);
  }

  // Update temperature state
  this->update_temperature_(display_str);

  if (changed) {
    this->publish_timestamp_();
  }
}

/// Check if a string represents a valid temperature in the expected range.
bool TublemetryDisplay::is_valid_temperature_(const std::string &str) {
  std::string stripped;
  for (char c : str) {
    if (c != ' ')
      stripped += c;
  }

  if (stripped.empty())
    return false;

  for (char c : stripped) {
    if (c < '0' || c > '9')
      return false;
  }

  if (stripped.length() < 2 || stripped.length() > 3)
    return false;

  return true;
}

/// Update temperature from display string. Valid temperatures update
/// current_temperature; non-temperature displays keep the last valid
/// temperature unchanged.
void TublemetryDisplay::update_temperature_(const std::string &display_str) {
  if (this->climate_ == nullptr)
    return;

  std::string stripped;
  for (char c : display_str) {
    if (c != ' ')
      stripped += c;
  }

  if (this->is_valid_temperature_(stripped)) {
    float temp = static_cast<float>(atoi(stripped.c_str()));
    std::string state = "temperature";

    if (temp < TEMP_MIN || temp > TEMP_MAX) {
      ESP_LOGW(TAG, "Temperature %.0f outside expected range %.0f-%.0f",
               temp, TEMP_MIN, TEMP_MAX);
    }

    if (temp != this->last_temperature_ || std::isnan(this->last_temperature_)) {
      this->last_temperature_ = temp;
      this->climate_->current_temperature = temp;
      this->climate_->publish_state();
      ESP_LOGI(TAG, "Temperature: %.0f F", temp);
    }

    if (state != this->last_display_state_) {
      this->last_display_state_ = state;
      if (this->display_state_sensor_ != nullptr) {
        this->display_state_sensor_->publish_state(state);
      }
    }
  } else {
    std::string state;
    if (stripped == "OH") {
      state = "OH";
    } else if (stripped == "ICE") {
      state = "ICE";
    } else if (stripped == "Ec") {
      state = "economy";
    } else if (stripped == "SL" || stripped == "5L") {
      state = "sleep";
    } else if (stripped == "St" || stripped == "5t") {
      state = "standby";
    } else if (stripped == "--" || stripped == "---") {
      state = "startup";
    } else if (stripped.empty()) {
      state = "blank";
    } else {
      state = "unknown";
    }

    if (state != this->last_display_state_) {
      this->last_display_state_ = state;
      if (this->display_state_sensor_ != nullptr) {
        this->display_state_sensor_->publish_state(state);
      }
      ESP_LOGD(TAG, "Display state: %s (temperature unchanged: %.0f F)",
               state.c_str(), this->last_temperature_);
    }
  }
}

/// Publish current timestamp to the last_update sensor.
void TublemetryDisplay::publish_timestamp_() {
  if (this->last_update_sensor_ == nullptr)
    return;

  char buf[32];
  snprintf(buf, sizeof(buf), "uptime:%lu", (unsigned long) millis());
  this->last_update_sensor_->publish_state(std::string(buf));
}

// --- TublemetryClimate ---

float TublemetryClimate::get_setup_priority() const {
  return setup_priority::DATA;
}

climate::ClimateTraits TublemetryClimate::traits() {
  auto traits = climate::ClimateTraits();
  traits.add_supported_mode(climate::CLIMATE_MODE_HEAT);
  traits.set_visual_min_temperature(80.0f);
  traits.set_visual_max_temperature(104.0f);
  traits.set_visual_temperature_step(1.0f);
  return traits;
}

void TublemetryClimate::control(const climate::ClimateCall &call) {
  // Phase 1: read-only. Setpoint control will be implemented in Phase 2
  // when button injection is available.
  ESP_LOGW(TAG, "Climate control not supported yet (read-only in Phase 1)");
}

}  // namespace tublemetry_display
}  // namespace esphome
