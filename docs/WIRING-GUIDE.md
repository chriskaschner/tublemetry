# Tublemetry Wiring Guide

## Overview

```
                    RJ45 T-Splitter
                    ┌─────────────┐
  VS300FL4 (J1) ───┤             ├─── Topside Panel (VL-series)
                    │   Tap Out   │
                    └──────┬──────┘
                           │
                    Terminal Block
                           │
            ┌──────────────┼──────────────┐
            │              │              │
      ┌─────┴─────┐  ┌────┴────┐  ┌──────┴──────┐
      │  Display   │  │  Power  │  │   Button    │
      │  Reading   │  │  & GND  │  │  Injection  │
      │ (inputs)   │  │         │  │ (outputs)   │
      └─────┬─────┘  └────┬────┘  └──────┬──────┘
            │              │              │
            └──────────────┼──────────────┘
                           │
                      ┌────┴────┐
                      │  ESP32  │
                      └─────────┘
```

## RJ45 Pinout (Confirmed)

| Pin | Color        | Function      | ESP32 Connection                    |
|-----|-------------|---------------|--------------------------------------|
| 1   | Orange/White | **+5V Power** | → ESP32 VIN + photorelay commons    |
| 2   | Orange       | **Temp Up**   | → Photorelay A switch out → GPIO18  |
| 3   | Green/White  | Lights        | (not used)                          |
| 4   | Blue         | **Ground**    | → ESP32 GND                         |
| 5   | Blue/White   | **Data**      | → Voltage divider → GPIO17          |
| 6   | Green        | **Clock**     | → Voltage divider → GPIO16          |
| 7   | Brown/White  | Jets          | (not used)                          |
| 8   | Brown        | **Temp Down** | → Photorelay B switch out → GPIO19  |

## Wiring Sections

### 1. Power — Direct from RJ45 Pin 1

```
RJ45 Pin 1 (+5V) ──┬─── ESP32 5V / VIN
                   ├─── C1: 220µF (+ to rail)
                   ├─── C2: 220µF (+ to rail)
                   └─── C3: 100µF (+ to rail)
RJ45 Pin 4 (GND) ──┴─── ESP32 GND
                   (all cap - legs here)
```

Total bulk capacitance: 540µF. Place all three caps as close to the ESP32 VIN/GND pins as possible. + legs to the +5V rail, - legs to GND.

**Capacity check:**
- ESP32 with WiFi LIGHT power save: ~30-50mA average
- ESP32 WiFi TX spikes to ~500mA for ~2ms; 540µF covers the ~300mA deficit without drooping below 4.5V

### 2. Ground

```
RJ45 Pin 4 (Blue) ──────── B0505S-1W Vin- (and ESP32 GND bus)
```

Pin 4 is the common ground reference for the entire circuit. It connects to B0505S-1W Vin- and to the ESP32 GND rail (which is also Vout-). One wire at the terminal block, then split.

### 3. Display Reading — Voltage Dividers (5V → 3.3V)

The clock and data signals from the controller are 5V logic. The ESP32 GPIO inputs are 3.3V tolerant but 5V will damage them. Two voltage dividers step the signals down.

```
                 10kΩ
Pin 6 (Clock) ──┤├──┬── GPIO16 (clock_pin)
                     │
                20kΩ │
                 ┤├──┘
                 │
                GND (ESP32 GND = Pin 4)


                 10kΩ
Pin 5 (Data) ───┤├──┬── GPIO17 (data_pin)
                     │
                20kΩ │
                 ┤├──┘
                 │
                GND (ESP32 GND = Pin 4)
```

**Resistor values:** Any 1:2 ratio works. Options:
- 10kΩ + 20kΩ (ideal)
- 1kΩ + 2.2kΩ (fine, slightly more current draw)
- 4.7kΩ + 10kΩ (close enough — gives 3.3V at 5V input)
- 3.3kΩ + 6.8kΩ (also works)

**Output voltage:** Vout = 5V × R2/(R1+R2) = 5V × 20k/30k = 3.33V ✓

**Important:** The ESP32 has internal pull-downs enabled on GPIO16 and GPIO17 (configured in YAML). This prevents noise when the display cable is not connected.

### 4. Button Injection — Photorelays (AQY212EH)

Each photorelay acts as a normally-open switch between the B0505S-1W Vout+ rail and the button line. When the ESP32 drives the GPIO high, the internal LED turns on, the photorelay closes, and the voltage jump on the button line registers as a button press.


**AQY212EH pinout (DIP-4):**
```
        ┌──────┐
  1 ──┤ +  LED │
  2 ──┤ -     ├── 3   (switch common)
        │      ├── 4   (switch output)
        └──────┘
```

**Temp Up photorelay (A):**
```
                   330Ω         AQY212EH
GPIO18 ──────────┤├──── Pin 1 (LED +)
                         Pin 2 (LED -) ──── GND

                         Pin 3 ──── RJ45 Pin 1 (+5V)
                         Pin 4 ──── RJ45 Pin 2 (Temp Up, Orange)
```

**Temp Down photorelay (B):**
```
                   330Ω         AQY212EH
GPIO19 ──────────┤├──── Pin 1 (LED +)
                         Pin 2 (LED -) ──── GND

                         Pin 3 ──── RJ45 Pin 1 (+5V)
                         Pin 4 ──── RJ45 Pin 8 (Temp Down, Brown)
```

**LED resistor calculation:**
- ESP32 GPIO output: 3.3V
- AQY212EH LED forward voltage: ~1.2V
- Target LED current: ~5mA (minimum to switch is 3mA, 5mA gives margin)
- R = (3.3V - 1.2V) / 5mA = **420Ω** → use 330Ω (6.4mA, well within 50mA max)

**How it simulates a button press:**
- Idle: button line sits at ~2.3V (pulled by controller's ADC circuit)
- Press: photorelay closes, connecting Vout+ (~5V) to button line → voltage jumps to ~4.7V
- Controller's ADC reads the voltage spike as a button press

## ESP32 GPIO Summary

| GPIO  | Direction | Function     | Connected To                          |
|-------|-----------|-------------|---------------------------------------|
| GPIO16| Input     | Clock       | RJ45 Pin 6 via voltage divider        |
| GPIO17| Input     | Data        | RJ45 Pin 5 via voltage divider        |
| GPIO18| Output    | Temp Up     | Photorelay A LED (330Ω)               |
| GPIO19| Output    | Temp Down   | Photorelay B LED (330Ω)               |
| VIN   | Power in  | 5V supply   | RJ45 Pin 1 (+5V)                      |
| GND   | —         | Common GND  | RJ45 Pin 4                            |

## Pre-Power Checklist

Run through this BEFORE connecting to the tub:

- [ ] **Power wired:** RJ45 Pin 1 (+5V) → ESP32 VIN, RJ45 Pin 4 (GND) → ESP32 GND
- [ ] **Bulk caps installed:** 2x 220µF + 1x 100µF in parallel across VIN/GND, + legs to +5V rail
- [ ] **Rail voltage:** measure ESP32 VIN to GND = 5V ± 0.25V with tub powered on
- [ ] **Voltage dividers built:** both tested with multimeter — 5V input → 3.0–3.5V output
- [ ] **Clock divider connected:** RJ45 Pin 6 → divider → GPIO16
- [ ] **Data divider connected:** RJ45 Pin 5 → divider → GPIO17
- [ ] **Photorelay A wired:** GPIO18 → 330Ω → LED+ (pin 1), LED- (pin 2) → GND, switch pin 3 → Vout+, switch pin 4 → RJ45 Pin 2 (Temp Up)
- [ ] **Photorelay B wired:** GPIO19 → 330Ω → LED+ (pin 1), LED- (pin 2) → GND, switch pin 3 → Vout+, switch pin 4 → RJ45 Pin 8 (Temp Down)
- [ ] **No shorts:** continuity between Pin 1 and Pin 4 should be open
- [ ] **No crossed wires:** clock → GPIO16 (not 17), data → GPIO17 (not 16)
- [ ] **Topside panel still works:** with just the T-splitter and terminal blocks (no ESP32), panel displays normally

## Verification Steps (After Power-On)

### Step 1: Display Reading
Watch the serial log or HA for:
```
[I][tublemetry_display] Temperature: 104 F
```
If you see temperature readings, display decoding works.

If you see `Unknown 7-segment byte: 0xNN`, the voltage divider output may be noisy or the clock/data pins are swapped.

### Step 2: Button Injection
In HA, set the climate entity target temperature to something different (e.g., 99°F). Watch the serial log for:
```
[I][button_injector] Starting sequence: target 99F — 25 down + 19 up presses
[I][button_injector] Verified: display shows 99F — sequence successful
```
Watch the topside panel — the display should flash as the setpoint changes.

### Step 3: Closed-Loop Verification
After a button sequence completes, the display should show the new setpoint briefly, then return to showing actual water temperature. The climate entity in HA should show both current temp and target temp.

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| No display data (all sensors blank) | Clock/data not connected or swapped | Check GPIO16=clock, GPIO17=data. Check voltage divider output with multimeter |
| `Unknown 7-segment byte` warnings | Signal noise or incorrect voltage level | Check divider output is 3.0-3.5V. Try shorter wires. |
| Display shows garbage after connecting | ESP32 loading the signal lines | Check voltage dividers are correct — direct 5V to GPIO will also cause this |
| Phantom button presses | Noise on button lines or wrong photorelay wiring | Verify photorelays are fully open when GPIO is LOW. Check for stray connections |
| Button press has no effect | Wrong RJ45 pin, photorelay not switching | Verify pin 2=Temp Up, pin 8=Temp Down. Check LED resistor. Test photorelay with multimeter (resistance across pins 3-4 should drop when GPIO is driven high) |
| ESP32 boot loops | Power issue or short | Disconnect all RJ45 wires, verify ESP32 boots on USB alone. Reconnect one section at a time |
| WiFi disconnects frequently | ESP32 antenna too close to pump motor | Reposition ESP32 or add a small antenna extension |

## Wire Colors Reference (for your notes)

Fill in as you wire — helps when debugging later:

| Connection | Wire Color Used |
|-----------|----------------|
| GND (Pin 4 → GND bus) | _____________ |
| Clock (Pin 6 → divider) | _____________ |
| Data (Pin 5 → divider) | _____________ |
| +5V (Pin 1 → ESP32 VIN + relay commons) | _____________ |
| Temp Up (Pin 2 → relay A) | _____________ |
| Temp Down (Pin 8 → relay B) | _____________ |
| GPIO16 → divider output | _____________ |
| GPIO17 → divider output | _____________ |
| GPIO18 → relay A resistor | _____________ |
| GPIO19 → relay B resistor | _____________ |
