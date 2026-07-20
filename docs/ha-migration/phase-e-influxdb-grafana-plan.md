# Phase E -- Tublemetry Time-Series Logging (InfluxDB + Grafana)

Implementation plan for persistent, long-term time-series logging of the hot-tub
metrics, running as HAOS add-ons on the Beelink MINIS12 Pro (Intel N100, 16GB,
NVMe). This logging layer lives **outside** HA's recorder/dashboard layer and is
the foundational requirement for tublemetry Tiers 1-3.

- Host: Beelink MINIS12 Pro, HAOS 18.x, HA Core ~2026.7.x.
- Data store: InfluxDB add-on on the Beelink.
- Visualization: Grafana add-on on the Beelink.
- Backup: the HA recorder DB is excluded from HA backups (Phase B), so InfluxDB
  durability is handled separately here.

---

## Verified facts (research, July 2026)

- **Two community InfluxDB add-ons exist.** InfluxDB 1.x (Frenck / hassio-addons,
  ships Chronograf + Kapacitor) and InfluxDB 2.x (Dattel / homeassistant-influxdb2,
  ships InfluxDB's own built-in UI). Both are community, not core. The HA
  `influxdb:` integration supports 1.x (InfluxQL), 2.x (Flux), and 3.x (InfluxQL +
  external SQL tools).
- **Recommendation: InfluxDB 2.x.** It gives bucket-level retention, a built-in UI
  (Data Explorer + Tasks), token auth, Flux (needed for Grafana's InfluxDB
  datasource and for downsampling tasks), and a clean OSS `influx backup` CLI.
  InfluxDB 3.x is explicitly NOT chosen: it dropped Flux and the built-in task
  engine, which breaks the downsampling-via-tasks and Grafana-Flux approach below.
- **YAML config for the `influxdb:` integration is deprecated.** On 2026.7.x the
  YAML block still works and is auto-imported into a config entry. YAML support
  ends in the **2026.9** release; a UI config flow was merged (core PR #170448).
  Action: apply the YAML now (it imports cleanly); after upgrading past 2026.9,
  manage the imported config entry via the UI. Nothing here needs to change on
  2026.7.
- **Measurement/field mapping.** The integration's `measurement_attr` defaults to
  `unit_of_measurement` (so temps land in a measurement literally named `°F`).
  Setting `measurement_attr: entity_id` instead makes each entity_id its own
  measurement -- much simpler Flux. Numeric states write to field `value`; binary
  sensors (`on`/`off`) and `automation`/`input_boolean` states convert to
  `value` = 1.0 / 0.0, which is exactly what duty-cycle `mean()` needs.
- **Backups:** InfluxDB 2.x uses `influx backup <dir>` / `influx restore`. Restore
  cannot overwrite an existing bucket -- use `--new-bucket` or delete first
  (important for restore-testing on the Pi 4).

Sources: HA InfluxDB integration docs; core issue #165712 (YAML deprecation ->
2026.9); InfluxData downsampling + backup/restore docs; community add-on threads.

---

## 1. InfluxDB version, buckets, and retention

### Add-on
Install the **InfluxDB 2.x** add-on. On first launch, open its UI and onboard:
set an organization (e.g. `tublemetry`), an initial bucket, and an operator
token. **Capture the operator token offline** (password manager + one offline
copy) -- same discipline as the HA emergency kit; it is required for full restores.

### Bucket design (tuned for slow-moving tub metrics)
Tub metrics are low-volume: water temp is filtered to `heartbeat: 30s` + `delta:
1.0` (esphome/tublemetry.yaml), heater/pump/setpoint are event-driven, and the
rate sensors refresh hourly/daily. A full year of raw data is tens of MB, so we
can afford long raw retention and still keep an infinite downsampled tier for
seasonal/multi-year analysis.

| Bucket | Resolution | Retention | Purpose |
|---|---|---|---|
| `tublemetry` | raw (as written by HA) | **400 days** | High-res recent data. Covers a full seasonal cycle for Tier 1 rate calcs and Grafana detail. |
| `tublemetry_longterm` | hourly aggregates | **infinite (0)** | Multi-year trend, seasonal comparison, capacity planning. Negligible size. |

Optional third tier (`tublemetry_daily`, daily means, infinite) can be added
later; not needed at this volume.

### Downsampling task (paste into InfluxDB UI -> Tasks -> Create Task)
```flux
option task = {name: "tublemetry_downsample_hourly", every: 1h, offset: 2m}

from(bucket: "tublemetry")
  |> range(start: -2h)                       // small overlap buffer
  |> filter(fn: (r) => r._field == "value")
  |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
  |> to(bucket: "tublemetry_longterm")
```
`mean` over the binary heater/pump series yields the hourly duty fraction (0-1);
over temps it yields the hourly average. Note the well-documented InfluxDB
downsample timeshift gotcha (UTC vs local, nested-window +1h drift) -- only
relevant if we later add cumulative kWh; not an issue for the gauge signals here.

---

## 2. HA -> InfluxDB integration config

Entity IDs below were confirmed by reading the repo (esphome/tublemetry.yaml,
esphome/components/tublemetry_display/*, and ha/*.yaml). ESPHome device
`friendly_name: Tublemetry` produces the `*.tublemetry_hot_tub_*` prefix.

### Curated include list (the exact entities to stream)

| entity_id | Source | Type / unit | Why stream it |
|---|---|---|---|
| `sensor.tublemetry_hot_tub_temperature` | esphome | °F | Water temp -- the anchor signal for every tier. |
| `number.tublemetry_hot_tub_setpoint` | esphome | °F | Commanded setpoint (HA -> tub). |
| `sensor.tublemetry_hot_tub_detected_setpoint` | esphome | °F | Panel-decoded setpoint (drift / sync tracking). |
| `sensor.hot_tub_expected_setpoint` | ha/templates.yaml | °F | TOU single-source-of-truth setpoint. |
| `sensor.outdoor_temperature` | ha/templates.yaml (from `weather.forecast_home`) | °F | Outside-air temp for heat-loss vs ambient ΔT. |
| `binary_sensor.tublemetry_hot_tub_heater` | esphome | on/off -> 1/0 | Heater duty cycle; defines heating windows. |
| `binary_sensor.tublemetry_hot_tub_pump` | esphome | on/off -> 1/0 | Pump state (context for temp readings). |
| `binary_sensor.hot_tub_heater_power` | ha/heater_power.yaml | on/off -> 1/0 | Enphase-derived heater power (currently a stub returning false; include now for when it is wired to the Envoy). |
| `sensor.hot_tub_heating_rate` | ha/thermal_model.yaml | °F/min | Derived heating rate (Tier 1). |
| `sensor.hot_tub_cooling_rate` | ha/thermal_model.yaml | °F/hr | Derived cooling/heat-loss rate (Tier 1). |
| `sensor.hot_tub_heat_loss_rate` | ha/thermal_model.yaml | °F/hr | Informational heat-loss rate. |
| `sensor.hot_tub_preheat_minutes` | ha/thermal_model.yaml | min | Current time-to-target estimate. |
| `input_number.hot_tub_max_setpoint` | ha/helpers.yaml | °F | TOU max (seasonal) config. |
| `input_number.hot_tub_coast_setpoint` | ha/helpers.yaml | °F | TOU coast (floor) config. |
| `input_boolean.thermal_runaway_active` | ha/helpers.yaml | on/off -> 1/0 | Safety-flag context for anomalies. |
| `automation.hot_tub_tou_schedule` | ha/tou_automation.yaml | on/off -> 1/0 | Whether the TOU schedule is enabled. |
| `binary_sensor.tublemetry_hot_tub_api_status` | esphome | on/off -> 1/0 | ESP32 online/offline -- correlate gaps/drift with the known ESP32<->HA sync flakiness. |

**Deliberately excluded** (keep it minimal): all string/text sensors have no
numeric value -- `sensor.hot_tub_preheat_eta` (string), and the diagnostic
text_sensors (`display_state`, `raw_hex`, `injection_phase`,
`last_command_result`, `display_string`, IP/SSID/MAC, firmware version). Also
excluded: `sensor.hot_tub_*_rate_snapshot` input_numbers (redundant with the live
rate sensors) and the WiFi-signal/uptime/retry-count diagnostics (add later only
if debugging).

### Config file: `ha/influxdb.yaml` (new package)

The repo uses HA packages (see the 78bd0fd restructure). `influxdb:` is a valid
top-level key in a package file.

```yaml
# ha/influxdb.yaml -- HA -> InfluxDB 2.x streaming (Phase E)
# NOTE: on HA <= 2026.8 this YAML is auto-imported to a config entry; from 2026.9
# manage it in the UI (Settings -> Devices & Services -> InfluxDB).
influxdb:
  api_version: 2
  host: <influxdb-addon-host>     # add-on internal hostname (e.g. a0d7b954-influxdb)
                                  #   or the Beelink LAN IP; confirm on the add-on page
  port: 8086
  ssl: false
  verify_ssl: false
  token: !secret influxdb_ha_write_token
  organization: !secret influxdb_org_id
  bucket: tublemetry
  measurement_attr: entity_id     # each entity_id becomes its own measurement
  max_retries: 3
  tags:
    source: tublemetry
  tags_attributes:
    - friendly_name
  include:
    entities:
      - sensor.tublemetry_hot_tub_temperature
      - number.tublemetry_hot_tub_setpoint
      - sensor.tublemetry_hot_tub_detected_setpoint
      - sensor.hot_tub_expected_setpoint
      - sensor.outdoor_temperature
      - binary_sensor.tublemetry_hot_tub_heater
      - binary_sensor.tublemetry_hot_tub_pump
      - binary_sensor.hot_tub_heater_power
      - sensor.hot_tub_heating_rate
      - sensor.hot_tub_cooling_rate
      - sensor.hot_tub_heat_loss_rate
      - sensor.hot_tub_preheat_minutes
      - input_number.hot_tub_max_setpoint
      - input_number.hot_tub_coast_setpoint
      - input_boolean.thermal_runaway_active
      - automation.hot_tub_tou_schedule
      - binary_sensor.tublemetry_hot_tub_api_status
```

Add to `secrets.yaml` (never commit real values):
```yaml
influxdb_ha_write_token: "<HA write token, scoped to the tublemetry bucket>"
influxdb_org_id: "<InfluxDB org id>"
```

Because `include:` is set, **only** these entities are written -- HA does not dump
every entity. Create the HA token in InfluxDB as a **write-only** token scoped to
the `tublemetry` bucket (least privilege). Restart HA after adding the file, then
confirm points arriving in InfluxDB Data Explorer.

---

## 3. Grafana add-on + starter dashboard

### Setup
1. Install the **Grafana** community add-on, start it, open it (ingress sidebar).
2. Administration -> Data sources -> Add -> **InfluxDB**. Query language:
   **Flux**. URL: `http://<influxdb-addon-host>:8086`. Organization: `tublemetry`.
   Token: a **read-only** token scoped to both buckets (separate from HA's write
   token). Default bucket: `tublemetry`. Save & Test.
3. Import the starter dashboard JSON (hand-off artifact) and point its variable at
   the datasource.

### Panels

1. **Water temp vs setpoints (hero, time series, °F).** Series: water temp,
   commanded setpoint, expected setpoint, panel detected-setpoint; outdoor temp on
   a second Y-axis.
   ```flux
   from(bucket: "tublemetry")
     |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
     |> filter(fn: (r) => r._measurement =~ /hot_tub_temperature|hot_tub_setpoint|expected_setpoint|detected_setpoint|outdoor_temperature/)
     |> filter(fn: (r) => r._field == "value")
     |> aggregateWindow(every: v.windowPeriod, fn: mean, createEmpty: false)
   ```
2. **Heater duty cycle.** (a) State-timeline of `binary_sensor.tublemetry_hot_tub_heater`
   raw on/off; (b) hourly duty % = `mean(value) * 100` over 1h windows. Overlay
   `binary_sensor.hot_tub_heater_power` once the Envoy is wired for an independent
   check.
3. **Heat-loss / heating rate.** `sensor.hot_tub_heating_rate` (convert °F/min ->
   °F/hr for a common axis) and `sensor.hot_tub_cooling_rate` / heat_loss_rate.
   Optionally add an instantaneous rate = `derivative()` of water temp.
4. **TOU schedule overlay.** Step line of `sensor.hot_tub_expected_setpoint` with
   shaded peak-rate regions, plus heater-on shading to show heating concentrated
   off-peak. Peak windows come from the tub schedule in ha/templates.yaml
   (weekday coast block ~10:00-17:30 = on-peak; overnight coast). Confirm exact
   MGE Rg-2A clock hours against the bill (open decision).
5. **Heating during peak vs off-peak.** Bar/stat: daily heater on-hours split into
   peak vs off-peak, and an energy proxy = on-hours x 4 kW nameplate (heater_power.yaml
   cites ~4 kW). Flux buckets by `hourOfDay`/`weekday`:
   ```flux
   from(bucket: "tublemetry")
     |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
     |> filter(fn: (r) => r._measurement == "binary_sensor.tublemetry_hot_tub_heater" and r._field == "value")
     |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)   // on-fraction per hour
     |> map(fn: (r) => ({r with kwh: r._value * 4.0}))             // hour x 4kW
     // then group by peak/off-peak via a conditional on date.hour(t: r._time)
   ```
6. **Connectivity / safety row (bonus).** `binary_sensor.tublemetry_hot_tub_api_status`
   and `input_boolean.thermal_runaway_active` as a state timeline to correlate data
   gaps and anomalies with ESP32 dropouts and runaway events.

---

## 4. How this unblocks Tier 1 (time-to-target)

**The core unblock:** the current rate sensors (ha/thermal_model.yaml) run SQL
directly against the recorder DB (`/config/home-assistant_v2.db`) over a 30-day
window. The recorder is volatile, purges old rows, and is **excluded from backups**
(Phase B). So today's rate estimates are fragile and non-durable. Streaming to
InfluxDB gives a durable, multi-season history the rate math can rely on.

> Finding / action: HA recorder `purge_keep_days` defaults to 10, but the SQL
> sensors query a 30-day window. Either raise `purge_keep_days` to >= 30 to keep
> the current sensors honest, or (preferred, long-term) reimplement the rate calcs
> as Flux against InfluxDB so they survive recorder loss. Verify current
> `purge_keep_days` on the restored config.

**Derived rates needed:**
- **Heating rate (°F/hr, heater ON):** over windows where
  `binary_sensor.tublemetry_hot_tub_heater == on`, compute d(water temp)/dt. In
  Flux, `derivative()` of the temp series masked to heater-on. Refine as a function
  of ΔT-to-ambient (water - outdoor) and setpoint gap for a better model than the
  current single scalar.
- **Cooling / heat-loss rate (°F/hr, heater OFF):** derivative over heater-off
  windows, ideally conditioned on (water - outdoor) ΔT so summer vs winter coasting
  is modeled correctly.

**Time-to-target:**
- Heat up: `minutes = (target - current) / heating_rate_per_min` (this is exactly
  what `sensor.hot_tub_preheat_minutes` already computes; InfluxDB makes the rate
  input stable and ambient-aware).
- Coast down to eco: `hours = (current - target) / cooling_rate_per_hr`.
- Confidence: use the variance of per-event rates in InfluxDB to attach an error
  band to the estimate (a Big-Button "ready in ~45 min +/- 10").

This is the data foundation for Tier 2 (schedule heating onto cheap power using
known heat-up time) and Tier 3 (opportunistic solar heating using known thermal
storage / loss rates).

---

## 5. InfluxDB durability / backup

The recorder is excluded from HA backups, so InfluxDB is the system of record for
long-term tub data and needs its own, restore-tested backup. Do **not** rely on
the InfluxDB add-on's data folder riding along inside the daily HA Supervisor
backup -- that defeats Phase B's "keep backups small / fit Drive's 15GB" goal.

**Plan:**
1. **Nightly logical dump.** From the Advanced SSH & Web Terminal add-on
   (installed in Phase C), cron a nightly:
   ```bash
   influx backup /share/influx-backups/tublemetry_$(date +%F) \
     --host http://<beelink-ip>:8086 \
     --token "$INFLUX_OPERATOR_TOKEN"
   # retain last ~14, delete older
   ```
   Dumps are small (slow sensors), so 14 days is trivial.
2. **Land it on the 3-2-1 path (Phase B).** Point `/share/influx-backups` at (or
   rsync it to) the DS218+ SMB share (copy 2). The dump is small enough to also
   push to Google Drive (offsite copy 3).
3. **Exclude the InfluxDB add-on folder from the daily HA Supervisor backup** --
   same rationale as excluding the recorder. The nightly `influx backup` covers it.
4. **Restore-test on the Pi 4 dev bench** (Phase B already calls for DR rehearsal):
   `influx restore <dir> --new-bucket tublemetry_restore` (restore cannot
   overwrite an existing bucket) and verify row counts. Keep the operator token
   with the emergency kit -- full restores need it.

This slots under Phase B's strategy: HA Supervisor backup (config + `.storage`,
recorder and InfluxDB both excluded) on one track; the small nightly InfluxDB dump
on a parallel track, both landing on NAS + Drive.

---

## 6. Dependency order + who does what

| # | Step | Owner | Blocks |
|---|---|---|---|
| 1 | Install + onboard InfluxDB 2.x add-on; create org; create `tublemetry` (400d) and `tublemetry_longterm` (infinite) buckets; create HA **write** token (bucket-scoped) + Grafana **read** token; capture operator token offline | User (HA UI) | everything |
| 2 | Add `ha/influxdb.yaml` package + `secrets.yaml` token/org; restart HA; verify points in Data Explorer | Claude writes file / User restarts + verifies | 3,4 |
| 3 | Create the `tublemetry_downsample_hourly` Flux task | User (Influx UI, paste from this doc) | -- |
| 4 | Install Grafana add-on; add InfluxDB datasource (Flux, read token); import starter dashboard | User (HA/Grafana UI) + Claude dashboard JSON | -- |
| 5 | Nightly `influx backup` cron -> NAS-synced dir + Drive; exclude InfluxDB add-on from HA backup; restore-test on Pi 4 | Claude script/automation + User wires NAS path & runs test | needs Phase B NAS mounted |
| 6 | (Later) Reimplement/validate rate queries in Flux; build Tier 1 time-to-target with confidence bands; verify recorder `purge_keep_days` | Claude + User | Tiers 1-3 |

**Files/config Claude can hand off now:** `ha/influxdb.yaml`, the `secrets.yaml`
additions, the downsampling Flux task text, the Grafana dashboard JSON, and the
nightly backup script/automation.

**Steps that require the user in the HA / add-on UI:** installing the two add-ons,
onboarding InfluxDB (org/buckets/tokens), pasting the Flux task, wiring the Grafana
datasource, importing the dashboard, restarting HA, and running the restore test.

---

## Open decisions for the user

1. **InfluxDB add-on choice:** confirm the specific 2.x community add-on (Dattel /
   homeassistant-influxdb2 is the maintained 2.x option). If you would rather stay
   on Frenck's officially-community 1.x add-on, the plan still works but swaps Flux
   -> InfluxQL, buckets -> databases+retention policies, and `influx backup` ->
   `influxd backup -portable`. Recommendation stands: **2.x**.
2. **Raw retention length:** 400 days proposed. Given the tiny data volume, raw
   could even be kept indefinitely -- your call on the cap.
3. **Exact MGE Rg-2A peak hours:** the plan infers on-peak from the tub schedule
   (weekday ~10:00-17:30). Confirm the true peak window(s) from your bill so the
   TOU-overlay and peak/off-peak energy panels are exact.
4. **Recorder `purge_keep_days`:** confirm it is >= 30 (or accept migrating the
   rate math to Flux) so the existing thermal-model sensors stay valid during the
   transition.
5. **True heater energy:** today the only heater-power signal is the Enphase stub
   (returns false until wired). To get real peak vs off-peak $ instead of the
   on-hours x 4 kW proxy, add the actual Envoy power/energy entity to the include
   list once configured.
