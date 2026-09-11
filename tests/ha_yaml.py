"""Shared loader for ha/*.yaml packages.

ha/hot_tub_button.yaml resolves the button's Zigbee IEEE through Home
Assistant's !secret tag so the hardware address is not published to the PUBLIC
tublemetry-ha repo. Plain yaml.safe_load raises ConstructorError on the unknown
tag, which would break every structural test that reads the packages.

The tag resolves to the SENTINEL below rather than a real-looking value, so a
test can assert "this field is sourced from a secret" and will fail loudly if
someone inlines a literal address again.
"""

from pathlib import Path

import yaml

SECRET_SENTINEL = "SECRET"


class HAYamlLoader(yaml.SafeLoader):
    """SafeLoader that tolerates Home Assistant's !secret tag."""


def _construct_secret(loader: yaml.Loader, node: yaml.Node) -> str:
    return f"{SECRET_SENTINEL}({loader.construct_scalar(node)})"


HAYamlLoader.add_constructor("!secret", _construct_secret)


def load_ha_yaml(path: Path) -> dict:
    """Parse an ha/*.yaml package, resolving !secret to a sentinel string."""
    return yaml.load(path.read_text(), Loader=HAYamlLoader)


def is_secret(value: object, key: str | None = None) -> bool:
    """True if `value` came from a !secret tag (optionally naming the key)."""
    if not isinstance(value, str) or not value.startswith(f"{SECRET_SENTINEL}("):
        return False
    return key is None or value == f"{SECRET_SENTINEL}({key})"
