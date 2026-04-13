"""Package format validation for ha/ YAML files.

HA packages require:
- Single-document YAML (no --- separators)
- Top-level domain key (automation:, template:, sql:, etc.)
- Each file is a standalone, self-contained package
"""

from pathlib import Path

import yaml

HA_DIR = Path(__file__).parent.parent / "ha"

# Files excluded from package validation
DASHBOARD = "dashboard.yaml"

# Files that must have automation: as top-level key
AUTOMATION_FILES = [
    "tou_automation.yaml",
    "thermal_runaway.yaml",
    "thermal_runaway_clear.yaml",
    "stale_data.yaml",
    "drift_detection.yaml",
]

# HA domain keys recognized by the packages system
HA_DOMAIN_KEYS = {
    "automation",
    "template",
    "sql",
    "input_boolean",
    "input_number",
    "input_text",
    "input_select",
    "input_datetime",
    "sensor",
    "binary_sensor",
    "script",
    "shell_command",
    "scene",
    "group",
    "switch",
    "light",
    "cover",
    "fan",
    "climate",
    "camera",
    "alert",
    "counter",
    "timer",
}


def _package_files():
    """All ha/*.yaml files except dashboard.yaml."""
    return [f for f in sorted(HA_DIR.glob("*.yaml")) if f.name != DASHBOARD]


# --- PKG-01: All files parse as valid single-document YAML ---


def test_all_yaml_single_document():
    """Every ha/*.yaml (except dashboard) parses with yaml.safe_load."""
    for path in _package_files():
        text = path.read_text()
        data = yaml.safe_load(text)
        assert data is not None or path.name == "heating_tracker.yaml", (
            f"{path.name} did not parse as valid YAML"
        )


# --- PKG-04: No multi-document separators ---


def test_no_multi_document_separators():
    """No ha/*.yaml (except dashboard) contains a bare '---' line."""
    for path in _package_files():
        lines = path.read_text().splitlines()
        for i, line in enumerate(lines, 1):
            assert line.strip() != "---", (
                f"{path.name}:{i} contains multi-document separator '---'"
            )


# --- PKG-02: Automation files have automation: domain key ---


def test_automation_files_have_domain_key():
    """Each automation file has 'automation' as a top-level key containing a list."""
    for name in AUTOMATION_FILES:
        path = HA_DIR / name
        data = yaml.safe_load(path.read_text())
        assert isinstance(data, dict), f"{name} did not parse as a dict"
        assert "automation" in data, f"{name} missing 'automation' top-level key"
        assert isinstance(data["automation"], list), (
            f"{name} 'automation' value is not a list"
        )


# --- PKG-05: templates.yaml has template: domain key ---


def test_templates_have_domain_key():
    """templates.yaml has 'template' as a top-level key."""
    path = HA_DIR / "templates.yaml"
    data = yaml.safe_load(path.read_text())
    assert isinstance(data, dict), "templates.yaml did not parse as a dict"
    assert "template" in data, "templates.yaml missing 'template' top-level key"


# --- PKG-06: thermal_model.yaml is merged single document ---


def test_thermal_model_merged():
    """thermal_model.yaml is a single document with sql, template, input_number, automation keys."""
    path = HA_DIR / "thermal_model.yaml"
    data = yaml.safe_load(path.read_text())
    assert isinstance(data, dict), "thermal_model.yaml did not parse as a dict"
    for key in ("sql", "template", "input_number", "automation"):
        assert key in data, f"thermal_model.yaml missing '{key}' top-level key"


# --- PKG-03: helpers.yaml defines input_boolean.thermal_runaway_active ---


def test_helpers_define_thermal_runaway():
    """helpers.yaml exists with input_boolean.thermal_runaway_active."""
    path = HA_DIR / "helpers.yaml"
    assert path.exists(), "ha/helpers.yaml does not exist"
    data = yaml.safe_load(path.read_text())
    assert "input_boolean" in data, "helpers.yaml missing 'input_boolean' key"
    ib = data["input_boolean"]
    assert "thermal_runaway_active" in ib, (
        "helpers.yaml missing 'thermal_runaway_active'"
    )
    entry = ib["thermal_runaway_active"]
    assert "name" in entry, "thermal_runaway_active missing 'name'"
    assert "icon" in entry, "thermal_runaway_active missing 'icon'"


# --- PKG-08: dashboard.yaml excluded from packages ---


def test_dashboard_excluded():
    """dashboard.yaml has no top-level HA domain key (reference-only)."""
    path = HA_DIR / DASHBOARD
    text = path.read_text()
    # dashboard.yaml is multi-document (Lovelace cards), parse all docs
    for doc in yaml.safe_load_all(text):
        if isinstance(doc, dict):
            assert not (set(doc.keys()) & HA_DOMAIN_KEYS), (
                f"dashboard.yaml has HA domain keys: {set(doc.keys()) & HA_DOMAIN_KEYS}"
            )


# --- PKG-09: heating_tracker.yaml is deprecated (comment-only) ---


def test_heating_tracker_deprecated():
    """heating_tracker.yaml is comment-only with no YAML domain keys."""
    path = HA_DIR / "heating_tracker.yaml"
    data = yaml.safe_load(path.read_text())
    # yaml.safe_load returns None for comment-only files
    assert data is None, (
        f"heating_tracker.yaml has YAML content (should be comment-only): {type(data)}"
    )


# --- Sanity checks for already-valid files ---


def test_heater_power_already_valid():
    """heater_power.yaml has 'template' as top-level key (no changes needed)."""
    path = HA_DIR / "heater_power.yaml"
    data = yaml.safe_load(path.read_text())
    assert isinstance(data, dict), "heater_power.yaml did not parse as a dict"
    assert "template" in data, "heater_power.yaml missing 'template' top-level key"


def test_sensors_already_valid():
    """sensors.yaml has 'sql' as top-level key (no changes needed)."""
    path = HA_DIR / "sensors.yaml"
    data = yaml.safe_load(path.read_text())
    assert isinstance(data, dict), "sensors.yaml did not parse as a dict"
    assert "sql" in data, "sensors.yaml missing 'sql' top-level key"
