# External Integrations

**Analysis Date:** 2026-03-13

## APIs & External Services

**None detected.**

The codebase does not integrate with external APIs or cloud services. All operations are local or hardware-bound.

## Data Storage

**Databases:**
- Not applicable

**File Storage:**
- Local filesystem only
- Input data: CSV and TXT files stored locally in project directory
- Output data: TXT logs written to project directory (same location as scripts)

**Caching:**
- None

## Authentication & Identity

**Auth Provider:**
- None. This is a local analysis toolkit with no authentication requirements.

## Monitoring & Observability

**Error Tracking:**
- None

**Logs:**
- Console-based (stdout/stderr)
- File-based logs created during capture:
  - `rs485_capture.txt` - Interactive capture with user-marked button press events
  - Baud rate test logs: `9600.log`, `2400.log`, `4800.log`, `19200.log`
- No structured logging framework

## Hardware Integration (External)

**Serial Port Devices:**
- USB RS-485 adapter on `COM9` (Windows)
  - Communication: Balboa VS300FL4 hot tub controller board
  - Protocol: Proprietary VS-series synchronous clock+data protocol (not standard RS-485)
  - Direction: Board → Panel data stream (status/display output)
  - Baud: 115200 8N1
  - Implementation: `rs485_capture.py`, `rs485_scan.py`, `rs485_jets.py`

**Logic Analyzer:**
- Saleae Logic Analyzer (or compatible)
- Input channels: 8 (CH0-CH7), typically CH4 and CH5 used for display data
- Sample rate: 1 MHz
- Export format: CSV (8 channels)
- Data size: 10M+ rows (10+ seconds of capture)

## CI/CD & Deployment

**Hosting:**
- Not applicable

**CI Pipeline:**
- Not configured

## Environment Configuration

**Required env vars:**
- None in standard sense
- Windows-specific paths via environment:
  - `USERPROFILE` - Used for OneDrive path in `decode_oh.py`

**Secrets location:**
- Not applicable - no credentials in project

**Serial Port Configuration:**
- Hardcoded: `COM9` (Windows USB device)
- Hardcoded: 115200 baud, 8N1
- Not externalized to config file

## Hardware Protocol Details

**VS300FL4 Communication (Reverse-Engineered):**

**Idle/Heartbeat Frame (8 bytes, repeating ~100ms):**
```
FE 06 70 E6 00 06 70 00
```

**Button Press Response Patterns:**
- Temp Down: Burst `E6 77 E6 E6 77 E6 E6 77 E6 E0 FF`, modified frame with `00 F3` at end
- Temp Up: Burst `E6 77 E6 E6 77 E6 E6 77 E6 E0 FF`, modified frame with `03 18` mid-sequence
- Lights Toggle: Frame loses `FE` byte entirely for ~2.5s (e.g., `06 70 E6 00 06 70 00`)
- Jets: No change detected on monitored RS-485 pair

**Display Data Encoding (7-Segment Multiplexing):**
- Pin 5 (CH4): Display content stream
- Pin 6 (CH5): Display refresh/sync stream
- Protocol: 60Hz synchronization, clock-and-data pattern
- Display refresh: ~500ms on, ~500ms off flash pattern
- Segment mapping: Brute-force analysis in `analyze_protocol.py` tests multiple bit-to-segment mappings

**RJ45 Connector Pinout (VS300FL4 to Panel):**
- Pin 1: (unknown)
- Pin 3: (unknown)
- Pin 4, 5: Blue pair (power/ground)
- Pin 6, 7: (unknown)
- Pin 8: GND

*Note: Full pinout not fully mapped. Only board → panel data stream captured. Panel → board command channel on different wire pair not yet tapped.*

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None

## Related External Projects

**For Reference (Not Integrated):**
- `netmindz/balboa_GL_ML_spa_control` - GL/ML protocol (incompatible with VS300FL4)
- `MagnusPer/Balboa-GS510SZ` - GS series synchronous protocol (reference for similar architecture, different protocol)
- Balboa BWA 0x7E-framed protocol (BP series) - Different from VS series

---

*Integration audit: 2026-03-13*
