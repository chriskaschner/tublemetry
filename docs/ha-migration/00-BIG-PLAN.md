# Tublemetry / HA Migration -- Consolidated Big Plan

**Date:** 2026-07-19
**Purpose:** Single entry point tying together the three workstream docs produced this session. Read this first, then drill into the detailed docs as needed.

## Where we are
- Old Raspberry Pi HA host died (SD-card controller failure, unrecoverable). Migrated to a **Beelink MINIS12 Pro** running HAOS bare-metal on internal NVMe, HA Core ~2026.7.x.
- An April-15 partial backup was restored. The **tublemetry TOU pipeline is recovered and live**: Git Pull add-on re-syncing the public `tublemetry-ha` repo, schedule enabled, sliders Max=102 / Coast=90, ESP32 online.
- Everything below is the forward plan. Nothing here has been executed.

## Source documents
| Workstream | Doc |
|---|---|
| Backups (Phase B) | `phase-b-backups-runbook.md` + `deadman-backup-alert.yaml` |
| Injection undershoot bug | `injection-undershoot-investigation.md` |
| Logging (Phase E) | `phase-e-influxdb-grafana-plan.md` |
| Full migration context | `~/Downloads/ha-migration-handoff-2026-07-19.md` |

---

## Dependency-ordered sequence

### 1. Phase B -- Backups  (DO FIRST)
The governing rule from the migration: never rebuild on one drive again. 8 ordered steps in the runbook, each tagged `[UI-HA]` / `[UI-SYN]` / `[EXTERNAL]` / `[VAULT]` / `[FILE]` and ending in a Verify line:
1. Enable the backup-status sensor (disabled by default) so the dead-man alert has a signal.
2. Synology: least-privilege `ha_backups` user + share; handle HDD hibernation.
3. HA: add SMB network storage (Usage = Backup).
4. Configure automatic backups -- **set History toggle OFF during the initial flow** (this is how the recorder DB is excluded; it can grey out afterward), retention, before-update, emergency kit.
5. Store the **encryption key OUTSIDE HA** (password manager + one offline copy). #1 cause of failed restores.
6. Google Drive offsite via OAuth (full click-path in the runbook; set consent screen to "In production").
7. Enable all 3 locations (NVMe + NAS + Drive) = 3-2-1; verify first backup.
8. Deploy the dead-man alert; then DR test-restore on the Pi 4.

**Gating decisions before starting:** retention number (scheduler is global-only -- see decisions), NAS hibernation choice, backup time-of-day.

### 2. Recorder-purge bridge  (couples Phase B and Phase E)
Because Phase B excludes the recorder DB from backups, and the Tier-1 rate sensors (`ha/thermal_model.yaml`) query the recorder over a **30-day** window while the default purge is **~10 days**, today's heating/cooling rates are quietly fragile and non-durable. Options:
- Raise `recorder: purge_keep_days` to >=30 now (cheap; keeps Tier-1 working until InfluxDB), or
- Migrate the rate math to Flux once Phase E is up.

### 3. Injection undershoot fix  (can run in parallel with B; gated on a hardware test)
Investigation found **two** bugs:
- **Undershoot:** the fast path fires exactly `abs(target-current)` presses with no wake-press compensation (`button_injector.cpp:161-167`); Balboa GL/ML panels consume the first press as a display-wake, so a +1 command lands one short.
- **False success:** verification compares against `last_display_temp_`, which includes the idle water temperature (`tublemetry_display.cpp:366-369`), so it reports `success` while the real setpoint is off. It ignores the trustworthy `detected_setpoint_`.

Fix (patch in the doc): closed-loop verification gated on the confirmed detected setpoint + bounded re-press using the existing `press_budget` slack; new `FakeBalboaPanel` wake-press test model (7 cases, several fail today). **Applying this reflashes the physical spa and needs a hardware smoke test -- requires explicit go and someone at the tub.**

### 4. Phase E -- InfluxDB / Grafana  (after B; before HA 2026.9 if using YAML)
- **InfluxDB 2.x** (keeps Flux + tasks + clean `influx backup`; 3.x dropped them).
- Buckets: `tublemetry` (raw, 400d) + `tublemetry_longterm` (hourly aggregates), with a Flux downsampling task.
- `ha/influxdb.yaml` package streaming **17 verified entities** (not a firehose).
- Grafana add-on + Flux datasource + 6-panel starter dashboard.
- InfluxDB durability: nightly `influx backup` -> DS218+/Drive; exclude the InfluxDB add-on folder from the HA Supervisor backup; restore-test on the Pi 4.
- Unblocks Tier 1 time-to-target estimates.

---

## Cross-cutting notes
- **Deprecation clock:** the `influxdb:` YAML integration config is deprecated; support ends **HA 2026.9**. Works now on 2026.7 and auto-imports to a config entry -- do Phase E before then or use the UI flow later.
- **Dead-man alert placement:** belongs in the `tublemetry-ha` deploy repo under `packages/deadman_backup_alert.yaml`, NOT a UI automation -- a backup watchdog that lives only in `.storage` would be lost in the exact host rebuild it defends against.
- **Retention is global-only** in HA's built-in scheduler -- it cannot do "NAS 30 / Drive 5-10" as the handoff assumed.

---

## Consolidated decisions needed from the user
**Phase B**
1. NAS hibernation: disable HDD hibernation (recommended) vs. pin backup time to an awake window.
2. Retention count (global): start ~15 (safely under Drive's 15 GB free with History excluded); revisit after seeing real sizes.
3. Backup time-of-day (default 03:30, must align with the hibernation choice).
4. Which add-ons to include in backups (Z2M + deCONZ pairing DBs + SSH once they exist in Phase D).
5. DR rehearsal target: Pi 4 now vs. throwaway HAOS VM.

**Recorder bridge**
6. Raise `purge_keep_days` to >=30 now, yes/no.

**Phase E**
7. Confirm the 2.x add-on (Dattel's maintained 2.x) vs. staying on Frenck's 1.x.
8. Raw-bucket retention cap (400d proposed; could be infinite given tiny volume).
9. Exact MGE Rg-2A peak hours (plan infers ~weekday 10:00-17:30 -- confirm against the bill).
10. Add the real Envoy/Enphase power/energy entity once wired (replaces the on-hours x 4kW proxy).

**Injection fix**
11. Approve applying the patch + tests, then scheduling a reflash + hardware smoke test (physical actuation).

---

## Recommended order
Phase B (backups) -> recorder-purge bridge (decision 6) -> Phase E (InfluxDB/Grafana, before 2026.9) -> injection fix whenever you can be at the tub for the smoke test. Homebridge retirement / Zigbee migration (Phase D in the handoff) is a separate track and not covered by these three docs.
