#include "tubtron_display.h"
#include "esphome/core/log.h"

#include <cmath>
#include <cstdio>
#include <cstring>

namespace esphome {
namespace tubtron_display {

static const char *const TAG = "tubtron_display";

// 7-segment lookup table.
// Ported from Python src/tubtron/decode.py SEVEN_SEG_TABLE.
// Segment mapping: bit6=a, bit5=b, bit4=c, bit3=d, bit2=e, bit1=f, bit0=g
// Values are masked to 7 bits (dp bit 7 stripped before lookup).
//
// Format: {hex_value, 'character'}, // status
// Cross-check test (tests/test_cross_check.py) parses this table to verify
// it matches the Python reference.
//
// SEVEN_SEG_TABLE_START
static const SegEntry SEVEN_SEG_TABLE[] = {
    {0x7E, '0'},  // unverified (GS510SZ reference)
    {0x30, '1'},  // confirmed
    {0x6D, '2'},  // unverified (GS510SZ reference)
    {0x79, '3'},  // unverified (GS510SZ reference)
    {0x33, '4'},  // unverified (GS510SZ reference)
    {0x5B, '5'},  // unverified (GS510SZ reference)
    {0x5F, '6'},  // unverified (GS510SZ reference)
    {0x70, '7'},  // confirmed
    {0x7F, '8'},  // unverified (GS510SZ reference)
    {0x7B, '9'},  // unverified (GS510SZ reference)
    {0x00, ' '},  // confirmed (blank)
    {0x37, 'H'},  // unverified (GS510SZ reference)
    {0x0E, 'L'},  // unverified (GS510SZ reference)
    {0x67, 'P'},  // unverified (GS510SZ reference)
    {0x4F, 'E'},  // unverified (GS510SZ reference)
    {0x01, '-'},  // unverified (GS510SZ reference)
    {0x03, '-'},  // unverified (alternate dash encoding)
    {0x0D, 'c'},  // unverified (GS510SZ reference)
    {0x05, 'r'},  // unverified (GS510SZ reference)
    {0x1D, 'o'},  // unverified (GS510SZ reference)
};
// SEVEN_SEG_TABLE_END

static const size_t SEVEN_SEG_TABLE_SIZE = sizeof(SEVEN_SEG_TABLE) / sizeof(SEVEN_SEG_TABLE[0]);

// Frame gap threshold in milliseconds.
// At 115200 baud, one byte = 87us. A gap > 1ms (~11 byte-times) indicates
// a new frame boundary.
static const uint32_t FRAME_GAP_MS = 1;

// Expected frame length (Pin 5 idle frames are 8 bytes)
static const size_t EXPECTED_FRAME_LEN = 8;

// Temperature range for valid readings (Fahrenheit)
static const float TEMP_MIN = 80.0f;
static const float TEMP_MAX = 120.0f;

/// Decode a 7-segment byte value to its character.
/// Masks off bit 7 (decimal point) before lookup.
/// Returns '?' for unknown byte patterns.
char TubtronDisplay::decode_7seg_(uint8_t byte_val) {
  uint8_t segments = byte_val & 0x7F;  // mask off dp (bit 7)

  for (size_t i = 0; i < SEVEN_SEG_TABLE_SIZE; i++) {
    if (SEVEN_SEG_TABLE[i].segments == segments) {
      return SEVEN_SEG_TABLE[i].character;
    }
  }

  ESP_LOGW(TAG, "Unknown 7-segment byte: 0x%02X (masked: 0x%02X)", byte_val, segments);
  return '?';
}

// --- TubtronDisplay (main component) ---

void TubtronDisplay::setup() {
  ESP_LOGI(TAG, "Tubtron display decoder starting");
  ESP_LOGI(TAG, "Pin 5 UART: %s", this->pin5_uart_ != nullptr ? "configured" : "NOT configured");
  ESP_LOGI(TAG, "Pin 6 UART: %s", this->pin6_uart_ != nullptr ? "configured" : "NOT configured");
  ESP_LOGI(TAG, "7-segment table entries: %d", (int) SEVEN_SEG_TABLE_SIZE);
}

void TubtronDisplay::loop() {
  this->process_pin5_data_();
  // Pin 6 data is currently unused (constant refresh pattern).
  // Read and discard to prevent UART buffer overflow.
  if (this->pin6_uart_ != nullptr) {
    uint8_t discard;
    while (this->pin6_uart_->available()) {
      this->pin6_uart_->read_byte(&discard);
    }
  }
}

float TubtronDisplay::get_setup_priority() const {
  return setup_priority::DATA;  // after UART is ready
}

/// Read bytes from Pin 5 UART and detect frame boundaries via timing gaps.
void TubtronDisplay::process_pin5_data_() {
  if (this->pin5_uart_ == nullptr)
    return;

  while (this->pin5_uart_->available()) {
    uint8_t byte;
    this->pin5_uart_->read_byte(&byte);

    uint32_t now = millis();

    // Frame boundary detection: gap > FRAME_GAP_MS means new frame
    if (this->pin5_index_ > 0 && (now - this->pin5_last_byte_time_) > FRAME_GAP_MS) {
      // Previous bytes were a partial frame; discard and start fresh
      ESP_LOGD(TAG, "Frame boundary detected (gap %u ms), discarding %u partial bytes",
               now - this->pin5_last_byte_time_, this->pin5_index_);
      this->pin5_index_ = 0;
    }

    this->pin5_last_byte_time_ = now;

    // Buffer the byte
    if (this->pin5_index_ < sizeof(this->pin5_buffer_)) {
      this->pin5_buffer_[this->pin5_index_++] = byte;
    } else {
      // Buffer overflow -- reset
      ESP_LOGW(TAG, "Pin 5 buffer overflow, resetting");
      this->pin5_index_ = 0;
      this->pin5_buffer_[this->pin5_index_++] = byte;
    }

    // Process complete frame when we have 8 bytes
    if (this->pin5_index_ >= EXPECTED_FRAME_LEN) {
      this->decode_pin5_frame_(this->pin5_buffer_, EXPECTED_FRAME_LEN);
      this->pin5_index_ = 0;
    }
  }
}

/// Decode an 8-byte Pin 5 frame: extract display string, raw hex,
/// digit values, and update temperature/diagnostic sensors.
void TubtronDisplay::decode_pin5_frame_(const uint8_t *frame, size_t len) {
  // Decode each byte via 7-segment lookup
  char decoded[8];
  int confirmed_count = 0;
  int total_count = 0;

  for (size_t i = 0; i < len; i++) {
    decoded[i] = this->decode_7seg_(frame[i]);
    total_count++;

    // Track confirmed mappings for confidence calculation
    uint8_t masked = frame[i] & 0x7F;
    // Confirmed: 0x30 ("1"), 0x70 ("7"), 0x00 (" ")
    if (masked == 0x30 || masked == 0x70 || masked == 0x00) {
      confirmed_count++;
    }
  }

  // Build display string
  std::string display_str(decoded, len);

  // Build raw hex string (space-separated uppercase hex)
  char hex_buf[8 * 3];  // "XX " per byte, last without space
  for (size_t i = 0; i < len; i++) {
    snprintf(hex_buf + i * 3, 4, "%02X ", frame[i]);
  }
  // Remove trailing space
  std::string raw_hex(hex_buf, len * 3 - 1);

  // Build digit values (pipe-separated decoded characters)
  std::string digit_values;
  for (size_t i = 0; i < len; i++) {
    if (i > 0)
      digit_values += '|';
    digit_values += decoded[i];
  }

  // Check for FE marker
  bool has_fe = (frame[0] == 0xFE);
  if (has_fe) {
    ESP_LOGD(TAG, "FE marker present in frame");
  }

  // Calculate decode confidence as percentage of confirmed bytes
  float confidence = (total_count > 0)
                         ? (static_cast<float>(confirmed_count) / total_count * 100.0f)
                         : 0.0f;

  // Only publish on change
  bool changed = false;

  if (display_str != this->last_display_string_) {
    this->last_display_string_ = display_str;
    if (this->display_string_sensor_ != nullptr) {
      this->display_string_sensor_->publish_state(display_str);
    }
    changed = true;
    ESP_LOGD(TAG, "Display: '%s'", display_str.c_str());
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

  // Always update confidence sensor (it reflects current frame quality)
  if (this->decode_confidence_sensor_ != nullptr) {
    this->decode_confidence_sensor_->publish_state(confidence);
  }

  // Update temperature state (handles persistence through non-temp displays)
  this->update_temperature_(display_str);

  // Publish timestamp if anything changed
  if (changed) {
    this->publish_timestamp_();
  }
}

/// Check if a string represents a valid temperature in the expected range.
bool TubtronDisplay::is_valid_temperature_(const std::string &str) {
  // Strip spaces
  std::string stripped;
  for (char c : str) {
    if (c != ' ')
      stripped += c;
  }

  if (stripped.empty())
    return false;

  // Check if all characters are digits
  for (char c : stripped) {
    if (c < '0' || c > '9')
      return false;
  }

  // Must be 2-3 digits
  if (stripped.length() < 2 || stripped.length() > 3)
    return false;

  return true;
}

/// Update temperature from display string. Implements the dumb decoder
/// pattern: valid temperatures update current_temperature; non-temperature
/// displays (OH, ICE, --) keep the last valid temperature unchanged.
void TubtronDisplay::update_temperature_(const std::string &display_str) {
  if (this->climate_ == nullptr)
    return;

  // Strip spaces for analysis
  std::string stripped;
  for (char c : display_str) {
    if (c != ' ')
      stripped += c;
  }

  if (this->is_valid_temperature_(stripped)) {
    float temp = static_cast<float>(atoi(stripped.c_str()));
    std::string state = "temperature";

    // Log out-of-range but still accept (low confidence)
    if (temp < TEMP_MIN || temp > TEMP_MAX) {
      ESP_LOGW(TAG, "Temperature %.0f outside expected range %.0f-%.0f",
               temp, TEMP_MIN, TEMP_MAX);
    }

    // Publish temperature only if changed
    if (temp != this->last_temperature_ || std::isnan(this->last_temperature_)) {
      this->last_temperature_ = temp;
      this->climate_->current_temperature = temp;
      this->climate_->publish_state();
      ESP_LOGI(TAG, "Temperature: %.0f F", temp);
    }

    // Update display state
    if (state != this->last_display_state_) {
      this->last_display_state_ = state;
      if (this->display_state_sensor_ != nullptr) {
        this->display_state_sensor_->publish_state(state);
      }
    }
  } else {
    // Non-temperature display: classify and update state, keep temperature
    std::string state;
    if (stripped == "OH") {
      state = "OH";
    } else if (stripped == "ICE") {
      state = "ICE";
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
    // current_temperature unchanged -- last valid reading persists
  }
}

/// Publish current timestamp to the last_update sensor.
/// Uses millis() as a fallback since SNTP may not be available.
void TubtronDisplay::publish_timestamp_() {
  if (this->last_update_sensor_ == nullptr)
    return;

  // Try to get real time from SNTP if available
  // ESPHome time components register globally; check if we can get a time
  auto *time_comp = time::RealTimeClock::get_default();
  if (time_comp != nullptr) {
    auto now = time_comp->now();
    if (now.is_valid()) {
      char buf[32];
      snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02d",
               now.year, now.month, now.day_of_month,
               now.hour, now.minute, now.second);
      this->last_update_sensor_->publish_state(std::string(buf));
      return;
    }
  }

  // Fallback: publish millis() as "uptime:NNNNN"
  char buf[32];
  snprintf(buf, sizeof(buf), "uptime:%lu", (unsigned long) millis());
  this->last_update_sensor_->publish_state(std::string(buf));
}

// --- TubtronClimate ---

float TubtronClimate::get_setup_priority() const {
  return setup_priority::DATA;
}

climate::ClimateTraits TubtronClimate::traits() {
  auto traits = climate::ClimateTraits();
  traits.set_supports_current_temperature(true);
  traits.set_supported_modes({climate::CLIMATE_MODE_HEAT});
  traits.set_visual_min_temperature(80.0f);
  traits.set_visual_max_temperature(104.0f);
  traits.set_visual_temperature_step(1.0f);
  traits.set_supports_action(false);
  return traits;
}

void TubtronClimate::control(const climate::ClimateCall &call) {
  // Phase 1: read-only. Setpoint control will be implemented in Phase 2
  // when button injection is available.
  ESP_LOGW(TAG, "Climate control not supported yet (read-only in Phase 1)");
}

}  // namespace tubtron_display
}  // namespace esphome
