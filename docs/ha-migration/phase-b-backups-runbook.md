# Phase B -- Backups Runbook (do-in-one-sitting)

Host: Beelink MINIS12 Pro, HAOS 18.x / HA Core ~2026.7.x, bare-metal on internal NVMe.
Goal: 3-2-1 backups = local NVMe copy + Synology DS218+ (SMB) + Google Drive offsite.
Constraint: the old Raspberry Pi died from single-drive (SD) failure. Never rely on one drive again -- this runbook exists so that a dead host is a same-day rebuild, not a data loss.

This runbook was verified against current Home Assistant documentation (backup system was overhauled across the 2025.x releases; the old Supervisor "Snapshots" UI no longer applies). Sources are listed at the bottom.

---

## How to read this runbook

Every step is tagged with WHO does it and WHERE:

- `[UI-HA]`      -- you, in the Home Assistant web UI (Settings ...).
- `[UI-SYN]`     -- you, in Synology DSM (the NAS admin web UI).
- `[EXTERNAL]`   -- you, in an external site (Google Cloud Console).
- `[VAULT]`      -- you, in your password manager / offline store. Do NOT skip these.
- `[FILE]`       -- a file already prepared for you in this repo; you deploy it, no typing.

Steps are in strict dependency order. Do them top to bottom. Where a step can fail silently, a "Verify" line tells you exactly what to confirm before moving on.

Time budget: ~60-90 min, most of it in the Google Cloud OAuth section (Step 4) and the DR rehearsal (Step 8).

---

## Dependency map (what blocks what)

```
Step 1 Synology user+share ─┐
                            ├─> Step 2 HA network storage (SMB) ─┐
Step 0 Pre-flight ──────────┘                                   │
                                                                ├─> Step 3 Automatic backup config
Step 4 Google Cloud OAuth ──> (HA add Google Drive integration) ┘        (schedule, History OFF,
                                                                          retention, before-update,
                                                                          EMERGENCY KIT)
                                                                          │
                                                                          ├─> Step 5 Enable all 3 locations
                                                                          ├─> Step 6 First backup + verify 3-2-1
                                                                          ├─> Step 7 Deploy dead-man alert [FILE]
                                                                          └─> Step 8 DR test-restore on Pi 4
```

You can do Step 4 (Google Cloud) in parallel with Steps 1-2 -- it is independent until you paste the credentials into HA. But the "add Google Drive integration in HA" sub-step belongs after Step 4 produces a Client ID + Secret.

---

## Step 0 -- Pre-flight `[UI-HA]`

0.1 Confirm HA Core version: Settings > About. Expect ~2026.7.x. If the backup UI below does not match, HA has moved again -- re-verify against the docs before proceeding.

0.2 Confirm the Home Assistant Companion app is installed on your phone and the notify service exists. Developer Tools > Actions, search `notify.mobile_app_chris_phone`. If it is not there, the dead-man alert (Step 7) has nothing to push to -- fix this first (open the Companion app once while logged in).

0.3 Confirm `event.backup_automatic_backup` and `sensor.backup_last_successful_automatic_backup` exist: Developer Tools > States, filter on `backup`. Some backup entities are DISABLED by default. If `sensor.backup_last_successful_automatic_backup` is missing, go to Settings > Devices & Services > Entities, search `backup`, and enable it. (It will read `unknown` until the first automatic backup runs -- that is expected.)

0.4 Note the HA instance URL you reach it at on the LAN (e.g. `http://homeassistant.local:8123`). You will need My Home Assistant configured for the Google Drive OAuth redirect (Step 4.10).

---

## Step 1 -- Synology: dedicated user + backups share `[UI-SYN]`

Do NOT use the admin account. Create a purpose-built, least-privilege user so a leaked HA credential cannot touch anything else on the NAS.

1.1 Log into DSM as an admin.

1.2 Create the share. Control Panel > Shared Folder > Create > Create shared folder.
   - Name: `ha_backups` (no spaces / special characters).
   - Location: the DS218+ main volume.
   - Description: "Home Assistant backups (HAOS on Beelink)".
   - Hide sub-folders/files from users without permission: yes.
   - (Optional, recommended) On the advanced screen, enable data checksum / integrity.
   - Do NOT enable encryption at the Synology share level -- HA already encrypts the backup archive (Step 3.7). Double encryption just complicates restore.

1.3 Create the dedicated user. Control Panel > User & Group > User > Create.
   - Name: `ha_user`.
   - Password: generate a strong unique password. Save it to your password manager now -- you paste it into HA in Step 2.
   - Uncheck "Allow this user to change account password" if you want it locked.
   - Groups: leave in `users` only (NOT `administrators`).
   - User application permissions: DENY everything EXCEPT File Station (File Station permission is required for a File Station shared folder to be usable as an SMB backup target). Deny DSM/Web/other apps so this account cannot log into the DSM UI.
   - Speed / quota: optional. If you set a quota on `ha_backups`, size it for ~30 backups (see retention math in Step 3.5).

1.4 Grant the user Read/Write on ONLY the backups share. On the shared-folder permissions step (or Control Panel > Shared Folder > ha_backups > Edit > Permissions): give `ha_user` = Read/Write on `ha_backups`, and No Access on every other share.
   Verify: `ha_user` shows Read/Write on `ha_backups` and nothing else.

1.5 Enable + pin SMB protocol. Control Panel > File Services > SMB > Enable SMB service.
   - Advanced Settings > set Minimum SMB protocol = SMB2 (or SMB2 and Large MTU) and Maximum = SMB3. HA connects over CIFS/SMB2.1+.
   - Do NOT enable "Local Master Browser" / WINS / transfer-log options that carry the warning "enabling this feature disables hard drive hibernation and activates the guest account without a password."

1.6 HDD hibernation decision (critical -- see gotcha #3). A NAS that is asleep at backup time makes the scheduled backup FAIL for that location. Two acceptable resolutions -- pick one and record it in "Open decisions":
   - (A, simplest, recommended) Disable HDD hibernation for the DS218+ while it is the backup target: Control Panel > Hardware & Power > HDD Hibernation > set "None" (or a long timeout well beyond your daily backup window). The DS218+ idles low; an always-awake backup target is the safe default.
   - (B, power-saving) Keep hibernation, but in Step 3.2 pick a Custom backup time that lands inside a window you know the NAS is already awake (e.g. right after a nightly Synology task), OR later convert to a `backup.create_automatic` automation that wakes the NAS first (out of scope for this runbook; noted as a future option).
   Note: an always-mounted SMB share plus HA's periodic access already tends to keep the drives spun up, so option A is usually what happens in practice anyway.

1.7 (Recommended, ransomware/oops protection) Enable Snapshot on `ha_backups` if the DS218+ supports Btrfs snapshots, so a compromised HA host cannot wipe your only NAS copy. Not required for 3-2-1 but cheap insurance.

Verify Step 1: from a laptop, browse `\\<NAS-IP>\ha_backups` and log in as `ha_user`. You should be able to write a test file and NOT see any other share. Delete the test file.

---

## Step 2 -- HA network storage over SMB `[UI-HA]`

2.1 Settings > System > Storage.

2.2 Under Network storage, click Add network storage.

2.3 Fill the form:
   - Name: `ds218-backups` (this becomes the mount name).
   - Usage / Purpose: Backup.  <-- must be Backup, not Media/Share, or it will not appear as a backup Location.
   - Server: the DS218+ LAN IP (use the IP, not `.local`, for reliability -- give the NAS a DHCP reservation if it does not already have a static IP).
   - Protocol: CIFS / SMB.
   - Remote share: `ha_backups`.
   - Username: `ha_user`.
   - Password: the password from Step 1.3.
   - (If offered) SMB version: leave default / v2.1+; matches Step 1.5.

2.4 Connect.
   Verify Step 2: the share shows Connected under Network storage. If it fails: 90% of the time it is the share name, the IP, or the `ha_user` password. Re-check Step 1.4 permissions.

---

## Step 3 -- Configure automatic backups `[UI-HA]` + `[VAULT]`

This is the core. Do it carefully -- the data-selection and emergency-kit choices here are the ones that bite people at restore time.

3.1 Settings > System > Backups > Set up backups (first-time), or Automatic backups > Configure automatic backups (if already initialized).

3.2 Schedule.
   - Frequency: Daily.
   - Time: choose Custom and set a time you KNOW the NAS is awake (aligns with Step 1.6). If you chose 1.6-A (hibernation off), any time is fine; pick a quiet hour, e.g. 03:30. Avoid "System optimal" only if you took the hibernation-B route and need a guaranteed-awake window.

3.3 Create backup before updating.
   - Turn this ON. HA will snapshot before every core/OS/add-on update so a bad update is a one-click rollback.

3.4 Choose what data to include (the recorder-DB exclusion).
   - Home Assistant settings/configuration: ON (this is your config, .storage, registries -- the irreplaceable half).
   - History (the recorder database, `home-assistant_v2.db`): turn OFF.
     This is the "EXCLUDE the recorder database" requirement. Long-term tub data lives in InfluxDB (Phase E), so the SQLite history is disposable and only bloats the archive. Turning History OFF keeps each backup roughly 50-500 MB instead of multiple GB, which is what makes the Google Drive free 15 GB tier viable.
   - Media: OFF (large, non-critical).
   - Share folder: OFF.
   - Add-ons: include the ones whose state you cannot rebuild from YAML -- specifically Zigbee2MQTT and deCONZ once they exist (their pairing databases live in add-on data, per the handoff Reconciliation note), and the SSH add-on config. You can leave InfluxDB/Grafana add-ons included too; they are small at first. Exclude nothing you would have to re-pair.
   IMPORTANT: set this data selection during the INITIAL "Set up backups" flow. On some versions the data-selection toggles become greyed-out / read-only after initial setup, and changing them later can require re-running setup. Get it right now.

3.5 Retention.
   Retention in the native UI is a single global policy across locations (there is no per-location retention in the built-in scheduler as of this writing). Set it to satisfy the SMALLEST-capacity location so nothing overflows:
   - Set "number of backups to keep" = 30. (Daily x 30 = ~30 days of history.)
   - This gives NAS the requested ~30 copies. Google Drive would then also try to hold ~30. At ~200-500 MB each that is ~6-15 GB -- close to the 15 GB free ceiling. See "Open decisions": if you want Drive at ~5-10 copies specifically, the built-in scheduler cannot do per-location counts. Options: (a) accept 30 everywhere and rely on the small (History-excluded) size, (b) set global retention lower (e.g. 10) and accept fewer NAS copies, or (c) later move to a `backup.create_automatic` automation for per-location control. Recommended for now: global = 15 (a safe middle: ~15 days, comfortably under Drive's 15 GB with History excluded, still a healthy NAS depth). Record the number you chose.

3.6 Locations. Enable Local (the NVMe) and `ds218-backups` now. Google Drive will be added to this same Locations list AFTER Step 4 -- come back and enable it in Step 5. (Local + NAS already gives you 2 of the 3 copies immediately, so you are protected even before Drive is wired.)

3.7 Encryption + EMERGENCY KIT (the #1 restore-killer -- do not rush this).
   - HA generates a backup encryption key on first setup and shows an emergency kit (the key + instructions). Download it when prompted.
   - `[VAULT]` Store the encryption key in your password manager as a dedicated entry, e.g. "HA backup encryption key -- Beelink 2026-07".
   - `[VAULT]` Store ONE offline copy: print the emergency kit or save it to an encrypted USB kept off the HA host and off the NAS. If the key only exists inside HA and inside the backup, a host loss = no restore = total data loss. That is exactly the failure this whole phase exists to prevent.
   - Note in the vault entry the DATE and which host it belongs to; if you ever rotate the key, older backups still need the OLD key to restore.
   - Do NOT store the key in this git repo, in HA's config, or on the NAS share.

Verify Step 3: Settings > System > Backups shows an automatic schedule, "before update" enabled, and Locations listing Local + ds218-backups. The emergency kit is now in your password manager AND offline.

---

## Step 4 -- Google Drive offsite: full OAuth click-path `[EXTERNAL]` then `[UI-HA]`

The official `google_drive` integration is the offsite leg. It needs your own Google Cloud OAuth client. The one non-obvious gotcha: publish the consent screen to production, or the refresh token expires every 7 days and backups silently stop (gotcha #5).

Google Cloud Console reorganized the OAuth screens ("Google Auth Platform" / Audience). The click-path below matches the current console; label wording may drift slightly.

4.1 Go to https://console.cloud.google.com and sign in with the Google account whose Drive (15 GB free) you want to use.

4.2 Create a project. Top project picker > New Project. Name it e.g. `home-assistant-backup`. Create, then select it so it is the active project.

4.3 Enable the Drive API. Shortcut: https://console.developers.google.com/start/api?id=drive with the project selected -> Enable. (Or APIs & Services > Library > search "Google Drive API" > Enable.)

4.4 Open the OAuth / Auth Platform config. APIs & Services > OAuth consent screen (in the newer console this is under "Google Auth Platform"). If prompted to "Get started", proceed.

4.5 App information.
   - App name: `Home Assistant`.
   - User support email: your email.

4.6 Audience: choose External. (Internal is only for Google Workspace org-internal apps; a personal Gmail must use External.)

4.7 Contact information: enter your email.

4.8 Finish the initial consent-screen creation (accept the data policy, Create).

4.9 Publish to production (THE gotcha step). In the OAuth consent screen / Audience view, Publishing status will read "Testing". Click Publish app / "Push to production" and confirm so status becomes "In production".
   - Why: a "Testing" app issues refresh tokens that expire in 7 days, so HA would lose Drive access weekly. "In production" tokens do not expire on that clock.
   - Verification prompts: because the integration uses the narrow `drive.file` scope (app only sees files it created), you can operate unverified. If Google shows an "unverified app" warning during the grant (Step 4.14), that is expected for a personal project -- click Advanced > Go to Home Assistant (unsafe) to proceed. You do not need to complete brand verification for personal use.

4.10 Create the OAuth client.
   - APIs & Services > Credentials > Create Credentials > OAuth client ID.
   - Application type: Web application. (Not "Desktop" -- HA's My Home Assistant redirect requires Web.)
   - Name: `home-assistant`.
   - Authorized redirect URIs > Add URI: paste EXACTLY:
     `https://my.home-assistant.io/redirect/oauth`
   - Create.

4.11 Copy the Client ID and Client Secret shown in the dialog. `[VAULT]` Save both to your password manager (entry: "HA Google Drive OAuth client"). You paste them into HA next.

4.12 (Prereq) Make sure My Home Assistant is set up in HA so the redirect above resolves back to your instance: Settings > System > Network, and/or the My Home Assistant integration; the redirect `https://my.home-assistant.io/redirect/oauth` bounces the OAuth grant back to your local instance URL.

4.13 In HA, add the integration. `[UI-HA]` Settings > Devices & Services > Add Integration > search "Google Drive".
   - If prompted for Application Credentials, paste the Client ID and Client Secret from 4.11.
   - Continue; HA opens the Google account chooser.

4.14 Grant access. Pick the Google account, work through the "unverified app" advanced-continue if shown (see 4.9), and approve the `drive.file` permission. The page shows "Link account to Home Assistant?" -- confirm. HA reports success and creates a `Home Assistant` folder in that Drive.

Verify Step 4: Settings > Devices & Services shows Google Drive connected. A `Home Assistant` folder now exists in the Google Drive account (Drive web > My Drive).

---

## Step 5 -- Enable all 3 locations (make it 3-2-1) `[UI-HA]`

5.1 Settings > System > Backups > Automatic backups > Configure automatic backups > Locations.

5.2 Enable all three: Local, `ds218-backups`, Google Drive.
   Verify: the automatic backup Locations list shows all three toggled on. This is the moment you actually have 3-2-1 configured (2 media types: NVMe + NAS HDD + cloud; 1 offsite: Drive).

---

## Step 6 -- First backup + verify the copies actually land `[UI-HA]`

Do not trust a config you have not exercised.

6.1 Settings > System > Backups > (three-dot menu) > Create automatic backup now (this uses your configured settings/locations), or the "Back up now" action. Alternatively call the `backup.create_automatic` action from Developer Tools > Actions.

6.2 Watch `sensor.backup_manager_state` (Developer Tools > States) move through creating -> uploading -> idle.

6.3 Verify all three copies exist:
   - Local: appears in the Backups list.
   - NAS: browse `\\<NAS-IP>\ha_backups` -- a `.tar` backup file is present.
   - Drive: the `Home Assistant` folder in Drive contains the backup.

6.4 Verify the monitoring entities populated: `sensor.backup_last_successful_automatic_backup` now holds a recent timestamp (no longer `unknown`). This is the entity the dead-man alert keys on -- it MUST be present and enabled (Step 0.3) before Step 7 is meaningful.

6.5 Confirm backup size is small (History excluded worked): the archive should be tens-to-hundreds of MB, not multiple GB. If it is GB-scale, re-check Step 3.4 (History toggle) -- it may have been left ON or greyed.

---

## Step 7 -- Deploy the dead-man backup alert `[FILE]`

File: `docs/ha-migration/deadman-backup-alert.yaml` (in this repo).

What it does: if no successful automatic backup has completed in ~48h (or the sensor is missing/stale), it pushes to `notify.mobile_app_chris_phone`, raises a persistent notification, and logs a warning -- matching the existing `tou_watchdog.yaml` / `stale_data.yaml` watchdog pattern.

Where it belongs: the tublemetry-ha DEPLOY repo, under `packages/` -- NOT a UI-clicked automation. Rationale:
   - It is a top-level `automation:` package, identical in shape to `ha/tou_watchdog.yaml` and `ha/stale_data.yaml`, so it drops straight into the same packages mechanism.
   - The declarative/git layer is the source of truth the handoff wants preserved. A UI automation would live only in `.storage`, be invisible to the repo, and be lost on exactly the kind of host rebuild this phase is defending against. A backup-health watchdog that only survives in the thing it is watching is self-defeating.
   - It depends only on core backup entities (`sensor.backup_last_successful_automatic_backup`, `event.backup_automatic_backup`) and the already-used `notify.mobile_app_chris_phone`, so it is portable to any restore of this instance.

Deploy steps:
   7.1 Copy `deadman-backup-alert.yaml` into the tublemetry-ha deploy repo as `packages/deadman_backup_alert.yaml` (use the gh-API push method noted in project memory, not a local clone push).
   7.2 Ensure packages are loaded (the repo already uses the packages format; this file follows the same top-level-`automation:` convention as the other `ha/*.yaml` packages).
   7.3 In HA: Developer Tools > YAML > Check Configuration, then Reload Automations (or restart).
   7.4 Verify: the automation "Backup Dead-Man Alert" appears in Settings > Automations. Trigger a dry run -- Developer Tools > Actions won't test the time logic, so instead temporarily set the staleness threshold low, reload, confirm you get a phone push, then restore 48h. (Or simply trust the template and confirm it does NOT fire while a fresh backup exists.)

Detecting "last successful backup" in current HA (verified): the native Backup integration exposes `sensor.backup_last_successful_automatic_backup` (a `timestamp` sensor) and `event.backup_automatic_backup` (state reflects last automatic backup: in progress / completed / failed). The alert uses the timestamp sensor as the reliable primary signal and the event entity as an optional immediate-on-failure trigger (the exact `event_type` string on the event entity should be confirmed once against your live Developer Tools > States, per the comment in the YAML).

---

## Step 8 -- DR test-restore rehearsal on the Pi 4 `[UI-HA]` + hardware

A backup you have never restored is a hope, not a backup. Rehearse now, on the freed Pi 4 (or a throwaway HAOS VM), so the real thing is muscle memory.

8.1 Prep target hardware: the freed Raspberry Pi 4 (per handoff: available once Homebridge retires; if not yet free, use a throwaway HAOS x86 VM on any spare machine). Flash HAOS to the Pi 4 SD/USB (this is a REHEARSAL host, SD is fine here).

8.2 Boot HAOS on the Pi 4 to the onboarding screen (`homeassistant.local:8123` on that device -- do it on an isolated port/hostname so it does not fight the live Beelink; easiest is to bring the Pi 4 up while the Beelink is reachable by IP and the Pi by `homeassistant.local`, or do it on a separate VLAN/subnet).

8.3 On the onboarding screen choose "Restore from backup".

8.4 Pull the backup: upload the `.tar` you copied from the NAS share (or point at Google Drive). Use a recent Step-6 backup.

8.5 When prompted, enter the BACKUP ENCRYPTION KEY from your emergency kit (Step 3.7). THIS is the moment that validates the #1 gotcha -- if the key in your vault does not decrypt the backup, you found out on a rehearsal instead of during a real outage. If it fails, stop and fix your emergency-kit storage before trusting production.

8.6 Let the restore complete and boot.

8.7 Validate portability (verified restore is usable):
   - HA starts and your config/dashboards are present.
   - Note what is EXPECTED to be absent/needing action: history/graphs will be empty (History was excluded by design -- InfluxDB holds the real long-term data); hardware-bound integrations (Zigbee coordinators on `/dev/serial/by-id/...`, Awair/Kasa/etc.) will be offline because the radios are physically on the Beelink -- that is correct, not a restore failure.
   - Confirm `.storage`-based integrations/config entries came back (this is the half the git repo does NOT cover -- validating it here proves the backup regime covers what the repo cannot).

8.8 Record the result (pass/fail + the encryption-key check) in the migration handoff doc, then wipe the Pi 4 rehearsal instance so it does not linger as a rogue HA on the network.

---

## Emergency-kit / encryption-key handling (summary card)

- Two independent copies, both OUTSIDE HA and OUTSIDE the NAS: (1) password manager entry, (2) one offline copy (print or encrypted USB kept elsewhere).
- Label each copy with host + date. If you ever regenerate the key, keep the old one -- older archives still decrypt only with the key that made them.
- Never commit the key to this repo, HA config, or the backup share.
- Rehearse decryption (Step 8.5) at least once, and again after any key rotation.
- This single item is the most common cause of failed restores. Treat losing it as equivalent to losing every backup.

---

## Open decisions the user must make

1. NAS hibernation strategy (Step 1.6): disable HDD hibernation on the DS218+ (recommended, simplest) OR keep it and pin a Custom backup time to a guaranteed-awake window. Pick one; it determines the Step 3.2 time.

2. Retention number (Step 3.5): the built-in scheduler is a SINGLE global count across all locations -- it cannot do "NAS 30 / Drive 5-10" natively. Choose:
   - Global 30 (matches NAS target; Drive holds 30 small History-excluded archives, ~6-15 GB, near the free ceiling), or
   - Global ~15 (recommended middle -- comfortably under Drive 15 GB, still healthy depth), or
   - Global ~10 (safest for Drive, fewer NAS copies), or
   - Defer per-location control to a future `backup.create_automatic` automation.
   Recommendation: start at 15, revisit once you see real archive sizes from Step 6.5.

3. Backup time of day (Step 3.2): pick the quiet hour (default suggestion 03:30) consistent with decision #1.

4. Which add-ons to include in backups (Step 3.4): definitely Zigbee2MQTT + deCONZ (pairing DBs) and SSH once they exist in Phase D; decide whether to also carry InfluxDB/Grafana data (grows over time -- you may later exclude their bulky data and back up only their config).

5. DR rehearsal target (Step 8): Pi 4 (if Homebridge is retired) vs throwaway HAOS VM now. If the Pi 4 is not yet free, do the VM rehearsal now and repeat on the Pi 4 later.

---

## Gotchas carried from the handoff (do not trip on these)

1. Encryption key OUTSIDE HA -- #1 restore-killer. Steps 3.7 + 8.5.
2. NAS sleep breaks scheduled backups -- Step 1.6 + 3.2.
3. Google OAuth must be "In production" or tokens die every 7 days -- Step 4.9.
4. Set the History (database) toggle OFF during INITIAL setup -- it can be greyed-out later. Step 3.4.
5. Network storage Usage must be "Backup" or it will not appear as a Location. Step 2.3.
6. Use the least-privilege `ha_user`, never admin, and grant File Station + Read/Write on only `ha_backups`. Step 1.

---

## Sources (verified for ~2026.7)

- Home Assistant Backup integration (sensors, event entity, backup.create_automatic): https://www.home-assistant.io/integrations/backup/
- Common tasks -- backups (setup, schedule, retention, data selection, emergency kit): https://www.home-assistant.io/common-tasks/general/
- Common tasks (OS) -- network storage / backup before update: https://www.home-assistant.io/common-tasks/os/
- Google Drive backup integration (OAuth click-path, redirect URI, publish to production): https://www.home-assistant.io/integrations/google_drive/
- Recorder integration (database size / retention context): https://www.home-assistant.io/integrations/recorder/
- Synology: Assign Shared Folder Permissions: https://kb.synology.com/en-global/DSM/help/DSM/AdminCenter/file_share_privilege
- Synology: SMB settings / hibernation warnings: https://kb.synology.com/en-in/DSM/help/SMBService/smbservice_smb_settings
- Synology: What stops the NAS from hibernating: https://kb.synology.com/en-au/DSM/tutorial/What_stops_my_Synology_NAS_from_entering_System_Hibernation
