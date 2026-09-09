#!/usr/bin/env python3
"""Measure deCONZ freeze episodes precisely, for before/after comparison.

Observation-only: polls HA's REST API and writes a local JSONL. Writes nothing
back to HA.

WHY THIS EXISTS
The deCONZ add-on process hangs for 20-110 min at a time (see WORKLOG.md
2026-09-09). Reading `binary_sensor.*` state history is a poor measuring stick
for that, because HA does not mark entities `unavailable` until a median 8.5
minutes AFTER the process actually stops responding. That lag is bigger than
some of the effects we want to measure.

This watches a livelier signal instead: `last_reported` on a deCONZ sensor that
reports every few minutes. When the add-on freezes, that timestamp stops
advancing immediately. Detection lands within one poll interval of the real
freeze rather than 8.5 minutes late.

The whole point is A/B measurement. Run it for a day, change exactly one thing
(disable VNC, switch add-on, etc.), run it again, and diff the two summaries:

    uv run scripts/watch_deconz_health.py --hours 24 --label baseline
    ... make ONE change ...
    uv run scripts/watch_deconz_health.py --hours 24 --label vnc-off
    uv run scripts/watch_deconz_health.py --summarize

The CONTROL entity is what keeps this honest. It is a non-deCONZ (ESPHome)
sensor on the same HA instance. If it stalls at the same moment, the fault is
HA, the network, or this laptop's connection -- NOT deCONZ -- and the episode is
recorded as `control_also_stalled` so it can be excluded rather than silently
inflating the deCONZ numbers.

Reads HA_URL / HA_TOKEN from the environment or the gitignored .env, same as
scripts/diagnose_tou.py.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Reports every ~5 min, so a stall is obvious fast. This is the freeze detector.
DECONZ_PROBE = "sensor.temperature_3"

# Non-deCONZ, same HA instance. Distinguishes "deCONZ froze" from "HA/network/
# laptop died", which otherwise look identical from here.
CONTROL_PROBE = "sensor.tublemetry_hot_tub_wifi_signal"

# The probe reports every ~5 min; 12 min of silence is a freeze, not a gap.
STALL_MINUTES = 12.0

LOG_PATH = Path(__file__).resolve().parent.parent / "docs" / "ha-migration" / "deconz-health.jsonl"


def load_env() -> tuple[str, str]:
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
        print("ERROR: set HA_URL and HA_TOKEN (env or .env). See --help.", file=sys.stderr)
        raise SystemExit(2)
    return base.rstrip("/"), token


def last_reported(base: str, token: str, entity: str) -> tuple[datetime | None, str]:
    """Return (last_reported, state). last_reported is None if HA is unreachable."""
    req = urllib.request.Request(
        f"{base}/api/states/{entity}", headers={"Authorization": f"Bearer {token}"}
    )
    try:
        d = json.load(urllib.request.urlopen(req, timeout=15))
    except (urllib.error.URLError, TimeoutError, OSError):
        return None, "ha_unreachable"
    ts = d.get("last_reported") or d.get("last_updated")
    return datetime.fromisoformat(ts), d.get("state", "?")


def watch(base: str, token: str, hours: float, interval: int, label: str) -> int:
    end_at = datetime.now(timezone.utc) + timedelta(hours=hours)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    print(f"watching {DECONZ_PROBE} (control: {CONTROL_PROBE})")
    print(f"label={label}  for {hours}h  every {interval}s  stall threshold {STALL_MINUTES} min")
    print(f"appending to {LOG_PATH}\n")

    frozen = False
    freeze_start: datetime | None = None
    control_stalled_during = False
    episodes = 0

    while datetime.now(timezone.utc) < end_at:
        now = datetime.now(timezone.utc)
        d_rep, d_state = last_reported(base, token, DECONZ_PROBE)
        c_rep, _c_state = last_reported(base, token, CONTROL_PROBE)

        if d_rep is None:
            # Can't reach HA at all -- our own problem, not deCONZ's. Skip.
            time.sleep(interval)
            continue

        d_age = (now - d_rep).total_seconds() / 60
        c_age = (now - c_rep).total_seconds() / 60 if c_rep else 0.0
        stalled = d_age > STALL_MINUTES or d_state == "unavailable"

        if stalled and not frozen:
            frozen, freeze_start = True, now
            control_stalled_during = c_age > STALL_MINUTES
            print(f"  {now.astimezone():%m-%d %H:%M:%S}  FREEZE START "
                  f"(probe silent {d_age:.1f} min, state={d_state})")
        elif stalled and frozen:
            control_stalled_during = control_stalled_during or c_age > STALL_MINUTES
        elif not stalled and frozen:
            dur = (now - freeze_start).total_seconds() / 60
            episodes += 1
            rec = {
                "label": label,
                "event": "freeze",
                "start": freeze_start.isoformat(),
                "end": now.isoformat(),
                "minutes": round(dur, 1),
                "control_also_stalled": control_stalled_during,
            }
            LOG_PATH.open("a").write(json.dumps(rec) + "\n")
            tag = "  [CONTROL ALSO STALLED -- not deCONZ]" if control_stalled_during else ""
            print(f"  {now.astimezone():%m-%d %H:%M:%S}  RECOVERED after {dur:.1f} min{tag}")
            frozen, freeze_start, control_stalled_during = False, None, False

        time.sleep(interval)

    LOG_PATH.open("a").write(json.dumps({
        "label": label, "event": "window",
        "end": datetime.now(timezone.utc).isoformat(), "hours": hours,
    }) + "\n")
    print(f"\ndone: {episodes} freeze episodes in {hours}h under label '{label}'")
    return 0


def summarize() -> int:
    if not LOG_PATH.exists():
        print(f"no data yet at {LOG_PATH}", file=sys.stderr)
        return 1
    runs: dict[str, dict] = {}
    for line in LOG_PATH.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        acc = runs.setdefault(r["label"], {"freezes": [], "hours": 0.0})
        if r["event"] == "freeze" and not r.get("control_also_stalled"):
            acc["freezes"].append(r["minutes"])
        elif r["event"] == "window":
            acc["hours"] += r["hours"]

    print(f"{'label':22s} {'hours':>7s} {'episodes':>9s} {'per day':>8s} {'down %':>8s} {'median':>8s}")
    for label, acc in runs.items():
        f, h = acc["freezes"], acc["hours"]
        if not h:
            continue
        down = sum(f) / 60
        med = sorted(f)[len(f) // 2] if f else 0
        print(f"{label:22s} {h:7.1f} {len(f):9d} {len(f) / (h / 24):8.1f} "
              f"{100 * down / h:7.1f}% {med:7.1f}m")
    print("\nEpisodes where the control entity also stalled are excluded -- those were\n"
          "HA/network/laptop outages, not deCONZ freezes.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--hours", type=float, default=24.0, help="how long to watch (default: 24)")
    ap.add_argument("--interval", type=int, default=60, help="poll seconds (default: 60)")
    ap.add_argument("--label", default="baseline", help="tag this run for A/B comparison")
    ap.add_argument("--summarize", action="store_true", help="print all runs and exit")
    args = ap.parse_args()

    if args.summarize:
        return summarize()
    base, token = load_env()
    return watch(base, token, args.hours, args.interval, args.label)


if __name__ == "__main__":
    raise SystemExit(main())
