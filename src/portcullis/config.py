"""TOML config loading and merging for the server."""

import tomllib
from pathlib import Path

DEFAULT_USER_CONFIG = Path.home() / ".config" / "portcullis" / "config.toml"
DEFAULT_LOCAL_CONFIG = Path.cwd() / ".portcullis.toml"


def deep_merge(base, override):
    """Recursively merge override into base and return a new dict."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(user_path=None, local_path=None):
    """Load user config then local override, merged key-by-key, local wins.

    Missing files are skipped. Returns an empty dict when nothing exists.
    """
    merged = {}
    for path in (user_path or DEFAULT_USER_CONFIG, local_path or DEFAULT_LOCAL_CONFIG):
        if path.exists():
            with open(path, "rb") as fh:
                merged = deep_merge(merged, tomllib.load(fh))
    return merged


def compute_client_root(config):
    """Return the client-side project root: configured base + server cwd basename."""
    base = config.get("client", {}).get("root_base", str(Path.home()))
    return str(Path(base) / Path.cwd().name)
