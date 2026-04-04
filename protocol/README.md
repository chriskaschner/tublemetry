# Balboa VS300FL4 Display Protocol -- Reverse Engineering

## TL;DR

The Balboa VS300FL4 with VL-series topside panels does **not** use RS-485. The
connection between the control board and panel is a **proprietary synchronous
clock+data protocol**: Pin 6 is a clock line (24 pulses per frame at 60Hz) and
Pin 5 carries 7-segment display data sampled on each clock rising edge.

This directory contains the scripts and notes from figuring that out.

## How We Determined It Wasn't RS-485

### The assumption

The RJ45 connector between the Balboa control board (J1) and the topside panel
looked like a textbook RS-485 setup. Community projects for other Balboa models
(GL/ML series) use RS-485 poll-response protocols, and some forum posts
reference RS-485 for VL panels too. We started with a Waveshare USB RS-485
adapter (SP485EEN) on what we assumed were the A/B differential pair (Pin 5
and Pin 6).

### What went wrong

The RS-485 adapter produced data -- 8-byte repeating frames at 115200 baud 8N1
-- but the bytes didn't match any known Balboa protocol. Different captures on
Pin 5 vs Pin 6 produced completely different patterns. Connecting the adapter
to Pin 6 corrupted the panel display (it showed "80" flashing). Button presses
only changed one byte in the frame, and jets produced zero change at all.

Every RS-485 wiring combination was tried (A/B swapped, different pin pairs,
grounding variations). All produced data that looked plausible but couldn't be
decoded consistently.

### The breakthrough: logic analyzer

An 8-channel logic analyzer (Lonely Binary, PulseView/sigrok) sampling all 8
RJ45 pins simultaneously at 4MHz revealed the truth:

1. **Pin 5 and Pin 6 are NOT a differential pair.** They are two independent
   digital signals with different timing characteristics.
2. **Pin 6 is a clock line.** It produces exactly 24 pulses per frame at 60Hz
   (16.7ms period), then goes idle until the next frame.
3. **Pin 5 is a data line.** Its transitions are synchronized to Pin 6's clock
   edges -- data is valid on each rising edge of Pin 6.
4. **24 bits per frame = 3 x 7-bit digits + 3 status bits.** This directly
   drives the panel's 7-segment displays and LED indicators.

The RS-485 adapter had been treating this synchronous bitstream as asynchronous
UART, which happened to produce somewhat coherent-looking bytes at 115200 baud
purely by coincidence. The actual protocol has no baud rate, no start/stop bits,
and no framing -- it's raw clocked serial.

### Confirmation: ladder capture

A temperature ladder capture (walking the setpoint from 105 down to 86 one
degree at a time) confirmed the 7-segment encoding for all digits 0-9 and
several mode characters (Ec, SL, St, OH). The encoding matches the
MagnusPer/Balboa-GS510SZ project (same protocol family) with one exception:
**"9" is 0x73 on the VS300FL4** vs 0x7B on the GS510SZ.

## RJ45 Pinout (Confirmed)

| Pin | T568B Color  | Function |
|-----|-------------|----------|
| 1   | Orange/White | +5V Power |
| 2   | Orange       | Button: Temp Up (analog, ~2.3V idle, ~4.7V pressed) |
| 3   | Green/White  | Button: Lights (analog) |
| 4   | Blue         | Ground |
| 5   | Blue/White   | Data (synchronous, 7-segment content) |
| 6   | Green        | Clock (24 pulses/frame at 60Hz) |
| 7   | Brown/White  | Button: Jets (analog) |
| 8   | Brown        | Button: Temp Down (analog) |

Buttons are analog -- each press pulls the pin from ~2.3V to ~4.7V. The board
reads them via ADC. Bridging Pin 1 (+5V) to a button pin simulates a press.

## 7-Segment Lookup Table

Segment mapping: `bit6=a, bit5=b, bit4=c, bit3=d, bit2=e, bit1=f, bit0=g`

| Hex  | Segments      | Character |
|------|---------------|-----------|
| 0x7E | a,b,c,d,e,f   | 0         |
| 0x30 | b,c           | 1         |
| 0x6D | a,b,d,e,g     | 2         |
| 0x79 | a,b,c,d,g     | 3         |
| 0x33 | b,c,f,g       | 4         |
| 0x5B | a,c,d,f,g     | 5 / S     |
| 0x5F | a,c,d,e,f,g   | 6         |
| 0x70 | a,b,c         | 7         |
| 0x7F | a,b,c,d,e,f,g | 8         |
| 0x73 | a,b,c,f,g     | 9 (VS300FL4 differs from GS510SZ 0x7B) |
| 0x00 | none          | blank     |
| 0x37 | b,c,e,f,g     | H         |
| 0x4F | a,d,e,f,g     | E         |
| 0x0D | d,e,g         | c         |
| 0x0E | d,e,f         | L         |
| 0x0F | d,e,f,g       | t         |

## Scripts

These scripts document the investigation process. The early scripts assume
RS-485 UART (which turned out to be wrong); the later ones work with logic
analyzer captures of the actual synchronous protocol.

### RS-485 era (wrong assumption, kept for reference)

| Script | Purpose |
|--------|---------|
| `rs485_scan.py` | Baud rate scanner -- tried 12 common rates, found 115200 "worked" |
| `rs485_capture.py` | Interactive capture with button press markers |
| `rs485_jets.py` | Focused single-button capture -- proved jets aren't on this stream |
| `scan_hex.py` | Deep scan of TeraTerm hex dump for non-idle byte values |
| `scan_teraterm.py` | Found display mode transitions (0x77 button-press, 0x67 Pr mode) |
| `analyze_protocol.py` | Exhaustive mapping search -- scored 40K permutations against known bytes |
| `bruteforce_7seg.py` | 7-segment brute-force v1 (5040 mappings, 0 solutions) |
| `bruteforce_7seg_v2.py` | v2: relaxed constraints, found 72 candidate solutions |
| `bruteforce_3digit.py` | 3-digit temperature variant (inconclusive) |

### Logic analyzer era (correct protocol)

| Script | Purpose |
|--------|---------|
| `decode_clockdata.py` | Synchronous clock+data decoder for sigrok CSV exports |
| `decode_csv.py` | Generic CSV UART decoder (single-ended, unreliable for differential) |
| `decode_oh.py` | OH.csv burst timing analyzer -- confirmed 60Hz refresh, Pin 5/6 sync |
| `decode_7seg.py` | OH.csv UART decoder -- 3-byte burst analysis on CH4/CH5 |
| `verify_magnusper.py` | Validates our findings against MagnusPer/Balboa-GS510SZ lookup table |

## Capture Setup (for future work)

Stub cable (T568B, cut end) into Monoprice RJ45 T-splitter at J1.
Logic analyzer clips onto bare wires:
- D0 -> Blue/White (Pin 5, Data)
- D1 -> Green (Pin 6, Clock)
- GND -> Blue (Pin 4, Ground)

```bash
sigrok-cli -d fx2lafw -c samplerate=1000000 --samples 10000000 --channels D0,D1 -o capture.sr
```

## Related Projects

| Project | Relevance |
|---------|-----------|
| [MagnusPer/Balboa-GS510SZ](https://github.com/MagnusPer/Balboa-GS510SZ) | Same protocol family, interrupt-driven Arduino/ESP8266. Our VS300FL4 lookup matches except "9". |
| [Shuraxxx/Balboa-GS523DZ](https://github.com/Shuraxxx/Balboa-GS523DZ) | Similar VL801D panel, same approach. |
| [netmindz/balboa_GL_ML_spa_control](https://github.com/netmindz/balboa_GL_ML_spa_control) | DIFFERENT protocol (ML smart panels, RS-485 FA/FB messages). Does NOT apply to VL panels. |

## Historical Notes

`rs485-status-2026-03-08.md` is a point-in-time snapshot from before the
protocol was identified. It documents the RS-485 investigation in detail,
including all the wrong turns. Kept for reference.
