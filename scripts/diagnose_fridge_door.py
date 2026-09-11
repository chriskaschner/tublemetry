#!/usr/bin/env python3
"""Diagnose false 'fridge door open' alerts from binary_sensor.fridge_door.

Observation-only: reads HA history and writes nothing back.

The SNZB-04PR2 door sensor drives an escalating push alert (ha/fridge_door.yaml).
When those alerts fire while the door is visibly shut, there are only a few
candidate causes, and this script separates them by looking at the state
timeline rather than guessing:

  1. Mesh dropouts -- the device goes 'unavailable' and returns. If it returns
     as 'on' while the door is shut, every such recovery is a false alert. This
     is the signature to look for: an OPEN episode whose previous state is
     'unavailable' rather than 'off'.
  2. A stuck / misaligned magnet -- long OPEN episodes that begin from 'off'
     and end from 'off', with no dropout involved.
  3. Reed chatter -- sub-minute open/close pulses. Real, but harmless here
     because the alert requires the door to hold open past the threshold.

IMPORTANT: HA's /api/history/period endpoint defaults end_time to start + 1 day.
Long windows silently return only the first day unless end_time is passed. This
script always passes it explicitly.

Usage:
    uv run scripts/diagnose_fridge_door.py
    uv run scripts/diagnose_fridge_door.py --days 14
    uv run scripts/diagnose_fridge_door.py --entity binary_sensor.fridge_door

Reads HA_URL / HA_TOKEN from the environment or the gitignored .env, same as
scripts/diagnose_tou.py.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_ENTITY = "binary_sensor.fridge_door"

# A second Zigbee device. If it drops out at the SAME timestamps as the door
# sensor, the problem is the coordinator/integration, not the door sensor's
# radio link -- one weak device cannot take another device offline.
PEER_ZIGBEE = "sensor.ac_vent_temperature"

# A non-Zigbee entity on the same HA instance (ESPHome over WiFi). If it stays
# available through the Zigbee dropouts, HA itself is healthy and the fault is
# isolated to the Zigbee stack. If it drops too, suspect HA restarts or the host.
CONTROL_ENTITY = "sensor.tublemetry_hot_tub_temperature"

# Mirrors the automation's floor (input_number.fridge_door_open_minutes min: 3).
# An OPEN episode shorter than this can never have produced a push.
ALERT_THRESHOLD_MIN = 3.0


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
        print("ERROR: set HA_URL and HA_TOKEN (env or .env). See --help.", file=sys.stderr)
        raise SystemExit(2)
    return base.rstrip("/"), token


def fetch_history(base: str, token: str, entity: str, days: int) -> list[tuple[datetime, str]]:
    """Return [(local_datetime, state)] for `entity` over the last `days` days."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    url = (
        f"{base}/api/history/period/{start.isoformat()}"
        f"?filter_entity_id={entity}"
        f"&end_time={urllib.parse.quote(end.isoformat())}"
        f"&minimal_response"
    )
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        payload = json.load(urllib.request.urlopen(req, timeout=60))
    except urllib.error.HTTPError as e:
        print(f"ERROR: HA returned {e.code} {e.reason} -- check HA_URL / token.", file=sys.stderr)
        raise SystemExit(1)

    if not payload or not payload[0]:
        print(f"ERROR: no history for {entity} in the last {days}d.", file=sys.stderr)
        raise SystemExit(1)

    out = []
    for row in payload[0]:
        ts = row.get("last_changed") or row.get("last_updated")
        out.append((datetime.fromisoformat(ts).astimezone(), row["state"]))
    return out


def unavailability(seq: list[tuple[datetime, str]]) -> tuple[int, float, float]:
    """Return (episode_count, hours_unavailable, pct_of_window) for a state sequence."""
    seq = seq + [(datetime.now().astimezone(), "NOW")]
    window = (seq[-1][0] - seq[0][0]).total_seconds()
    secs = sum(
        (seq[i + 1][0] - seq[i][0]).total_seconds()
        for i in range(len(seq) - 1)
        if seq[i][1] == "unavailable"
    )
    count = sum(1 for t, s in seq[:-1] if s == "unavailable")
    return count, secs / 3600, 100 * secs / window if window else 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=7, help="lookback window (default: 7)")
    ap.add_argument("--entity", default=DEFAULT_ENTITY, help=f"door sensor (default: {DEFAULT_ENTITY})")
    args = ap.parse_args()

    base, token = load_env()
    seq = fetch_history(base, token, args.entity, args.days)

    # Sentinel so the final episode has a duration. Not a real state.
    seq.append((datetime.now().astimezone(), "NOW"))

    window_s = (seq[-1][0] - seq[0][0]).total_seconds()
    print(f"{args.entity} -- {seq[0][0]:%Y-%m-%d %H:%M} to now ({window_s / 3600:.1f}h, {len(seq) - 1} states)\n")

    dropouts: list[tuple[datetime, float, str]] = []
    opens: list[tuple[datetime, float, str]] = []
    for i in range(len(seq) - 1):
        (t, state), (t_next, next_state) = seq[i], seq[i + 1]
        held = (t_next - t).total_seconds()
        prev = seq[i - 1][1] if i > 0 else "?"
        if state == "unavailable":
            dropouts.append((t, held, next_state))
        elif state == "on":
            opens.append((t, held, prev))

    dropout_s = sum(d for _, d, _ in dropouts)
    print("DROPOUTS (device off the Zigbee mesh)")
    print(f"  {len(dropouts)} episodes, {dropout_s / 3600:.1f}h total "
          f"({100 * dropout_s / window_s:.1f}% of window, "
          f"{len(dropouts) / (window_s / 86400):.1f}/day)")
    recovered_open = [d for d in dropouts if d[2] == "on"]
    if recovered_open:
        print(f"  {len(recovered_open)} recovered as OPEN <-- each of these is a candidate false alert:")
        for t, held, _ in recovered_open:
            print(f"    {t:%m-%d %H:%M:%S}  was away {held / 60:.1f} min, came back 'on'")
    else:
        print("  all recoveries returned 'off' -- dropouts alone are not producing the alerts")

    print(f"\nOPEN episodes ({len(opens)}) -- alert fires past {ALERT_THRESHOLD_MIN:.0f} min")
    if not opens:
        print("  none")
    for t, held, prev in opens:
        mins = held / 60
        flag = "ALERTED" if mins > ALERT_THRESHOLD_MIN else "       "
        origin = "AFTER DROPOUT" if prev == "unavailable" else f"from {prev}"
        print(f"  {t:%m-%d %H:%M:%S}  {flag}  open {mins:8.1f} min  ({origin})")

    # Locate the fault: door sensor vs. a peer Zigbee device vs. a non-Zigbee control.
    print("\nFAULT LOCALIZATION (is it this sensor, the Zigbee gateway, or HA?)")
    door_stats = unavailability(seq[:-1])
    print(f"  {args.entity:45s} {door_stats[0]:4d} eps  {door_stats[1]:6.1f}h  {door_stats[2]:5.1f}%")
    for label, ent in (("peer Zigbee device", PEER_ZIGBEE), ("non-Zigbee control", CONTROL_ENTITY)):
        try:
            stats = unavailability(fetch_history(base, token, ent, args.days))
        except SystemExit:
            print(f"  {ent:45s} (no history -- skipped)")
            continue
        print(f"  {ent:45s} {stats[0]:4d} eps  {stats[1]:6.1f}h  {stats[2]:5.1f}%   <- {label}")
    print("  Peer matches door + control stays up  => Zigbee gateway fault, not the door sensor.")
    print("  NOTE: history before 2026-09-11 is from the ConBee II/deCONZ coordinator")
    print("        under old entity ids, so windows spanning that date will look empty.")

    alerting = [o for o in opens if o[1] / 60 > ALERT_THRESHOLD_MIN]
    after_dropout = [o for o in alerting if o[2] == "unavailable"]
    print(f"\nSUMMARY: {len(alerting)} alert-length OPEN episodes, "
          f"{len(after_dropout)} of them began at a dropout recovery.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
