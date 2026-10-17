"""The podman command group."""

from .base import Command, Group, Param
from ..params import LocalReadableFileType


def make_group(client_root):
    """Build the podman command group with client-root-aware file params."""
    build = Command(
        name="build",
        description="Build a container image from a Containerfile in the project directory",
        params={
            "file": Param(
                LocalReadableFileType(client_root),
                "Path to the Containerfile, relative to the project directory",
                required=True,
            ),
        },
        build_argv=lambda args: ["podman", "build", "-f", str(args["file"]), "."],
    )
    return Group("podman", "Container image management via podman", {"build": build})
