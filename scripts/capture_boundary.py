#!/usr/bin/env python3
"""
Capture the hot tub setpoint + injection state across a TOU boundary.

Purpose: record exactly what the ESP32 button-injection does when the schedule
drives a DOWN-move (the known-fragile compounding path). Poll HA, log every
state transition (and a periodic heartbeat) to a timestamped JSONL, sampling
fast while injection is active so the press burst is captured at high resolution.

This is observation-only: it makes NO writes to HA.

Usage:
    uv run scripts/capture_boundary.py                 # runs until 22:25 local
    uv run scripts/capture_boundary.py --until 22:30
    uv run scripts/capture_boundary.py --minutes 180

Reuses HA / load_dotenv from diagnose_tou (same dir, same .env).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

# scripts/ is on sys.path[0] when run directly, so this resolves.
from diagnose_tou import (  # noqa: E402
    COMMANDED,
    DETECTED,
    INJECTION_PHASE,
    LAST_RESULT,
    RETRY,
    API_STATUS,
    HA,
    load_dotenv,
)
import os

EXPECTED = "sensor.hot_tub_expected_setpoint"

# Curated fields we always log, as {label: (candidate entity ids...)}.
CURATED = {
    "commanded": (COMMANDED,),
    "detected": (DETECTED,),
    "expected": (EXPECTED,),
    "phase": INJECTION_PHASE,
    "result": LAST_RESULT,
    "retry": (RETRY,),
    "esp32": (API_STATUS,),
}

# Extra tublemetry entities auto-discovered on first poll (water temp, heater, etc.)
EXTRA_KEYWORDS = ("water", "temp", "heater", "target")

IDLE_INTERVAL = 5.0   # seconds between polls when injection is idle
BUSY_INTERVAL = 1.5   # seconds between polls while a sequence is running
HEARTBEAT = 60.0      # force-log a line at least this often even with no change


def _pick_state(states: dict, ids) -> str | None:
    for i in ids:
        obj = states.get(i)
        if obj is not None:
            return obj.get("state")
    return None


def snapshot(states: dict, extras: list[str]) -> dict:
    row = {label: _pick_state(states, ids) for label, ids in CURATED.items()}
    for eid in extras:
        obj = states.get(eid)
        if obj is not None:
            row[eid] = obj.get("state")
    return row


def discover_extras(states: dict) -> list[str]:
    found = []
    for eid in states:
        if "tublemetry" not in eid:
            continue
        if eid in {v for ids in CURATED.values() for v in ids}:
            continue
        if any(k in eid for k in EXTRA_KEYWORDS):
            found.append(eid)
    return sorted(found)


def parse_until(s: str) -> datetime:
    hh, mm = (int(x) for x in s.split(":"))
    now = datetime.now()
    stop = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if stop <= now:
        stop += timedelta(days=1)
    return stop


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", default="22:25", help="local HH:MM to stop (default 22:25)")
    ap.add_argument("--minutes", type=int, default=None,
                    help="run for N minutes instead of --until")
    ap.add_argument("--out", default=None, help="output JSONL path")
    args = ap.parse_args()

    load_dotenv()
    base, token = os.environ.get("HA_URL"), os.environ.get("HA_TOKEN")
    if not base or not token:
        print("ERROR: set HA_URL and HA_TOKEN (env or .env).", file=sys.stderr)
        return 2
    client = HA(base, token)

    start = datetime.now()
    stop = (start + timedelta(minutes=args.minutes)) if args.minutes else parse_until(args.until)

    out_path = Path(args.out) if args.out else (
        Path(__file__).resolve().parent.parent
        / "docs/ha-migration"
        / f"boundary-capture-{start:%Y%m%d-%H%M}.jsonl"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[capture] start {start:%H:%M:%S} -> stop {stop:%H:%M:%S} local")
    print(f"[capture] logging to {out_path}")

    extras: list[str] = []
    prev: dict | None = None
    last_logged = 0.0

    with out_path.open("a") as fh:
        while datetime.now() < stop:
            now = datetime.now()
            try:
                states = client.states()
            except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
                err = {"ts": now.isoformat(timespec="seconds"), "error": str(e)}
                fh.write(json.dumps(err) + "\n")
                fh.flush()
                print(f"[capture] {now:%H:%M:%S} poll error: {e}")
                time.sleep(IDLE_INTERVAL)
                continue

            if not extras:
                extras = discover_extras(states)
                print(f"[capture] extra entities: {extras or 'none found'}")

            row = snapshot(states, extras)
            phase = (row.get("phase") or "").lower()
            busy = phase not in ("idle", "", "none", "unknown", "unavailable")

            changed = prev is None or any(row.get(k) != prev.get(k) for k in row)
            heartbeat = (time.monotonic() - last_logged) >= HEARTBEAT

            if changed or heartbeat:
                rec = {"ts": now.isoformat(timespec="seconds"),
                       "reason": "change" if changed else "heartbeat",
                       **row}
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
                last_logged = time.monotonic()
                if changed and prev is not None:
                    diffs = {k: (prev.get(k), row.get(k)) for k in row if row.get(k) != prev.get(k)}
                    print(f"[capture] {now:%H:%M:%S} {diffs}")
                elif prev is None:
                    print(f"[capture] {now:%H:%M:%S} baseline {row}")
                prev = row

            time.sleep(BUSY_INTERVAL if busy else IDLE_INTERVAL)

    print(f"[capture] done at {datetime.now():%H:%M:%S}; log: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
