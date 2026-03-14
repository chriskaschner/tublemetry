# RS-485 Hot Tub Project — Status as of 2026-03-08

## Project Goal

Automate hot tub temperature setpoint via Home Assistant to execute TOU rate
optimization (drop to 99°F on-peak, reheat to 104°F before evening soak).
Eliminates twice-daily manual adjustments, saves ~$10/month on MGE Rg-2A rate.

---

## Hardware

- **Hot Tub:** Strong Spas Rockport S6-0001 (Costco "Evolution" / "Convertible Spa")
- **Control Board:** Balboa VS300FL4 (PCB: VS500Z, P/N 22972_E2)
- **Topside Panel:** VL-series (VL401/VL403/VL406U) — "dumb" panel, no microcontroller
- **Electrical:** 240V, 4kW heater, 2BHP two-speed pump
- **Connection:** RJ45 between board (J1) and topside panel
- **Tap Method:** Monoprice RJ45 T-splitter at J1, sacrificial Cat5 to Wago breakout

---

## Complete RJ45 Pinout (CONFIRMED)

Two cables connect J1 (board) to the topside panel. Pin orientation is identical
in both; only the wire colors differ.

| Pin | T568B patch cable | OEM panel cable | Function                        |
|-----|-------------------|-----------------|---------------------------------|
| 1   | Orange/White      | Brown           | **+5V Power**                   |
| 2   | Orange            | Blue            | **Button: Temp Up** (analog)    |
| 3   | Green/White       | Yellow          | **Button: Lights** (analog)     |
| 4   | Blue              | Green           | **Ground**                      |
| 5   | Blue/White        | Red             | **RS-485 Data** (board→panel display content) |
| 6   | Green             | Black           | **RS-485 Data** (board→panel display refresh)  |
| 7   | Brown/White       | Orange          | **Button: Jets** (analog)       |
| 8   | Brown             | Grey            | **Button: Temp Down** (analog)  |

The T568B patch cable runs from the board J1 to an RJ45 T-splitter.
The OEM cable runs from the T-splitter to the topside panel (factory-installed,
non-standard wire colors).

### How pinout was confirmed
- **Multimeter:** Orange/White to Blue = 5V (power/ground identification)
- **Logic analyzer** (Lonely Binary 8ch, PulseView/Sigrok): All 8 pins captured
  simultaneously at 4MHz. Identified Pin 5 and Pin 6 as RS-485 data (transitions),
  all others as steady-state. Captures: `254.sr`, `OH.csv`
- **RS-485 adapter** (Waveshare USB, SP485EEN): Decoded UART at 115200 8N1 on
  Pin 5 (board→panel heartbeat) and Pin 6 (display refresh stream)
- **Multimeter button testing:** Each button pin measured while pressing all 4 buttons

---

## Button Input — Analog Voltage Matrix

Buttons are NOT digital/UART. The board reads 4 analog pins via ADC.
Each button press pulls exactly ONE pin from ~2.3V idle to ~4.7V.

| Button    | Spike Pin               | Idle   | Pressed |
|-----------|-------------------------|--------|---------|
| Temp Up   | Pin 2 (Orange)          | 2.82V  | 4.69V   |
| Temp Down | Pin 8 (Brown)           | 2.26V  | 4.70V   |
| Lights    | Pin 3 (Green/White)     | 2.27V  | 4.71V   |
| Jets      | Pin 7 (Brown/White)     | 2.26V  | 4.71V   |

### Manual button simulation: CONFIRMED WORKING
- Briefly bridging Pin 1 (+5V) to Pin 8 (Temp Down) successfully lowered the
  displayed temperature setpoint by 1°F
- This proves an ESP32 can inject button presses by driving the correct pin high

### Sensitivity warning
- The analog button lines are sensitive to loading/noise
- Even an unterminated Cat5 breakout cable caused phantom Temp Up presses
- ESP32 circuit MUST use high-impedance isolation when idle (analog switches
  or MOSFETs, not bare GPIO)

---

## RS-485 Data Streams (Board → Panel)

### Bus Parameters
- **Baud rate:** 115,200
- **Data format:** 8N1
- **Protocol:** Balboa GL/ML display protocol — NOT standard BWA `0x7E`-framed
- **Architecture:** Two simplex RS-485 channels (both board→panel), NOT half-duplex

### Protocol type
The VS300FL4 with VL-series topsides uses the **Balboa GL/ML display protocol**.
VL panels are "dumb" — no microcontroller. The board directly drives the panel's
7-segment displays and LEDs via continuous serial data. Reference project:
`github.com/netmindz/balboa_GL_ML_spa_control`

### Pin 5 (Blue/White) — Display Content Stream

**Idle/Heartbeat Frame:**
```
FE 06 70 E6 00 06 70 00
```
8-byte repeating frame, continuous, ~110ms between chunks. These bytes are
7-segment bitmap data encoding the current temperature display.

**Button Press Responses (board status changes on this stream):**

- **Temp Down** (~2s delay): burst `E6 77 E6 E6 77 E6 E6 77 E6 E0 FF`,
  modified frame `06 70 E6 00 00 06 00 F3`
- **Temp Up** (~0.5s delay): modified frame `06 70 E6 00 00 03 18 00`,
  same burst pattern
- **Lights** (~0.5s delay): `FE` byte drops from frame (7 bytes instead of 8)
- **Jets:** No change detected on this stream

**Byte 4 varies with temperature:** `E6` in some captures, `0x30` in others.
These are different 7-segment patterns for different temperature digits.

### Pin 6 (Green) — Display Refresh Stream

Continuous repeating pattern, no variation on button presses:
```
77 E6 E6 77 E6 E6 77 E6 E6 FF
```
Likely the multiplexing/refresh signal for the 7-segment display. Captured via
RS-485 adapter on Green pair (A=Green/White, B=Green, GND=Blue).

**Caution:** Connecting the RS-485 adapter to this pair caused display corruption
(panel showed "80" flashing). The adapter loads the line and interferes with
display refresh.

---

## What We Don't Know Yet

1. **7-segment lookup table** — need captures at known temperatures to map byte
   values to displayed digits
2. **Full display protocol structure** — frame boundaries, which bytes map to
   which display digits/LEDs
3. **ESP32 circuit design** — analog switch IC selection, voltage levels,
   impedance matching for button injection
4. **Whether we need to read the RS-485 streams** — if we only need to inject
   button presses (temp up/down), we may not need to decode the display protocol
   at all. But reading current temp from the display stream would enable
   closed-loop control.

---

## Capture Files

| File | Description |
|------|-------------|
| `254.sr` | Logic analyzer: 4MHz, 2M samples, 8 channels, idle tub. First full pinout identification |
| `254.csv` | CSV export of 254.sr |
| `OH.csv` | Logic analyzer: 1MHz, 10M samples, 8 channels, "OH" (overheat) display flashing |
| `rs485_capture.txt` | 72s Python RS-485 capture on Pin 5, 4 button markers, pattern frequency summary |
| `rs485_jets.txt` | 30s focused capture on Pin 5, 8 jets presses, no bus change detected |
| `teraterm.txt` | TeraTerm hex dump — mangled by UTF-8. Less trustworthy than Python |
| `hex.txt` | Cleaner hex dump, shows `30` in byte 4 (different temp than Python capture) |
| `rs485_capture.py` | Interactive capture script with button markers (in $TEMP) |
| `rs485_jets.py` | Focused single-button capture script (in $TEMP) |
| `rs485_scan.py` | Baud rate scanner (in $TEMP) |

---

## Next Steps

### Phase 1: ESP32 Button Injection (MVP)
**Goal:** ESP32 connected to Home Assistant can press Temp Up and Temp Down.

1. **Select analog switch IC** — need 4-channel analog switch (e.g., CD4066,
   DG408, or similar) that can switch ~5V with high off-impedance
2. **Build circuit:** ESP32 GPIO → analog switch → button pins. Pull-up to +5V
   through the switch when "pressing", high-Z when idle
3. **ESPHome integration:** Expose as buttons or a climate entity in Home Assistant
4. **Automation:** Time-based schedule — lower temp at on-peak start, raise before
   evening soak

### Phase 2: Closed-Loop Control (Optional)
**Goal:** Read current temperature from RS-485 display stream.

1. Map 7-segment byte values to temperature digits
2. ESP32 + MAX485 reads Pin 5 display stream
3. Climate entity shows actual temp + setpoint
4. Automation can verify temp changes took effect

---

## Tools & Environment

- **Logic analyzer:** Lonely Binary 8ch 24MHz USB + PulseView (Sigrok)
- **RS-485 adapter:** Waveshare USB (FT232RL + SP485EEN) on COM9
- **Capture scripts:** Python (`C:\dev\.venv\Scripts\python`)
- **Multimeter:** Used for voltage measurements on all 8 RJ45 pins
- **Tap hardware:** Monoprice RJ45 T-splitter, Cat5 cable, Wago connectors

# Balboa VS300FL4 RS485 Reverse Engineering

## Hardware Setup
- **Control Board:** Balboa VS300FL4
- **Connection:** RJ45 (8 wires / 4 pairs) between control board and topside panel
- **RS485 Adapter:** USB to RS485 on COM9
- **Tap Point:** Y-connector at the main board

## Confirmed Parameters
- **Baud Rate:** 115200
- **Data Format:** 8N1 (8 data bits, no parity, 1 stop bit)
- **Protocol:** Proprietary — NOT standard Balboa 7E-framed protocol

## What We're Seeing

We're currently tapped into **one pair** of the RJ45, which carries the **board → panel status/display stream**.

### Idle/Heartbeat Frame
```
FE 06 70 E6 00 06 70 00
```
8-byte repeating frame, continuous, ~100ms between chunks.

### Button Press Responses (board status changes)

**Temp Down** (~2s delay after press):
1. Burst pattern: `E6 77 E6 E6 77 E6 E6 77 E6 E0 FF` (10-byte repeating)
2. Modified frame: `06 70 E6 00 00 06 00 F3` (8-byte, note `00 F3` replacing `70 00`)
3. Cycles between burst and modified frame, then returns to idle

**Temp Up** (~0.5s delay after press):
1. Modified frame: `06 70 E6 00 00 03 18 00` (9-byte, note `03 18` replacing `06 70`)
2. Same burst pattern: `E6 77 E6 E6 77 E6 E6 77 E6 E0 FF`
3. Cycles between these, then returns to idle

**Lights** (~0.5s delay after press):
- The `FE` byte drops out of the frame entirely
- Idle: `FE 06 70 E6 00 06 70 00` (8 bytes)
- Lights active: `06 70 E6 00 06 70 00` (7 bytes, no FE)
- Persists ~2.5s, then FE returns

**Jets:**
- **No change detected on this pair** across 8 button presses
- Jets physically turned on/off normally — button works fine
- Confirmed: jet state is not encoded in this data stream (or not on this wire pair)

## Key Observations

1. **FE appears to be a status/flag byte** — present during idle, absent during lights toggle
2. **Different command signatures in status stream:**
   - Temp up: `00 03 18`
   - Temp down: `00 06 00 F3`
3. **`E6 77 E6 E6 77 E6 E6 77 E6 E0 FF` burst** — appears to be a display update/acknowledgment pattern, common to both temp buttons
4. **We're only hearing one side of the conversation** — the board → panel status channel

## What's Missing

The **panel → board button command channel** is on a different wire pair in the RJ45. This is why:
- Temp/lights show changes: the board's STATUS output updates to reflect the new state
- Jets show nothing: the board's status stream doesn't visibly change when jets toggle

## Next Steps

### 1. Identify the Wire Pairs
With a multimeter on the RJ45 Y-connector:
- **Find power pairs:** Check for ~12V DC between pins. Those are power/ground — skip them.
- **Find current data pair:** The pair your RS485 A/B is currently connected to.
- **Find the other data pair:** The remaining pair carries panel → board commands.

### Standard RJ45 pair mapping (T-568B):
| Pair | Pins | Colors (T-568B) |
|------|------|-----------------|
| 1    | 4, 5 | Blue            |
| 2    | 1, 2 | Orange          |
| 3    | 3, 6 | Green           |
| 4    | 7, 8 | Brown           |

### 2. Capture the Other Data Pair
Move RS485 adapter A/B to the other non-power pair and run the same capture to see button commands.

### 3. Full Protocol Decode
Once both directions are captured, we can:
- Map all button command bytes
- Understand the full request/response protocol
- Build an ESPHome or Home Assistant integration

## Tools

All capture scripts are in `$TEMP`:
- `rs485_scan.py` — Baud rate scanner (tries 12 common rates)
- `rs485_capture.py` — Interactive capture with button markers
- `rs485_jets.py` — Focused capture for single-button testing

### Running the scripts
```powershell
# In PowerShell:
C:\dev\.venv\Scripts\python "$env:TEMP\rs485_scan.py"
C:\dev\.venv\Scripts\python "$env:TEMP\rs485_capture.py"
C:\dev\.venv\Scripts\python "$env:TEMP\rs485_jets.py"
```

## Capture Files
- `rs485_capture.txt` — Full 72s capture with temp down, temp up, lights, jets markers
- `rs485_jets.txt` — Focused 30s jets-only capture (8 presses, no bus change detected)

# RS-485 Hot Tub Integration — Project Context

## Goal

Integrate the hot tub with Home Assistant so that the water temperature setpoint
can be automated on a schedule. This eliminates manual setpoint adjustments that
are currently required to execute the TOU rate optimization strategy.

The TOU strategy (drop to 99°F during on-peak hours, reheat to 104°F before
evening soak) saves ~$10/month but requires remembering to manually change the
setpoint twice a day. Automation via HA would make it hands-off.

---

## Hot Tub Hardware

- **Model:** Strong Spas Rockport S6-0001 (sold through Costco as "Evolution" /
  "Convertible Spa")
- **Construction:** Rotomolded, ~300-gallon capacity, 6 jets
- **Heater:** 4kW stainless steel
- **Pump:** 2BHP two-speed
- **Electrical:** 120V/240V convertible — currently running 240V
- **Control board:** Balboa VS300FL4 (PCB is VS500Z, P/N 22972_E2)
- **Topside panel:** VL-series (VL401/VL403/VL406U)
- **Serial number:** 072825-R013 (manufactured July 28, 2025)

---

## Why Not the Official WiFi Module?

The Balboa BWA WiFi module (part 50350) requires a BP-series board. The VS300FL4
is **incompatible**. No plug-and-play WiFi option exists for this board.

---

## RS-485 Approach

The topside panel communicates with the VS300FL4 board via RS-485 over an RJ45
cable. Community projects have decoded the Balboa RS-485 protocol for BP/GS-series
boards. The VS300FL4 uses the same VS500Z PCB and the same J1/J1A connector
architecture, so it almost certainly speaks the same protocol — but this is
**unconfirmed for VS-series specifically**. That's what Phase 1 verifies.

### Physical connector confirmed

The topside panel cable uses a **standard 8-pin RJ45 plug** on a flat ribbon
26AWG 300V cable. Photos were taken of the board and the plug was confirmed to be
completely standard form factor.

### Board connector layout (from photos)

- **J1:** Populated RJ45 jack — this is where the topside panel cable plugs in
- **J1A:** Unpopulated RJ45 footprint on the board (parallel to J1, same bus)
- **J2, J2A:** Unpopulated RJ45 footprints

J1A being an identical unpopulated RJ45 footprint confirms that soldering a
connector there would give a second tap point. However, the chosen approach is
simpler: a T-splitter at J1.

---

## Phase 1: Passive Protocol Verification

**Goal:** Confirm the VS300FL4 speaks the Balboa RS-485 protocol before spending
more money.

### Shopping List (~$18 total)

| Item | Amazon Link | ~Cost |
|---|---|---|
| Monoprice RJ45 T-adapter, 8P8C, 1F→2F, parallel wiring | amazon.com/dp/B0069LVUPS | $6 |
| Waveshare USB RS-485 adapter (FT232RL + SP485EEN chip) | amazon.com/dp/B081MB6PN2 | $10–12 |

Plus two short Cat5/6 patch cables:
- **Cable 1 (intact):** J1 on board → T-splitter port 1
- **Cable 2 (sacrificial):** T-splitter port 2 → cut end → wires into RS-485
  adapter screw terminals

The topside panel cable (existing) plugs into T-splitter port 3. It is **not
modified in any way**.

Note on the T-splitter: it has three female ports, so both cables connecting to
it need male RJ45 plugs. The existing topside cable already has a male plug.

### Physical chain

```
Board J1 (female)
    ↓
[Cable 1: short patch cable]
    ↓
T-splitter port 1 (female)
    ├── port 2: existing topside panel cable (undisturbed)
    └── port 3: Cable 2 (sacrificial)
                    ↓
           Cut end — identify 3 wires
                    ↓
           RS-485 adapter screw terminals (A, B, GND)
                    ↓
           USB → laptop
```

### Setup steps

1. Install T-splitter between J1 and topside panel cable
2. Connect cut cable to RS-485 adapter screw terminals
3. Open serial terminal on laptop: **115,200 baud, 8N1**
4. Watch for data while pressing topside panel buttons

### Identifying which RJ45 pins are RS-485 A/B

Before connecting the adapter, use a multimeter to identify:
- 12V pin and GND pin (measure relative to chassis ground)
- Remaining pins are RS-485 candidates
- RS-485 A and B sit at ~2–3V differential at rest

Community research suggests pins 4 and 5 (center pair in standard RJ45) carry
RS-485 on Balboa boards, but **measure before connecting** — don't assume.

### What success looks like

You should see binary data in the terminal. Compare against Balboa protocol:
https://github.com/ccutrer/balboa_worldwide_app/blob/master/doc/protocol.md

Known Balboa message framing: `0x7E [len] [msg_type] [data...] [crc] 0x7E`

**GO condition:** Seeing `0x7E` byte framing in the stream, especially correlated
with button presses → proceed to Phase 2.

**NO-GO condition:** Garbage that doesn't match this framing → VS-series may use
a different protocol; reassess before spending more.

---

## Phase 2: Home Assistant Integration (if Phase 1 succeeds)

### Additional hardware (~$25–35)

| Item | ~Cost |
|---|---|
| ESP32 dev board (any common variant) | $10–15 |
| MAX485 RS-485 transceiver module | $5 |
| 5V buck converter (or power from USB) | $5 |
| Small enclosure, zip ties | $5 |

### Software: ESPHome path (preferred)

ESPHome has a `balboa_spa` external component. If the protocol matches, this
gives native Home Assistant entities with no MQTT broker or extra services
required.

Repos to evaluate (in order of preference):
1. **mhetzi's ESPHome Balboa** (most actively maintained):
   https://github.com/mhetzi/esphome_balboa_spa
2. **brianfeucht's version** (fallback):
   https://github.com/brianfeucht/esphome-balboa-spa

### HA entities you'd get (if protocol matches)

- Water temperature (sensor)
- Set point (number entity — **this is the one you need for automation**)
- Heating state (binary sensor)
- Pump state (switch)
- Filter cycle status

### Automation goal

Once the setpoint is a HA number entity, a simple time-based automation handles
the TOU schedule:
- Weekdays 5:30am → setpoint 104°F (morning soak prep)
- Weekdays 7:00am → setpoint 99°F (coast through on-peak)
- Weekdays 4:00pm → setpoint 104°F (evening soak prep)
- Weekdays 9:00pm → setpoint 99°F (post-soak drop)

---

## Decision Tree

```
Hardware arrives
    ↓
Install T-splitter, connect cut cable to RS-485 adapter
    ↓
Open serial terminal: 115200 baud 8N1
    ↓
See 0x7E framing? ──No──→ VS-series unconfirmed; post findings to
    ↓ Yes              ccutrer/balboa_worldwide_app GitHub issues
Buy ESP32 + MAX485
    ↓
Flash ESPHome with mhetzi's balboa component
    ↓
Entities appear in HA?
    ↓ Yes
Build TOU time-based automation
```

---

## Context: Why This Matters

The tub costs ~$90/month to run in a Wisconsin winter (MGE TOU rate Rg-2A).
The current manual setpoint strategy saves ~$10/month but requires twice-daily
manual adjustments. Automation removes that friction without changing the
strategy.

The setpoint strategy itself: dropping to 99°F during on-peak hours (10am–9pm
weekdays) costs less in total heat loss than holding 104°F all day, even after
accounting for the on-peak reheat spike before the evening soak. The savings
come from reduced heat loss during the low-setpoint window, not from rate
arbitrage.

MGE TOU periods (winter Rg-2A, weekdays only):
- Off-peak: 9pm–10am — $0.140/kWh
- On-Peak 1 (10am–1pm) — $0.236/kWh
- On-Peak 2 (1pm–6pm) — $0.233/kWh
- On-Peak 3 (6pm–9pm) — $0.238/kWh
- Weekends + major holidays: always off-peak

---

## Key References

- Balboa protocol documentation:
  https://github.com/ccutrer/balboa_worldwide_app/blob/master/doc/protocol.md
- ccutrer community wiki (physical layer pinout):
  https://github.com/ccutrer/balboa_worldwide_app/wiki
- VS300FL4 tech sheet (Balboa P/N 54626-02):
  Available at balboawater.com — board is VS500Z PCB P/N 22972_E2
- mhetzi ESPHome component:
  https://github.com/mhetzi/esphome_balboa_spa