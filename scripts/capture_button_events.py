#!/usr/bin/env python3
"""Capture Zigbee button events from the live Home Assistant event bus.

Observation-only: subscribes to HA's SSE event stream and prints every
deconz_event / zha_event it sees. Writes nothing back to HA.

Purpose: Zigbee remotes report gestures as opaque numeric codes
(deCONZ `buttonevent`, ZHA `command`) whose values vary by device model AND
firmware. Rather than hardcode what a datasheet claims, run this, press the
button, and read the real codes off your own hardware.

Usage:
    uv run scripts/capture_button_events.py                 # 60s, all devices
    uv run scripts/capture_button_events.py --seconds 120
    uv run scripts/capture_button_events.py --id roundbutton

Reads HA_URL / HA_TOKEN from the environment or the gitignored .env, same as
scripts/diagnose_tou.py.

deCONZ buttonevent codes are conventionally XXYY where XX is the button number
and YY is the action: 01=hold, 02=short release, 03=long release, 04=double,
05=triple. The GESTURE column below applies that convention as a *hint* only --
trust the observed sequence over the guess.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

# deCONZ buttonevent trailing-digit -> human gesture. Hint only; verify live.
DECONZ_ACTIONS = {
    "01": "HOLD (long press started)",
    "02": "SHORT RELEASE (single press)",
    "03": "LONG RELEASE (long press ended)",
    "04": "DOUBLE PRESS",
    "05": "TRIPLE PRESS",
    "06": "QUADRUPLE PRESS",
    "10": "MANY PRESSES",
}


def load_env() -> tuple[str, str]:
    """Return (base_url, token) from env, falling back to .env."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip("\"'"))

    base, token = os.environ.get("HA_URL"), os.environ.get("HA_TOKEN")
    if not base or not token:
        sys.exit("ERROR: set HA_URL and HA_TOKEN (env or .env).")
    return base.rstrip("/"), token


def describe(event_type: str, data: dict) -> str:
    """Best-effort human reading of a raw button event."""
    if event_type == "deconz_event":
        code = data.get("event")
        if code is None:
            return "(no 'event' field)"
        action = DECONZ_ACTIONS.get(f"{int(code) % 100:02d}", "UNKNOWN")
        return f"button={int(code) // 1000} action={action}"
    if event_type == "zha_event":
        return f"command={data.get('command')} args={data.get('args')}"
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seconds", type=int, default=60, help="listen duration")
    ap.add_argument("--id", default=None, help="only show this device id")
    args = ap.parse_args()

    base, token = load_env()
    url = f"{base}/api/stream?restrict=deconz_event,zha_event"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})

    print(f"Listening {args.seconds}s on {base} for deconz_event / zha_event...")
    print("Press the button now. Leave ~3s between gestures.\n")
    print(f"{'TIME':<13} {'EVENT TYPE':<14} {'DEVICE':<16} {'CODE':<8} GESTURE")
    print("-" * 88)

    seen: list[tuple[str, object]] = []
    try:
        with urllib.request.urlopen(req, timeout=args.seconds + 10) as stream:
            deadline = datetime.now().timestamp() + args.seconds
            for raw in stream:
                if datetime.now().timestamp() > deadline:
                    break
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data: ") or line == "data: ping":
                    continue
                try:
                    evt = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue

                etype = evt.get("event_type", "")
                data = evt.get("data", {})
                dev = str(data.get("id") or data.get("device_id") or "?")
                if args.id and dev != args.id:
                    continue

                code = data.get("event", data.get("command", "?"))
                stamp = datetime.now().strftime("%H:%M:%S.%f")[:12]
                print(f"{stamp:<13} {etype:<14} {dev:<16} {str(code):<8} {describe(etype, data)}")
                sys.stdout.flush()
                seen.append((dev, code))
    except KeyboardInterrupt:
        print("\n(interrupted)")

    print("-" * 88)
    if not seen:
        print("NO EVENTS CAPTURED. Check the button is awake and paired.")
        return 1

    print(f"\n{len(seen)} event(s). Distinct codes, in first-seen order:")
    ordered: list[tuple[str, object]] = []
    for pair in seen:
        if pair not in ordered:
            ordered.append(pair)
    for dev, code in ordered:
        print(f"  id={dev!r}  event={code}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
