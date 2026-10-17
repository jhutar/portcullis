"""Command registry: name -> group factory."""

from .base import Command, Group, Param  # noqa: F401  (re-exported for command modules)
from .podman import make_group as make_podman_group

# Factories: name -> callable(client_root) -> Group
REGISTRY = {
    "podman": make_podman_group,
}
