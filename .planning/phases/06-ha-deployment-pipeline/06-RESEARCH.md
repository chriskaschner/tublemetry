# Phase 6: HA Deployment Pipeline - Research

**Researched:** 2026-04-12
**Domain:** Home Assistant packages, Git Pull add-on, YAML config management
**Confidence:** HIGH

## Summary

This phase converts the existing `ha/` YAML files into proper HA packages and sets up automated sync from GitHub to the RPi4 HA instance. The research uncovered three critical findings that shape the plan:

1. **Most ha/ files need restructuring.** Bare automation files (tou_automation.yaml, thermal_runaway.yaml, etc.) need wrapping under an `automation:` key. Multi-document files using `---` separators (thermal_model.yaml, heating_tracker.yaml, dashboard.yaml) must be consolidated into single-document package files because HA's YAML parser does not support multi-document files.

2. **The Git Pull add-on clones/syncs the entire repo to /config -- not a subdirectory.** This means the repo cannot remain in its current structure (ha/ as a subdirectory). The safest approach is a shell_command-based pull that copies only the packages directory, OR restructuring the repo so the ha/ files live at `packages/` in the repo root with a `.gitignore` that excludes everything else. Given D-01 (use Git Pull add-on), the recommended approach is a shell_command automation that pulls and copies, since the add-on's whole-repo behavior risks overwriting non-git-managed HA files.

3. **Dashboard YAML cannot be deployed via packages.** Lovelace dashboards require either storage mode (UI) or a separate YAML mode configuration under the `lovelace:` key in configuration.yaml -- not packages. The dashboard.yaml file should remain a reference/paste file.

**Primary recommendation:** Restructure ha/ files as single-document HA packages with proper domain key wrappers, create a helpers.yaml package for input_boolean, use a shell_command + automation for git pull + selective reload instead of the Git Pull add-on (which risks config wipe), and exclude dashboard.yaml from the packages pipeline.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Use the official HA Git Pull add-on to auto-sync from this GitHub repo
- **D-02:** Git Pull add-on auto-reloads automations only after pull (calls `automation.reload`). Template sensors and other config requiring restart are handled manually.
- **D-03:** Use HA packages directory structure (`/config/packages/`). Each `ha/*.yaml` file becomes a standalone package. HA merges packages automatically at load time.
- **D-04:** Repo `ha/` directory maps 1:1 to `/config/packages/` -- no file merging or splitting required.
- **D-05:** Define `input_boolean.thermal_runaway_active` and any other helper entities in a YAML package file (e.g., `ha/helpers.yaml`). Git-managed and auto-deployed alongside automations.
- **D-06:** All `ha/*.yaml` files auto-sync to HA packages directory. This includes automations, template sensors (heater_power.yaml), helpers, dashboard config, and all other YAML files.
- **D-07:** No manual file placement required -- HA packages support automations, template sensors, input_booleans, and template entities natively.

### Claude's Discretion
- Git Pull add-on configuration details (pull interval, branch, repo URL format)
- Whether to add a post-pull script for the automation reload call
- Directory structure for the HA packages mapping (symlink vs copy)
- Whether to include a `configuration.yaml` snippet for enabling packages

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope

</user_constraints>

## Critical Research Findings

### Finding 1: Git Pull Add-on Syncs Entire Repo to /config (HIGH RISK)

The Git Pull add-on operates on the `/config` directory directly. On first run, it clones the entire repo INTO `/config`. On subsequent runs, it does `git pull` within `/config`. There is NO subdirectory-only sync option. [VERIFIED: official docs and GitHub DOCS.md]

**Risk:** If tubtron's repo (which contains firmware source, tests, protocol docs, etc.) is pointed at by the Git Pull add-on, ALL repo files would land in `/config`, potentially overwriting HA's `.storage/`, `secrets.yaml`, and other critical files. Multiple GitHub issues document this exact problem (#1325, #1690, #2653, #3547). [VERIFIED: GitHub issues]

**Implication for D-01:** The Git Pull add-on CAN still be used, but ONLY if:
- Option A: A SEPARATE repo is created containing only the packages/ directory, OR
- Option B: The tubtron repo is restructured so `packages/` is at the root with aggressive `.gitignore`, OR
- Option C: Use `shell_command` + automation instead (more flexible, same result)

**Recommendation (Claude's Discretion):** Use Option C -- a `shell_command` in HA that does `cd /config/tubtron-repo && git pull && cp -r ha/* /config/packages/`. This is triggered by a webhook from GitHub Actions or a periodic automation. This preserves D-01's intent (auto-sync from git) without the config-wipe risk, and keeps the repo structure unchanged.

### Finding 2: Existing ha/ Files Need Package-Format Restructuring

HA packages require each file to be a single YAML document with proper domain-key wrappers. [VERIFIED: official HA packages docs]

Current file analysis:

| File | Current Format | Package-Ready? | Action Needed |
|------|---------------|----------------|---------------|
| `tou_automation.yaml` | Bare automation (alias at top) | NO | Wrap in `automation:` list |
| `thermal_runaway.yaml` | Bare automation | NO | Wrap in `automation:` list |
| `thermal_runaway_clear.yaml` | Bare automation | NO | Wrap in `automation:` list |
| `drift_detection.yaml` | Bare automation | NO | Wrap in `automation:` list |
| `stale_data.yaml` | Bare automation | NO | Wrap in `automation:` list |
| `heater_power.yaml` | Has `template:` key | YES | No changes needed |
| `sensors.yaml` | Has `sql:` key | YES | No changes needed |
| `templates.yaml` | List format `- sensor:` | NO | Wrap in `template:` key |
| `thermal_model.yaml` | Multi-doc (`---`) with sql, template, input_number, automation | NO | Merge into single document |
| `heating_tracker.yaml` | Multi-doc (`---`) with 2 automations | NO | Merge into single document, wrap in `automation:` list |
| `dashboard.yaml` | Multi-doc Lovelace cards | N/A | Cannot be a package (see Finding 3) |

[VERIFIED: parsed all 11 files with yaml.safe_load]

### Finding 3: Dashboard Cannot Be Deployed via Packages

Lovelace dashboards are NOT supported in HA packages. Dashboards require either:
- Storage mode (managed via UI, stored in `.storage/`)
- YAML mode (configured under `lovelace:` key in `configuration.yaml`, separate from packages)

The `ha/dashboard.yaml` file contains individual Lovelace card definitions separated by `---`. This is a paste-reference file -- it cannot be auto-deployed as a package. [VERIFIED: official HA dashboard docs]

**Recommendation:** Exclude `dashboard.yaml` from the packages pipeline. It remains a reference doc for manual dashboard setup.

## Standard Stack

### Core
| Component | Version | Purpose | Why Standard |
|-----------|---------|---------|--------------|
| HA Packages | N/A (built-in) | Modular YAML config organization | Official HA feature, allows grouping related config in single files |
| shell_command | N/A (built-in) | Run git pull from within HA | Built-in HA integration for shell scripts |
| automation.reload | N/A (built-in) | Hot-reload automations after pull | No restart needed for automation changes |

### Supporting
| Component | Version | Purpose | When to Use |
|-----------|---------|---------|-------------|
| template.reload | N/A (built-in) | Hot-reload template entities | When template sensor YAML changes |
| input_boolean.reload | N/A (built-in) | Hot-reload input helpers | When input_boolean YAML changes |
| input_number.reload | N/A (built-in) | Hot-reload input number helpers | When input_number YAML changes |
| homeassistant.reload_all | N/A (built-in) | Reload all YAML config at once | Nuclear option -- reloads everything reloadable |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| shell_command git pull | Git Pull add-on | Add-on syncs whole repo to /config -- high risk of config wipe |
| Manual copy | Symlink ha/ -> packages/ | Symlinks may not work in HA OS container filesystem |
| homeassistant.reload_all | Individual reload services | reload_all is simpler but more resource-intensive |

## Architecture Patterns

### Recommended Package File Structure

Each `ha/*.yaml` file becomes a self-contained HA package:

```yaml
# ha/tou_automation.yaml -- AFTER restructuring
automation:
  - alias: Hot Tub TOU Schedule
    description: >
      Rg-2A TOU setpoint control...
    mode: single
    trigger:
      - platform: time
        at: "04:30:00"
        id: wd_preheat
      # ... rest of triggers
    condition:
      - condition: state
        entity_id: input_boolean.thermal_runaway_active
        state: "off"
    action:
      - choose:
          # ... rest of actions
```

### Pattern 1: Bare Automation -> Package Automation
**What:** Wrap bare automation dict in `automation:` list
**When to use:** Every file that currently starts with `alias:` at the top level
**Example:**
```yaml
# BEFORE (bare automation -- not valid as package)
alias: My Automation
mode: single
trigger: [...]
action: [...]

# AFTER (valid HA package)
automation:
  - alias: My Automation
    mode: single
    trigger: [...]
    action: [...]
```
[CITED: https://www.home-assistant.io/docs/configuration/packages/]

### Pattern 2: Multi-Domain Package
**What:** Single file with multiple HA domain keys
**When to use:** When related config spans domains (e.g., thermal_model.yaml has sql, template, input_number, automation)
**Example:**
```yaml
# ha/thermal_model.yaml -- merged single document
sql:
  - name: "Hot Tub Heating Rate"
    db_url: sqlite:////config/home-assistant_v2.db
    # ...

template:
  - sensor:
      - name: "Hot Tub Preheat Minutes"
        # ...

input_number:
  hot_tub_heating_rate_snapshot:
    name: "Hot Tub Heating Rate (snapshot)"
    # ...

automation:
  - alias: "Hot Tub Refresh Thermal Model"
    trigger:
      - platform: time
        at: "03:00:00"
    action:
      # ...
```
[CITED: https://www.home-assistant.io/docs/configuration/packages/]

### Pattern 3: Helper Entity Package
**What:** Dedicated package for input_boolean and other helper entities
**When to use:** For cross-cutting helpers referenced by multiple automations
**Example:**
```yaml
# ha/helpers.yaml
input_boolean:
  thermal_runaway_active:
    name: "Thermal Runaway Active"
    icon: mdi:alert-octagon
```
[CITED: https://www.home-assistant.io/integrations/input_boolean/]

### Pattern 4: Deploy Script Package
**What:** Package containing shell_command and automation for git-based deployment
**When to use:** The deploy pipeline itself
**Example:**
```yaml
# ha/deploy.yaml
shell_command:
  tubtron_pull: >
    cd /config/tubtron && git pull origin main &&
    cp ha/*.yaml /config/packages/

automation:
  - alias: "Tubtron Deploy and Reload"
    description: "Pull latest config from GitHub and reload automations"
    mode: single
    trigger:
      - platform: time
        at: "03:30:00"
    action:
      - action: shell_command.tubtron_pull
      - delay: "00:00:05"
      - action: automation.reload
      - action: template.reload
      - action: input_boolean.reload
      - action: input_number.reload
```
[ASSUMED] -- the shell_command approach for git pull + copy + reload is a community pattern, not an official documented workflow

### Pattern 5: Template Sensor List -> Package Format
**What:** Wrap template sensor list under `template:` key
**When to use:** For templates.yaml which currently uses bare list format
**Example:**
```yaml
# BEFORE (list format -- not valid as package)
- sensor:
    - name: Outdoor Temperature
      state: "{{ state_attr('weather.forecast_home', 'temperature') }}"

# AFTER (valid HA package)
template:
  - sensor:
      - name: Outdoor Temperature
        state: "{{ state_attr('weather.forecast_home', 'temperature') }}"
```
[CITED: https://www.home-assistant.io/integrations/template/]

### Anti-Patterns to Avoid
- **YAML multi-document separators (`---`):** HA packages must be single-document YAML. Files with `---` separators will cause parse errors. [VERIFIED: yaml.safe_load throws errors on thermal_model.yaml, heating_tracker.yaml, dashboard.yaml]
- **Duplicate domain keys across packages:** If `input_boolean.thermal_runaway_active` is defined both in helpers.yaml package AND in configuration.yaml, HA will error on startup. Each entity key must be globally unique. [CITED: https://www.home-assistant.io/docs/configuration/packages/]
- **Using Git Pull add-on with a non-config-mirrored repo:** The add-on will overwrite /config with repo contents, potentially deleting .storage/, secrets.yaml, and other HA-managed files. [VERIFIED: GitHub issues #1325, #1690, #3547]
- **Relying on `input_boolean` unique_id:** As of 2024, `unique_id` is not a valid option for `input_boolean` in YAML -- it will cause a config validation error. [VERIFIED: GitHub issue #109741]

### configuration.yaml Snippet Required

The HA instance needs this in its `configuration.yaml` to enable packages:

```yaml
homeassistant:
  packages: !include_dir_named packages/
```

This tells HA to load every `.yaml` file in `/config/packages/` as a named package (filename without extension becomes the package name).

[CITED: https://www.home-assistant.io/docs/configuration/packages/]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Config sync from git | Custom rsync/scp scripts | shell_command with git pull + cp | Built-in HA integration, atomic operations |
| Automation reload after deploy | Custom REST API calls | automation.reload service action | HA native service, no auth token management |
| Helper entity management | UI-created helpers (non-reproducible) | YAML package with input_boolean | Git-managed, auto-deployed, reproducible |
| YAML validation | Manual review | `ha core check_config` or pytest YAML parse | Automated, catches errors before deploy |

## Common Pitfalls

### Pitfall 1: Multi-Document YAML Files
**What goes wrong:** HA packages expect single-document YAML. Files with `---` separators cause "expected a single document" parse errors at startup.
**Why it happens:** Several ha/ files were originally written as paste-reference docs with multiple sections separated by `---`.
**How to avoid:** Merge all sections into one document. Remove all `---` separators. Each domain key appears once at the top level.
**Warning signs:** HA logs show "expected a single document in the stream" errors.

### Pitfall 2: Bare Automations Without Domain Wrapper
**What goes wrong:** A YAML file starting with `alias:` is a valid automation dict but NOT a valid package -- HA doesn't know what domain it belongs to.
**Why it happens:** Automations created via the UI or copy-pasted from docs use the bare format.
**How to avoid:** Always wrap under `automation:` list. The file must have `automation:` as a top-level key with a list of automation dicts underneath.
**Warning signs:** HA startup logs show unknown integration errors or silently ignores the file.

### Pitfall 3: Git Pull Add-on Config Wipe
**What goes wrong:** First run of Git Pull add-on clones the repo to /config, replacing ALL existing files. .storage/ directory deleted, all UI-configured entities lost.
**Why it happens:** The add-on treats the ENTIRE /config as the git working tree. There is no subdirectory option.
**How to avoid:** Use shell_command approach instead, or ensure the repo ONLY contains files safe for /config.
**Warning signs:** After first run, HA fails to start because .storage/ is missing.

### Pitfall 4: Entity ID Conflicts Between Packages and Main Config
**What goes wrong:** If `input_boolean.thermal_runaway_active` is defined both in a package and via the Helpers UI (stored in .storage/), HA throws a duplicate entity error.
**Why it happens:** UI-created helpers and YAML-defined helpers share the same namespace.
**How to avoid:** Before deploying the helpers.yaml package, DELETE any UI-created input_boolean.thermal_runaway_active helper from Settings > Devices & Services > Helpers.
**Warning signs:** HA startup error: "duplicate key" or entity shows as unavailable.

### Pitfall 5: Shell Command 60-Second Timeout
**What goes wrong:** HA's shell_command integration kills processes after 60 seconds with no option to extend.
**Why it happens:** HA design decision -- not intended for long-running processes.
**How to avoid:** The git pull + cp operation should complete well within 60 seconds for a small repo. If not, break into separate commands.
**Warning signs:** shell_command returns error in HA logs after timeout. [CITED: https://www.home-assistant.io/integrations/shell_command/]

### Pitfall 6: Heating Tracker References Removed Climate Entity
**What goes wrong:** heating_tracker.yaml references `climate.hot_tub` which was removed in Phase 2 (replaced with sensor + number entities).
**Why it happens:** heating_tracker.yaml was written before the Phase 2 architecture fix.
**How to avoid:** Update entity references to use `number.tublemetry_hot_tub_setpoint` and `sensor.tublemetry_hot_tub_temperature` before packaging.
**Warning signs:** Automation fails silently because climate.hot_tub entity doesn't exist.

### Pitfall 7: Template Reload Can Break Cross-References
**What goes wrong:** Reloading template entities can cause template entities that reference OTHER template entities to temporarily show "unavailable."
**Why it happens:** Known HA issue -- template entities are reloaded in no guaranteed order.
**How to avoid:** Use `homeassistant.reload_all` which handles ordering better, or accept brief unavailability. Not a safety concern since all safety automations gate on entity availability.
**Warning signs:** Template sensors show "unavailable" briefly after reload, then recover. [VERIFIED: GitHub issue #40611]

## Code Examples

### Example 1: Wrapping a Bare Automation for Packages

```yaml
# Source: https://www.home-assistant.io/docs/configuration/packages/
# Wrapping tou_automation.yaml for packages

automation:
  - alias: Hot Tub TOU Schedule
    description: >
      Rg-2A TOU setpoint control. Weekday schedule tracks on/off-peak windows.
    mode: single
    trigger:
      - platform: time
        at: "04:30:00"
        id: wd_preheat
      # ... (rest unchanged)
    condition:
      - condition: state
        entity_id: input_boolean.thermal_runaway_active
        state: "off"
    action:
      - choose:
          # ... (rest unchanged)
```

### Example 2: Helpers Package

```yaml
# Source: https://www.home-assistant.io/integrations/input_boolean/
# ha/helpers.yaml -- new file

input_boolean:
  thermal_runaway_active:
    name: "Thermal Runaway Active"
    icon: mdi:alert-octagon
```

### Example 3: configuration.yaml Packages Directive

```yaml
# Source: https://www.home-assistant.io/docs/configuration/packages/
# Add to /config/configuration.yaml on the RPi4

homeassistant:
  packages: !include_dir_named packages/
```

### Example 4: Deploy Shell Command + Automation

```yaml
# ha/deploy.yaml -- deployment pipeline package
# [ASSUMED] -- community pattern, not officially documented

shell_command:
  tubtron_pull: >-
    cd /config/tubtron && git pull origin main 2>&1 &&
    rsync -a --delete /config/tubtron/ha/ /config/packages/
    --exclude=dashboard.yaml --exclude=deploy.yaml

automation:
  - alias: "Tubtron Auto-Deploy"
    description: >
      Periodically pulls latest config from GitHub and reloads.
      deploy.yaml itself is excluded from sync to avoid chicken-and-egg.
    mode: single
    trigger:
      - platform: time
        at: "03:30:00"
    action:
      - action: shell_command.tubtron_pull
      - delay:
          seconds: 5
      - action: automation.reload
      - action: template.reload
      - action: input_boolean.reload
      - action: input_number.reload
```

### Example 5: Merging Multi-Document thermal_model.yaml

```yaml
# ha/thermal_model.yaml -- AFTER merging (no --- separators)

sql:
  - name: "Hot Tub Heating Rate"
    db_url: sqlite:////config/home-assistant_v2.db
    scan_interval: 3600
    query: >
      # ... (SQL unchanged)
    column: "value"
    unit_of_measurement: "F/min"

  - name: "Hot Tub Cooling Rate"
    db_url: sqlite:////config/home-assistant_v2.db
    scan_interval: 3600
    query: >
      # ... (SQL unchanged)
    column: "value"
    unit_of_measurement: "F/hr"

template:
  - sensor:
      - name: "Hot Tub Preheat Minutes"
        unit_of_measurement: "min"
        state_class: measurement
        icon: mdi:timer-outline
        state: >
          # ... (template unchanged)

      - name: "Hot Tub Preheat ETA"
        icon: mdi:clock-outline
        state: >
          # ... (template unchanged)

      - name: "Hot Tub Heat Loss Rate"
        unit_of_measurement: "F/hr"
        state_class: measurement
        icon: mdi:thermometer-minus
        state: >
          # ... (template unchanged)

input_number:
  hot_tub_heating_rate_snapshot:
    name: "Hot Tub Heating Rate (snapshot)"
    min: 0
    max: 5
    step: 0.0001
    unit_of_measurement: "F/min"
    icon: mdi:thermometer-chevron-up

  hot_tub_cooling_rate_snapshot:
    name: "Hot Tub Cooling Rate (snapshot)"
    min: 0
    max: 10
    step: 0.01
    unit_of_measurement: "F/hr"
    icon: mdi:thermometer-chevron-down

automation:
  - alias: "Hot Tub Refresh Thermal Model"
    description: >
      Triggers the SQL sensors to recompute rates once per day.
    trigger:
      - platform: time
        at: "03:00:00"
    action:
      - action: homeassistant.update_entity
        target:
          entity_id:
            - sensor.hot_tub_heating_rate
            - sensor.hot_tub_cooling_rate
      - delay: "00:00:10"
      - action: input_number.set_value
        target:
          entity_id: input_number.hot_tub_heating_rate_snapshot
        data:
          value: >
            {{ states('sensor.hot_tub_heating_rate') | float(0) }}
      - action: input_number.set_value
        target:
          entity_id: input_number.hot_tub_cooling_rate_snapshot
        data:
          value: >
            {{ states('sensor.hot_tub_cooling_rate') | float(0) }}
```

## Reloadable Domains Reference

Services that can be called after a git pull to apply changes without HA restart:

| Domain | Reload Service | Notes |
|--------|---------------|-------|
| automation | `automation.reload` | Reloads all YAML-defined automations |
| template | `template.reload` | Reloads template sensors/binary_sensors |
| input_boolean | `input_boolean.reload` | Reloads YAML-defined input_booleans |
| input_number | `input_number.reload` | Reloads YAML-defined input_numbers |
| script | `script.reload` | Reloads YAML-defined scripts |
| All at once | `homeassistant.reload_all` | Reloads everything reloadable |

**Requires restart (not reloadable):**
- New `shell_command` entries (first definition requires restart; edits to existing commands DO reload)
- New `sql` sensor entries (first definition requires restart)
- Changes to `homeassistant:` core config (packages directive)
- New integration platforms not previously loaded

[CITED: https://www.home-assistant.io/docs/tools/dev-tools/]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `service:` keyword in automations | `action:` keyword | HA 2024.8 | Both work, `action:` is preferred |
| `mode: yaml` for Lovelace | `lovelace: dashboards:` entries | HA 2026.8 (upcoming) | Legacy `mode: yaml` being removed |
| Git Pull add-on for full config | shell_command + webhook automation | Community evolution | More control, less config-wipe risk |
| UI-only helpers | YAML packages for helpers | Always available | Reproducible, git-managed helpers |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2+ |
| Config file | pyproject.toml (pythonpath configured) |
| Quick run command | `uv run pytest tests/ -x --tb=short` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PKG-01 | All ha/*.yaml files parse as valid single-document YAML | unit | `uv run pytest tests/test_packages.py::test_all_yaml_single_document -x` | Wave 0 |
| PKG-02 | All automation files have `automation:` top-level key | unit | `uv run pytest tests/test_packages.py::test_automation_files_have_domain_key -x` | Wave 0 |
| PKG-03 | helpers.yaml defines input_boolean.thermal_runaway_active | unit | `uv run pytest tests/test_packages.py::test_helpers_define_thermal_runaway -x` | Wave 0 |
| PKG-04 | No `---` multi-document separators in any package file | unit | `uv run pytest tests/test_packages.py::test_no_multi_document_separators -x` | Wave 0 |
| PKG-05 | templates.yaml has `template:` top-level key | unit | `uv run pytest tests/test_packages.py::test_templates_have_domain_key -x` | Wave 0 |
| PKG-06 | thermal_model.yaml is single document with sql, template, input_number, automation keys | unit | `uv run pytest tests/test_packages.py::test_thermal_model_merged -x` | Wave 0 |
| PKG-08 | dashboard.yaml excluded from packages (no domain key needed) | unit | `uv run pytest tests/test_packages.py::test_dashboard_excluded -x` | Wave 0 |
| PKG-09 | heating_tracker.yaml is comment-only (deprecated, no YAML domain keys) | unit | `uv run pytest tests/test_packages.py::test_heating_tracker_deprecated -x` | Wave 0 |
| PKG-10 | Existing test suite still passes after restructuring | integration | `uv run pytest tests/ -v` | Existing |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_packages.py -x --tb=short`
- **Per wave merge:** `uv run pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_packages.py` -- covers PKG-01 through PKG-10 (excluding PKG-07, removed)
- [ ] No framework install needed -- pytest already in dev dependencies

## Assumptions Log

> List all claims tagged `[ASSUMED]` in this research.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | shell_command + automation for git pull + copy is the best deployment approach given Git Pull add-on risks | Architecture Patterns | D-01 says use Git Pull add-on -- user may prefer the add-on despite risks, or may want a separate dedicated repo |
| A2 | deploy.yaml excludes itself from rsync to avoid chicken-and-egg | Code Examples | May need different exclusion approach or manual initial setup |
| A3 | The `rsync --delete` pattern is safe for /config/packages/ | Code Examples | Could delete manually-placed packages if any exist |

**Note on A1:** D-01 explicitly says "Use the official HA Git Pull add-on." The research shows this carries significant risk for a repo that isn't structured to mirror /config. The planner should surface this tension to the user -- either restructure the repo, create a separate deployment repo, or deviate from D-01 to use shell_command instead.

## Open Questions (All Resolved)

1. **Git Pull add-on vs shell_command** -- RESOLVED
   - Decision: Separate tublemetry-ha repo with Git Pull add-on (per D-05). The config-wipe risk is eliminated because the dedicated repo contains ONLY package YAML files -- no firmware, tests, or other non-HA content. Git Pull add-on syncs the entire repo to /config/packages/, which is exactly the desired behavior.

2. **heating_tracker.yaml climate entity references** -- RESOLVED
   - Decision: Deprecated. The file is replaced with a comment-only stub (no YAML domain keys). thermal_model.yaml provides the SQL-based heating/cooling rate sensors that supersede it.

3. **Initial deployment bootstrapping (chicken-and-egg)** -- RESOLVED
   - Decision: README in tublemetry-ha documents one-time manual setup: (1) add packages directive to configuration.yaml, (2) install Git Pull add-on, (3) configure add-on to pull tublemetry-ha repo to /config/packages/, (4) restart HA. No deploy.yaml needed.

4. **SQL integration reload** -- RESOLVED
   - Decision: sql: changes require HA restart (not just reload). Documented in tublemetry-ha README reloadable-vs-restart table. Plan 03 README content includes this.
## Sources

### Primary (HIGH confidence)
- [HA Packages Documentation](https://www.home-assistant.io/docs/configuration/packages/) - Package format, merge rules, !include_dir_named
- [HA Git Pull DOCS.md](https://github.com/home-assistant/addons/blob/master/git_pull/DOCS.md) - Configuration options, behavior
- [HA Input Boolean](https://www.home-assistant.io/integrations/input_boolean/) - YAML format, no unique_id support
- [HA Shell Command](https://www.home-assistant.io/integrations/shell_command/) - 60-second timeout, usage pattern
- [HA Automation YAML](https://www.home-assistant.io/docs/automation/yaml/) - Package format for automations
- [HA Template Integration](https://www.home-assistant.io/integrations/template/) - Template sensor format in packages
- [HA Dashboard Docs](https://www.home-assistant.io/dashboards/dashboards/) - YAML mode vs storage mode

### Secondary (MEDIUM confidence)
- [DeepWiki Git Pull](https://deepwiki.com/home-assistant/addons/4.2-git-pull) - Add-on architecture details
- [Frenck's HA Config](https://github.com/frenck/home-assistant-config) - Packages directory pattern reference
- [HA Community: Reload Packages](https://community.home-assistant.io/t/how-to-reload-packages/260944) - Reload behavior confirmed

### Tertiary (LOW confidence)
- GitHub issues on Git Pull config wipe (#1325, #1690, #2653, #3547) - Anecdotal but numerous and consistent

## Metadata

**Confidence breakdown:**
- Package format restructuring: HIGH - verified against official docs and tested YAML parsing
- Git Pull add-on behavior: HIGH - verified via official DOCS.md and multiple GitHub issues
- Reload services: HIGH - verified via official docs
- Deploy script pattern: MEDIUM - community pattern, not officially documented
- Dashboard exclusion: HIGH - verified dashboards are not a packages feature

**Research date:** 2026-04-12
**Valid until:** 2026-05-12 (stable domain, 30 days)
