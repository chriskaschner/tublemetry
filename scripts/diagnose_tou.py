#!/usr/bin/env python3
"""
Diagnose the hot tub TOU automation against a live Home Assistant instance.

Answers two questions directly:
  1. Is the TOU automation actually working (enabled, firing on schedule)?
  2. Is the tub setpoint actually changing (commanded == what the panel shows,
     and stepping through the schedule over the last several days)?

It also inventories every automation (flagging non-canonical / lingering ones and
whether each is GUI-deletable or YAML-defined), reports the running ESP32 firmware
build vs the repo, lists notify.* services (to wire push alerts), and flags any
duplicate ..._2 entities.

The diagnosis logic is the pure function `diagnose(states)` so it can be unit
tested; the HA REST calls are a thin wrapper around it.

Usage:
    export HA_URL=http://homeassistant.local:8123
    export HA_TOKEN=<long-lived access token>   # or put both in a .env file
    uv run scripts/diagnose_tou.py
    uv run scripts/diagnose_tou.py --history-days 7

Actions (each is an explicit, guarded write -- nothing is changed without a flag):
    uv run scripts/diagnose_tou.py --enable-schedule   # automation.turn_on
    uv run scripts/diagnose_tou.py --clear-flag        # input_boolean.turn_off

Create the token in HA: Profile > Security > Long-lived access tokens > Create.
Store HA_URL / HA_TOKEN in a .env file (already gitignored) -- do not commit it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

# --------------------------------------------------------------------------- #
# Entity ids. ESPHome text_sensor components map to HA's `sensor.` domain, so
# injection_phase / last_command_result live under sensor.*, not text_sensor.*
# (the text_sensor.* ids referenced elsewhere in ha/ read as unknown -- noted).
# --------------------------------------------------------------------------- #
SCHEDULE = "automation.hot_tub_tou_schedule"
FLAG = "input_boolean.thermal_runaway_active"
API_STATUS = "binary_sensor.tublemetry_hot_tub_api_status"
COMMANDED = "number.tublemetry_hot_tub_setpoint"
DETECTED = "sensor.tublemetry_hot_tub_detected_setpoint"
RETRY = "sensor.tublemetry_hot_tub_retry_count"
INJECTION_PHASE = (
    "sensor.tublemetry_hot_tub_injection_phase",
    "text_sensor.tublemetry_hot_tub_injection_phase",
)
LAST_RESULT = (
    "sensor.tublemetry_hot_tub_last_command_result",
    "text_sensor.tublemetry_hot_tub_last_command_result",
)
COMPONENT_VERSION = "sensor.tublemetry_hot_tub_component_version"
FIRMWARE_VERSION = "sensor.tublemetry_hot_tub_firmware_version"
UPTIME = "sensor.tublemetry_hot_tub_uptime"

# Automations that SHOULD exist (aliases). Anything else is a removal candidate.
CANONICAL_CORE = {
    "Hot Tub TOU Schedule",
    "Hot Tub Thermal Runaway Protection",
    "Hot Tub Thermal Runaway Clear",
    "Hot Tub ESP32 Offline Detection",
    "Hot Tub Setpoint Drift Detection",
    "Hot Tub Refresh Thermal Model",
}
# Added by this project; absence before deploy is expected (reported INFO, not WARN).
NEW_AUTOMATIONS = {"Hot Tub TOU Watchdog", "Backup Dead-Man Alert", "AC Compressor Not Cooling"}

# Schedule boundaries (local time) the setpoint should step at.
TOU_TRANSITIONS = ["04:30", "05:00", "10:00", "17:30", "19:00", "22:00"]

REPO_ROOT = Path(__file__).resolve().parent.parent
# Where the running firmware build's version literal lives in the repo.
VERSION_HEADER = REPO_ROOT / "esphome/components/tublemetry_display/tublemetry_display.h"

PASS, FAIL, WARN, INFO = "PASS", "FAIL", "WARN", "INFO"
_UNAVAIL = {"unknown", "unavailable", "", None}


# --------------------------------------------------------------------------- #
# Report model
# --------------------------------------------------------------------------- #
@dataclass
class Finding:
    key: str
    status: str  # PASS / FAIL / WARN / INFO
    title: str
    detail: str = ""


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    def add(self, key: str, status: str, title: str, detail: str = "") -> None:
        self.findings.append(Finding(key, status, title, detail))

    def get(self, key: str) -> Finding | None:
        for f in self.findings:
            if f.key == key:
                return f
        return None

    @property
    def overall(self) -> str:
        statuses = {f.status for f in self.findings}
        if FAIL in statuses:
            return FAIL
        if WARN in statuses:
            return WARN
        return PASS


# --------------------------------------------------------------------------- #
# Helpers (pure)
# --------------------------------------------------------------------------- #
def _pick(states: dict, *ids: str) -> dict | None:
    """Return the first present state object among the given entity ids."""
    for i in ids:
        if i in states:
            return states[i]
    return None


def _num(state_obj: dict | None) -> float | None:
    """Parse a numeric state, or None if missing/unavailable/non-numeric."""
    if not state_obj:
        return None
    val = state_obj.get("state")
    if val in _UNAVAIL:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _age(iso: str | None, now: datetime) -> str:
    """Human ' (N days ago)' suffix for an ISO timestamp, or '' if unknown."""
    if not iso:
        return ""
    try:
        ts = datetime.fromisoformat(iso)
    except ValueError:
        return ""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    delta = now - ts
    secs = delta.total_seconds()
    if secs < 3600:
        return f" ({int(secs // 60)} min ago)"
    if secs < 86400:
        return f" ({secs / 3600:.1f} h ago)"
    return f" ({secs / 86400:.1f} days ago)"


def repo_component_version() -> str | None:
    """Read TUBLEMETRY_VERSION from the component header at repo HEAD."""
    try:
        text = VERSION_HEADER.read_text()
    except OSError:
        return None
    m = re.search(r'TUBLEMETRY_VERSION\s*=\s*"([^"]+)"', text)
    return m.group(1) if m else None


# --------------------------------------------------------------------------- #
# Core diagnosis -- pure function over a {entity_id: state_obj} mapping.
# --------------------------------------------------------------------------- #
def diagnose(
    states: dict,
    *,
    now: datetime | None = None,
    repo_version: str | None = None,
) -> Report:
    now = now or datetime.now(timezone.utc)
    r = Report()

    # 1. Is the schedule enabled?
    sched = states.get(SCHEDULE)
    if sched is None:
        r.add("schedule", FAIL, f"{SCHEDULE} not found",
              "The TOU automation entity is missing from HA.")
    else:
        lt = sched.get("attributes", {}).get("last_triggered")
        info = f"last_triggered: {lt or 'never'}{_age(lt, now)}"
        if sched.get("state") == "on":
            r.add("schedule", PASS, "TOU schedule is enabled", info)
        else:
            r.add("schedule", FAIL, "TOU schedule is DISABLED",
                  f"state={sched.get('state')}; {info}. "
                  "Re-enable with `--enable-schedule`.")

    # 2. Is the thermal-runaway flag stuck on? (it gates the whole schedule)
    flag = states.get(FLAG)
    if flag is None:
        r.add("runaway_flag", WARN, f"{FLAG} not found", "")
    elif flag.get("state") == "on":
        r.add("runaway_flag", FAIL, "Thermal runaway flag is ON",
              "This blocks the TOU schedule. Once the tub is safe, clear it with "
              "`--clear-flag`.")
    else:
        r.add("runaway_flag", PASS, "Thermal runaway flag is off", "")

    # 3. Is the ESP32 online? (offline => stale data, setpoint won't reach panel)
    api = states.get(API_STATUS)
    if api is None:
        r.add("esp32", WARN, f"{API_STATUS} not found", "")
    elif api.get("state") == "on":
        r.add("esp32", PASS, "ESP32 is online", "")
    else:
        r.add("esp32", FAIL, "ESP32 is OFFLINE",
              f"state={api.get('state')}. Setpoint changes cannot reach the panel.")

    # 4. Does the commanded setpoint match what the panel actually shows?
    cmd = _num(states.get(COMMANDED))
    det = _num(_pick(states, DETECTED))
    if cmd is None:
        r.add("setpoint", WARN, "Commanded setpoint unavailable", COMMANDED)
    elif det is None:
        r.add("setpoint", INFO, f"Commanded setpoint {cmd:g}F (panel readout unavailable)", "")
    elif abs(cmd - det) <= 0.5:
        r.add("setpoint", PASS, f"Setpoint agrees: commanded {cmd:g}F == panel {det:g}F", "")
    else:
        r.add("setpoint", FAIL,
              f"Setpoint MISMATCH: commanded {cmd:g}F != panel {det:g}F",
              "HA changed the setpoint but the panel did not follow -- button "
              "injection is likely failing at the hardware.")

    # 5. Injection health (hardware-side signal that changes aren't landing).
    phase = (_pick(states, *INJECTION_PHASE) or {}).get("state")
    result = (_pick(states, *LAST_RESULT) or {}).get("state")
    retry = _num(states.get(RETRY))
    if phase not in _UNAVAIL or result not in _UNAVAIL:
        detail = f"phase={phase or 'n/a'}, last_result={result or 'n/a'}, retries={retry if retry is not None else 'n/a'}"
        status = WARN if (retry and retry > 0) else INFO
        r.add("injection", status, "Injection status", detail)

    # 6. Duplicate ..._2 entities (a package/entity defined twice).
    dups = sorted(e for e in states if e.endswith("_2"))
    if dups:
        r.add("duplicates", WARN, f"{len(dups)} duplicate '..._2' entities",
              ", ".join(dups) + " -- an entity is defined by two packages.")
    else:
        r.add("duplicates", PASS, "No '..._2' duplicate entities", "")

    # 7. Firmware build vs repo.
    running = (states.get(COMPONENT_VERSION) or {}).get("state")
    uptime = _num(states.get(UPTIME))
    up = f", uptime {uptime / 86400:.1f} days" if uptime else ""
    if running in _UNAVAIL:
        r.add("firmware", INFO, "Firmware build unknown",
              f"{COMPONENT_VERSION} unavailable{up}")
    elif repo_version and running != repo_version:
        r.add("firmware", WARN,
              f"Firmware DRIFT: running {running}, repo {repo_version}",
              f"Re-flash esphome/tublemetry.yaml via OTA{up}.")
    else:
        r.add("firmware", PASS,
              f"Firmware build {running}"
              + (f" (matches repo)" if repo_version else ""), up.lstrip(", "))

    # 8. Automation inventory: canonical vs lingering, and anything missing.
    autos = {
        e: s.get("attributes", {}).get("friendly_name", e)
        for e, s in states.items()
        if e.startswith("automation.")
    }
    known = CANONICAL_CORE | NEW_AUTOMATIONS
    lingering = {e: n for e, n in autos.items() if n not in known}
    if lingering:
        lines = "; ".join(f"{n} ({e})" for e, n in sorted(lingering.items(), key=lambda kv: kv[1]))
        r.add("inventory", WARN,
              f"{len(lingering)} non-canonical automation(s) -- removal candidates",
              lines)
    else:
        r.add("inventory", PASS, "Only canonical automations present", "")

    present = set(autos.values())
    missing_core = sorted(CANONICAL_CORE - present)
    if missing_core:
        r.add("missing", WARN, f"{len(missing_core)} canonical automation(s) missing",
              ", ".join(missing_core))
    missing_new = sorted(NEW_AUTOMATIONS - present)
    if missing_new:
        r.add("pending", INFO, "Not yet deployed (expected pre-deploy)",
              ", ".join(missing_new))

    return r


# --------------------------------------------------------------------------- #
# Thin HA REST client (I/O)
# --------------------------------------------------------------------------- #
class HA:
    def __init__(self, base_url: str, token: str):
        self.base = base_url.rstrip("/")
        self.token = token

    def _req(self, path: str, method: str = "GET", body: dict | None = None):
        url = f"{self.base}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else None

    def states(self) -> dict:
        return {s["entity_id"]: s for s in self._req("/api/states")}

    def services(self) -> list:
        return self._req("/api/services")

    def history(self, entity_id: str, days: int) -> list:
        # entity ids are URL-safe (letters, digits, '.', '_'); no quoting needed.
        start = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        path = f"/api/history/period/{start}?filter_entity_id={entity_id}&minimal_response"
        data = self._req(path)
        return data[0] if data else []

    def automation_source(self, config_id: str) -> str:
        """'gui' if editable via the config API (in .storage), else 'yaml'."""
        try:
            self._req(f"/api/config/automation/config/{config_id}")
            return "gui"
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return "yaml"
            raise

    def call_service(self, domain: str, service: str, entity_id: str):
        return self._req(f"/api/services/{domain}/{service}", "POST",
                         {"entity_id": entity_id})


# --------------------------------------------------------------------------- #
# .env loading + CLI
# --------------------------------------------------------------------------- #
def load_dotenv() -> None:
    for candidate in (Path.cwd() / ".env", REPO_ROOT / ".env"):
        if not candidate.is_file():
            continue
        for line in candidate.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)


_STATUS_MARK = {PASS: "PASS", FAIL: "FAIL", WARN: "WARN", INFO: "info"}


def print_report(report: Report) -> None:
    print(f"\n{'=' * 68}\nHot Tub TOU diagnosis\n{'=' * 68}")
    for f in report.findings:
        print(f"[{_STATUS_MARK[f.status]:>4}] {f.title}")
        if f.detail:
            print(f"        {f.detail}")
    print(f"{'-' * 68}\nOVERALL: {report.overall}\n")


def print_history(client: HA, days: int) -> None:
    try:
        hist = client.history(COMMANDED, days)
    except Exception as e:  # noqa: BLE001 - report, don't crash the diagnosis
        print(f"(setpoint history unavailable: {e})")
        return
    print(f"Setpoint history (last {days} days) -- {len(hist)} recorded points:")
    if not hist:
        print("  none -- recorder empty or entity never recorded.")
        return
    changes = []
    last = None
    for pt in hist:
        val = pt.get("state")
        if val in _UNAVAIL or val == last:
            continue
        last = val
        when = pt.get("last_changed") or pt.get("last_updated")
        changes.append((when, val))
    for when, val in changes[-40:]:
        try:
            local = datetime.fromisoformat(when).astimezone().strftime("%a %m-%d %H:%M")
        except (ValueError, TypeError):
            local = str(when)
        print(f"  {local}  ->  {val}F")
    if len(changes) <= 1:
        print("  WARN: setpoint has not changed -- the schedule is not acting.")
    else:
        print(f"  ({len(changes)} distinct changes; expected steps near "
              f"{', '.join(TOU_TRANSITIONS)})")


def print_notify_services(client: HA) -> None:
    try:
        domains = client.services()
    except Exception as e:  # noqa: BLE001
        print(f"(notify services unavailable: {e})")
        return
    notify = []
    for d in domains:
        if d.get("domain") == "notify":
            notify = sorted(d.get("services", {}).keys())
    mobile = [f"notify.{s}" for s in notify if s.startswith("mobile_app")]
    print(f"notify.* services: {', '.join('notify.' + s for s in notify) or 'none'}")
    if mobile:
        print(f"  -> use for push alerts: {', '.join(mobile)}")
    else:
        print("  -> no notify.mobile_app_* found; install the HA mobile app to enable push.")


def classify_lingering(client: HA, states: dict, report: Report) -> None:
    finding = report.get("inventory")
    if not finding or finding.status != WARN:
        return
    print("Removal candidates (how to delete each):")
    for e, s in states.items():
        if not e.startswith("automation."):
            continue
        name = s.get("attributes", {}).get("friendly_name", e)
        if name in (CANONICAL_CORE | NEW_AUTOMATIONS):
            continue
        config_id = s.get("attributes", {}).get("id")
        where = "unknown"
        if config_id:
            try:
                where = client.automation_source(str(config_id))
            except Exception:  # noqa: BLE001
                where = "unknown"
        how = ("delete in app (Settings > Automations)" if where == "gui"
               else "delete file from tublemetry-ha/packages/" if where == "yaml"
               else "source unknown")
        print(f"  - {name} ({e}) [{where}] -> {how}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--history-days", type=int, default=7)
    ap.add_argument("--enable-schedule", action="store_true",
                    help="automation.turn_on the TOU schedule (guarded write)")
    ap.add_argument("--clear-flag", action="store_true",
                    help="input_boolean.turn_off thermal_runaway_active (guarded write)")
    args = ap.parse_args()

    load_dotenv()
    base, token = os.environ.get("HA_URL"), os.environ.get("HA_TOKEN")
    if not base or not token:
        print("ERROR: set HA_URL and HA_TOKEN (env or .env). See --help.", file=sys.stderr)
        return 2

    client = HA(base, token)
    try:
        states = client.states()
    except urllib.error.HTTPError as e:
        print(f"ERROR: HA returned {e.code} {e.reason} -- check HA_URL / token.", file=sys.stderr)
        return 2
    except urllib.error.URLError as e:
        print(f"ERROR: cannot reach {base} -- {e.reason}", file=sys.stderr)
        return 2

    report = diagnose(states, repo_version=repo_component_version())
    print_report(report)
    print_history(client, args.history_days)
    print()
    print_notify_services(client)
    print()
    classify_lingering(client, states, report)

    # Guarded writes.
    if args.enable_schedule:
        client.call_service("automation", "turn_on", SCHEDULE)
        print(f"\n-> enabled {SCHEDULE}")
    if args.clear_flag:
        client.call_service("input_boolean", "turn_off", FLAG)
        print(f"-> cleared {FLAG}")

    return 0 if report.overall != FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
