#include "tublemetry_display.h"
#include "esphome/core/log.h"
#include "esphome/core/hal.h"

#include <cstdio>
#include <cstring>
#include <cmath>

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
    {0x34, '1'},  // confirmed (setpoint display mode — "1" with lower-left foot segment e)
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

// Minimum microseconds between valid clock edges (noise rejection).
// Real clock pulses are ~37us apart; anything shorter is floating-pin noise.
static const uint32_t MIN_PULSE_US = 10;

// Static instance pointer for ISR trampoline
static TublemetryDisplay *isr_instance_ = nullptr;

/// ISR trampoline -- static function that calls instance method
static void IRAM_ATTR clock_isr_trampoline(TublemetryDisplay *instance) {
  if (instance != nullptr) {
    instance->clock_isr_();
  } else if (isr_instance_ != nullptr) {
    isr_instance_->clock_isr_();
  }
}

/// ISR: called on every clock rising edge. Samples data pin and accumulates bits.
void IRAM_ATTR TublemetryDisplay::clock_isr_() {
  uint32_t now = micros();

  // Reject noise: ignore edges closer than MIN_PULSE_US apart
  uint32_t elapsed = now - this->isr_data_.last_edge_us;
  if (elapsed < MIN_PULSE_US) {
    return;
  }

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

  ESP_LOGV(TAG, "Unknown 7-segment byte: 0x%02X (masked: 0x%02X)", byte_val, segments);
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
  this->clock_pin_->attach_interrupt(clock_isr_trampoline, this, gpio::INTERRUPT_RISING_EDGE);

  ESP_LOGI(TAG, "Clock interrupt attached, waiting for frames...");

  // Publish component version
  ESP_LOGI(TAG, "Tublemetry version: %s", TUBLEMETRY_VERSION);
  if (this->version_sensor_ != nullptr) {
    this->version_sensor_->publish_state(TUBLEMETRY_VERSION);
  }

  // Set up button injector if configured
  if (this->injector_ != nullptr) {
    this->injector_->setup();
  }
}

void TublemetryDisplay::loop() {
  // Drive button injector state machine (non-blocking)
  if (this->injector_ != nullptr) {
    this->injector_->loop();
  }

  // Copy frame from ISR with interrupts disabled to prevent torn reads
  portDISABLE_INTERRUPTS();
  bool has_frame = this->isr_data_.frame_ready;
  uint32_t frame_bits = this->isr_data_.last_frame;
  if (has_frame) this->isr_data_.frame_ready = false;
  portENABLE_INTERRUPTS();

  if (!has_frame) {
    return;
  }

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
  uint8_t status = frame_bits & 0x07;           // bits 2-0 (p4)

  // Checksum gate — p1 bits 6,3,1,0 must be zero in valid frames;
  // p4 bit 0 must also be zero.
  {
    uint8_t p1 = digit_bytes[0];
    static constexpr uint8_t CHECKSUM_MASK = 0x4B;  // bits 6,3,1,0
    if ((p1 & CHECKSUM_MASK) != 0x00 || (status & 0x01) != 0x00) {
      ESP_LOGW(TAG, "Frame checksum failed (p1=0x%02X p4=0x%X), dropping", p1, status);
      return;
    }
  }

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

  // Drop partial frames — transitional display states are not actionable
  if (known_count < DIGITS_PER_FRAME) {
    ESP_LOGD(TAG, "Partial frame dropped (raw: %s, confidence: %.0f%%)", raw_hex.c_str(), confidence);
    return;
  }

  // Stability filter — require STABLE_THRESHOLD consecutive identical decoded frames
  if (display_str == this->candidate_display_string_) {
    if (this->stable_count_ < 255) this->stable_count_++;
  } else {
    this->candidate_display_string_ = display_str;
    this->stable_count_ = 1;
  }
  if (this->stable_count_ < STABLE_THRESHOLD) {
    ESP_LOGD(TAG, "Stability: %d/%d for '%s', holding",
             this->stable_count_, STABLE_THRESHOLD, display_str.c_str());
    return;
  }

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

  if (this->decode_confidence_sensor_ != nullptr && confidence != this->last_confidence_) {
    this->last_confidence_ = confidence;
    this->decode_confidence_sensor_->publish_state(confidence);
  }

  // Classify display state (temperature, economy, sleep, etc.)
  this->classify_display_state_(display_str);

  // Status bit extraction — heater/pump/light
  // p1_full re-extracts digit_bytes[0] because the checksum scoped block's p1 is out of scope.
  uint8_t p1_full = (frame_bits >> 17) & 0x7F;
  bool heater_on = (p1_full >> 2) & 0x01;   // p1 bit 2
  bool pump_on   = (status >> 2) & 0x01;    // p4 bit 2
  bool light_on  = (status >> 1) & 0x01;    // p4 bit 1
  if (static_cast<int8_t>(heater_on) != this->last_heater_) {
    this->last_heater_ = static_cast<int8_t>(heater_on);
    if (this->heater_binary_sensor_ != nullptr) this->heater_binary_sensor_->publish_state(heater_on);
  }
  if (static_cast<int8_t>(pump_on) != this->last_pump_) {
    this->last_pump_ = static_cast<int8_t>(pump_on);
    if (this->pump_binary_sensor_ != nullptr) this->pump_binary_sensor_->publish_state(pump_on);
  }
  if (static_cast<int8_t>(light_on) != this->last_light_) {
    this->last_light_ = static_cast<int8_t>(light_on);
    if (this->light_binary_sensor_ != nullptr) this->light_binary_sensor_->publish_state(light_on);
  }

  if (changed) {
    this->publish_timestamp_();
  }
}

/// Classify the display string into a state category.
/// Temperature values are published as raw decoded strings (no unit conversion).
/// HA is responsible for interpreting units.
///
/// Set-mode detection: the controller alternates blank→setpoint→blank when the
/// user holds a button. We detect this pattern and route setpoint flashes to
/// detected_setpoint_sensor_ rather than temperature_sensor_.
void TublemetryDisplay::classify_display_state_(const std::string &display_str) {
  std::string stripped;
  for (char c : display_str) {
    if (c != ' ')
      stripped += c;
  }

  std::string state;

  // Check if it's a 2-3 digit numeric string (temperature reading)
  bool is_numeric = !stripped.empty() && stripped.length() >= 2 && stripped.length() <= 3;
  if (is_numeric) {
    for (char c : stripped) {
      if (c < '0' || c > '9') {
        is_numeric = false;
        break;
      }
    }
  }

  if (is_numeric) {
    state = "temperature";
    float temp = static_cast<float>(atoi(stripped.c_str()));

    // Check set mode timeout before deciding whether this is a setpoint flash
    if (this->in_set_mode_ && (millis() - this->last_blank_seen_ms_) >= SET_MODE_TIMEOUT_MS) {
      this->in_set_mode_ = false;
      this->set_temp_potential_ = NAN;
      ESP_LOGD(TAG, "Set mode timeout — returning to normal");
    }

    // Feed raw value to button injector for closed-loop verification
    if (this->injector_ != nullptr) {
      this->injector_->feed_display_temperature(temp);
    }

    if (this->in_set_mode_) {
      // Setpoint flash — record candidate, suppress temperature sensor publish
      this->set_temp_potential_ = temp;
      ESP_LOGD(TAG, "Set mode candidate: %.0fF (suppressing temperature publish)", temp);
      // temperature_sensor_ publish is intentionally skipped here
    } else {
      // Normal temperature — publish to HA
      if (this->temperature_sensor_ != nullptr) {
        this->temperature_sensor_->publish_state(temp);
      }
    }
  } else if (stripped == "OH") {
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
    this->in_set_mode_ = true;
    this->last_blank_seen_ms_ = millis();
    ESP_LOGD(TAG, "Set mode entry (blank frame)");

    // Confirmation blank: if we accumulated a candidate, publish detected setpoint
    if (!std::isnan(this->set_temp_potential_)) {
      if (std::isnan(this->detected_setpoint_) || this->set_temp_potential_ != this->detected_setpoint_) {
        this->detected_setpoint_ = this->set_temp_potential_;
        if (this->detected_setpoint_sensor_ != nullptr)
          this->detected_setpoint_sensor_->publish_state(this->detected_setpoint_);
        if (this->injector_ != nullptr)
          this->injector_->set_known_setpoint(this->detected_setpoint_);
        ESP_LOGI(TAG, "Setpoint detected: %.0fF", this->detected_setpoint_);
        this->last_setpoint_capture_ms_ = millis();
      }
    }
    this->set_temp_potential_ = NAN;
  } else {
    state = "unknown";
  }

  if (state != this->last_display_state_) {
    this->last_display_state_ = state;
    if (this->display_state_sensor_ != nullptr) {
      this->display_state_sensor_->publish_state(state);
    }
    ESP_LOGD(TAG, "Display state: %s", state.c_str());
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

}  // namespace tublemetry_display
}  // namespace esphome
