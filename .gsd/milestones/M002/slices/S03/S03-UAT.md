# S03: Status Bit Binary Sensors — UAT

**Milestone:** M002
**Written:** 2026-04-04T14:13:56.544Z

## Preconditions

- Firmware compiled from this branch is flashed to the ESP32 at tublemetry.local (192.168.0.92)
- ESP32 is connected to the VS300FL4 RS-485 bus and receiving live frames
- Home Assistant integration is active and entities are visible

## Test Cases

### TC-01: Binary sensor entities appear in HA

**Steps:**
1. Open HA → Developer Tools → States
2. Filter for `binary_sensor.tublemetry`

**Expected:** Three entities visible: `binary_sensor.tublemetry_hot_tub_heater`, `binary_sensor.tublemetry_hot_tub_pump`, `binary_sensor.tublemetry_hot_tub_light`

---

### TC-02: Heater sensor reflects display bit state

**Steps:**
1. Observe the hot tub display panel
2. Compare heater LED indicator on the panel with `binary_sensor.tublemetry_hot_tub_heater` in HA

**Expected:** HA binary sensor state matches the physical heater indicator. On = heater active, Off = heater inactive.

---

### TC-03: Pump sensor reflects pump state

**Steps:**
1. Observe the hot tub panel pump indicator
2. Compare with `binary_sensor.tublemetry_hot_tub_pump` in HA

**Expected:** HA binary sensor matches physical pump indicator.

---

### TC-04: Light sensor reflects light state

**Steps:**
1. Press the light button on the hot tub panel to toggle the light
2. Observe `binary_sensor.tublemetry_hot_tub_light` in HA

**Expected:** HA binary sensor changes state within ~1 second of pressing the light button. Toggles on/off reliably.

---

### TC-05: No spurious state changes when sensors are stable

**Steps:**
1. Leave the tub idle for 60 seconds with heater/pump/light in steady state
2. Monitor HA history for all three binary sensors

**Expected:** No state changes appear in history during the idle period.

---

### TC-06: Dashboard status card renders correctly

**Steps:**
1. Open HA dashboard
2. Scroll to Card 6 "Hot Tub Status"

**Expected:** Card shows three rows: Heater, Pump, Light — each with correct on/off state matching TC-02 through TC-04.

---

### TC-07: Existing temperature and setpoint sensors unaffected

**Steps:**
1. Check `sensor.tublemetry_hot_tub_temperature` and `number.tublemetry_hot_tub_setpoint` in HA

**Expected:** Both entities still present with valid values. No ID changes or gaps in history.

---

### TC-08: First publish on boot

**Steps:**
1. OTA flash the firmware
2. Watch HA history for heater/pump/light sensors immediately after reboot

**Expected:** All three sensors publish their first state within a few seconds of boot (first valid frame processed), even if the state is False/Off.

---

## Edge Cases

- **All three sensors on simultaneously:** Press the TEMP button to wake the display; observe all three sensors report correct values when heater is heating, pump is running, and light is on.
- **Status bit 0 frames (checksum failure):** Frames with `status & 0x01 == 1` should be discarded by the checksum gate — sensor values should not flicker when such frames arrive.
- **Rapid light toggle:** Toggle light on/off quickly; HA should publish each change within one frame cycle (~17ms × stable_threshold = ~50ms).
