"""Command registry: name -> group factory."""

from .base import Command, Group, Param  # noqa: F401  (re-exported for command modules)
from .podman import make_group as make_podman_group
from .testing import make_group as make_testing_group

# Factories: name -> callable(client_root) -> Group
REGISTRY = {
    "podman": make_podman_group,
    "testing": make_testing_group,
}
