# Home Assistant Setup on Raspberry Pi 4

## Context

Tubtron needs Home Assistant for:
- Climate entity dashboard (current + target temperature)
- TOU automation (on-peak/off-peak temperature scheduling)
- Push notifications (temp drops, device offline)
- ESPHome native API integration (auto-discovery)

Currently running Homebridge on a Raspberry Pi 3 (ethernet). Spare Pi 4 Model B available for upgrade. ESP32 (tublemetry) is on IoT WiFi at 192.168.0.92 — confirmed reachable from Pi via ping.

## Plan

### Phase 1: Flash HA OS on Pi 4
1. Download [Home Assistant OS for Pi 4](https://www.home-assistant.io/installation/raspberrypi) — 64-bit image
2. Flash to SD card (or SSD if you have a USB adapter — much more reliable) using [Balena Etcher](https://etcher.balena.io/) or Raspberry Pi Imager
3. Connect Pi 4 via ethernet to the same network
4. Boot it up — first boot takes ~20 minutes to set up
5. Access HA at `http://homeassistant.local:8123` from your browser
6. Create your admin account

### Phase 2: Install Homebridge Add-on (migrate from Pi 3)
1. In HA: Settings → Add-ons → Add-on Store → search "Homebridge"
2. Install the [Homebridge add-on](https://github.com/oznu/homebridge-config-ui-x)
3. Export your Homebridge config from the Pi 3 (`/var/lib/homebridge/config.json`)
4. Import it into the HA Homebridge add-on
5. Verify your existing HomeKit devices still work
6. Shut down the Pi 3

### Phase 3: ESPHome Integration
1. In HA: Settings → Devices & Services → Add Integration → ESPHome
2. Enter the ESP32's address: `192.168.0.92` (or `tublemetry.local` if mDNS works)
3. Enter the API encryption key from `esphome/secrets.yaml` (`api_key`)
4. HA should auto-discover all entities:
   - `climate.hot_tub` — thermostat card with current + target temperature
   - `sensor.hot_tub_wifi_signal` — WiFi RSSI
   - `sensor.hot_tub_uptime` — device uptime
   - `sensor.hot_tub_decode_confidence` — display decode quality
   - `text_sensor.hot_tub_display` — raw display string
   - `text_sensor.hot_tub_display_state` — state (temperature/economy/sleep/etc)
   - `binary_sensor.hot_tub_api_status` — online/offline
   - `button.hot_tub_restart` — remote restart
   - `button.hot_tub_safe_mode` — trigger safe mode

### Phase 4: Notifications
1. Install the HA Companion App on your phone (iOS/Android)
2. Create automations:
   - **Temp drop alert**: If `climate.hot_tub` current_temperature drops below threshold → push notification
   - **Device offline**: If `binary_sensor.hot_tub_api_status` goes to `off` → push notification
3. Example automation YAML:
```yaml
automation:
  - alias: "Hot Tub Offline Alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.hot_tub_api_status
        to: "off"
        for: "00:05:00"  # 5 min grace period
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "🛁 Hot Tub Offline"
          message: "Tublemetry has been unreachable for 5 minutes"
```

### Phase 5: TOU Automation
After button injection is verified on real hardware:
```yaml
automation:
  - alias: "Hot Tub On-Peak (Lower Temp)"
    trigger:
      - platform: time
        at: "10:00:00"
    condition:
      - condition: time
        weekday: [mon, tue, wed, thu, fri]
    action:
      - service: climate.set_temperature
        target:
          entity_id: climate.hot_tub
        data:
          temperature: 99

  - alias: "Hot Tub Off-Peak (Raise Temp)"
    trigger:
      - platform: time
        at: "21:00:00"
    action:
      - service: climate.set_temperature
        target:
          entity_id: climate.hot_tub
        data:
          temperature: 104
```

## Network Requirements

- Pi 4 on ethernet must reach ESP32 on IoT WiFi (192.168.0.92) ✅ confirmed via ping
- mDNS (tublemetry.local) resolves from Pi ✅ confirmed
- UniFi firewall: no additional rules needed (current setup works)
- Pi 4 needs internet access for HA updates and add-on installs

## Hardware

- Raspberry Pi 4 Model B (spare)
- SD card (or USB SSD for better reliability/longevity)
- Ethernet cable (already have from Pi 3 setup)
- Power supply (USB-C, 5V/3A recommended for Pi 4)

## Notes

- HA OS is the recommended install — gets you Supervisor, Add-ons, and automatic updates
- SSD via USB is strongly recommended over SD card — SD cards die in always-on Pi setups
- The HA HomeKit Bridge integration can expose tub entities back to Apple Home if wanted
- Homebridge add-on runs inside HA — single box, single power supply
