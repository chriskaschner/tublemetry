"""Guard against the same entity being defined by two ha/ packages.

Loading two packages that both define an entity with the same name registers it
twice, and the second copy shows up as '..._2'. This test would have caught the
sensors.yaml / thermal_model.yaml (and templates.yaml preheat) collisions.
"""

from collections import defaultdict
from pathlib import Path

import yaml

HA_DIR = Path(__file__).parent.parent / "ha"
SKIP = {"dashboard.yaml"}


def _identifiers(data):
    """Yield (kind, identifier) pairs an HA package would register."""
    if not isinstance(data, dict):
        return

    # sql / template sensors carry human 'name:' fields
    for entry in data.get("sql", []) or []:
        if isinstance(entry, dict) and "name" in entry:
            yield ("sensor_name", entry["name"])

    for block in data.get("template", []) or []:
        if not isinstance(block, dict):
            continue
        for domain in ("sensor", "binary_sensor", "number", "switch"):
            for item in block.get(domain, []) or []:
                if isinstance(item, dict) and "name" in item:
                    yield ("sensor_name", item["name"])

    # helper domains are keyed by object id
    for domain in ("input_number", "input_boolean", "input_select",
                   "input_text", "input_datetime", "counter", "timer"):
        for key in (data.get(domain) or {}):
            yield (domain, key)

    # automations by alias
    for auto in data.get("automation", []) or []:
        if isinstance(auto, dict) and "alias" in auto:
            yield ("automation", auto["alias"])


def test_no_entity_defined_by_two_packages():
    owners = defaultdict(list)
    for path in sorted(HA_DIR.glob("*.yaml")):
        if path.name in SKIP:
            continue
        data = yaml.safe_load(path.read_text())
        for kind, ident in _identifiers(data):
            owners[(kind, ident)].append(path.name)

    dupes = {k: v for k, v in owners.items() if len(v) > 1}
    assert not dupes, "Entities defined by more than one package:\n" + "\n".join(
        f"  {kind} '{ident}' in {files}" for (kind, ident), files in sorted(dupes.items())
    )
