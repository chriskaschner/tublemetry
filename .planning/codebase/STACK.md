# Technology Stack

**Analysis Date:** 2026-03-13

## Languages

**Primary:**
- Python 3.x - All automation and analysis scripts

**Secondary:**
- None detected

## Runtime

**Environment:**
- Python 3.x (version not pinned in codebase)

**Package Manager:**
- pip (no lock file detected)
- No `requirements.txt` or `pyproject.toml` found

## Frameworks

**Core:**
- None (pure Python standard library and third-party packages)

**Testing:**
- None detected

**Build/Dev:**
- None detected

## Key Dependencies

**Hardware Communication:**
- `pyserial` - Serial port communication with RS-485 adapter (`import serial` in `rs485_capture.py`, `rs485_scan.py`, etc.)

**Data Analysis:**
- `numpy` - Numerical analysis for logic analyzer data (`decode_7seg.py` uses `np.loadtxt()`, `np.where()`, array operations)

**Standard Library:**
- `threading` - Concurrent input handling (`rs485_capture.py`)
- `queue` - Thread-safe queue for input (`rs485_capture.py`)
- `csv` - CSV file parsing (`decode_oh.py`)
- `time` - Timing and delays
- `sys` - System utilities
- `os` - File system operations
- `re` - Regular expressions (minimal usage)
- `collections` - Counter for frequency analysis (`analyze_protocol.py`)
- `itertools` - Permutation generation for mapping brute-force (`analyze_protocol.py`)

## Configuration

**Environment:**
- Hardcoded port: `COM9` (Windows USB RS-485 adapter) in `rs485_capture.py`, `rs485_scan.py`, `rs485_jets.py`
- Hardcoded baud rate: `115200` 8N1 (8 data bits, no parity, 1 stop bit)
- Data paths: `decode_7seg.py` uses OneDrive path hard-coded: `C:\Users\ckaschner\OneDrive - Electronic Theatre Controls, Inc\Desktop\485\OH.csv`
- `decode_oh.py` references Windows environment: `os.environ["USERPROFILE"]` for OneDrive paths

**Build:**
- No build configuration detected

## Platform Requirements

**Development:**
- Windows (scripts assume Windows serial port naming `COM9`, Windows file paths with OneDrive)
- Python 3.6+ recommended (uses f-strings, type hints not used)
- USB RS-485 adapter connected to COM9
- Logic analyzer for capture files (Saleae or similar, 1MHz sample rate, outputs CSV format)

**Production:**
- Not applicable - scripts are analysis/capture tools, not runtime services

## Hardware Integration

**RS-485 Communication:**
- Serial protocol: 115200 baud, 8N1
- Adapter: USB RS-485 (automatic RX/TX, not manual control via RE/DE pins)
- Connection: Y-connector on RJ45 cable between Balboa VS300FL4 hot tub controller and topside panel

**Logic Analyzer:**
- Supports Saleae Logic Analyzer CSV export (8 channels, configurable sample rate)
- Input: `OH.csv` (10M+ rows, captures at 1MHz)
- Output: Decoded UART at 115200 baud from two channels

## Data Formats

**Input:**
- CSV (logic analyzer output): `OH.csv`, `254.csv`
- TXT (raw serial captures): `rs485_capture.txt`, `rs485_jets.txt`, `teraterm.txt`, `hex.txt`
- LOG files (baud rate test outputs): `9600.log`, `2400.log`, etc.

**Output:**
- TXT (structured capture logs with timestamps and markers)
- Console output (UART decode results, pattern analysis)

## Known Dependencies Not Present

- No web framework (Flask, FastAPI, Django)
- No database ORM (SQLAlchemy)
- No async library (asyncio explicitly not used)
- No testing framework
- No CI/CD configuration

---

*Stack analysis: 2026-03-13*
