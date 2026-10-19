"""The podman command group."""

from ..params import (
    GenericEnvVarType,
    GenericListType,
    GenericLocalReadableFileType,
    GenericStringType,
    PodmanImageNameType,
    PodmanVolumeSpecType,
)
from .base import Command, Group, Param


def build_argv(args):
    """Assemble the podman build argv from validated params."""
    return ["podman", "build", "-f", str(args["file"]), "."]


def run_argv(args):
    """Assemble the podman run argv from validated params.

    ``--rm`` removes the container after it exits (no host litter) and
    ``-it`` gives the container a TTY so the run command writes to
    stdout/stderr like a normal process; the session itself is not
    interactive. Volumes and env vars are appended before the image,
    the command words after it, so podman can never mistake them for
    its own flags.
    """
    argv = ["podman", "run", "--rm", "-it"]
    for volume in args.get("volume", []):
        argv += ["-v", volume]
    for env in args.get("env", []):
        argv += ["-e", env]
    argv.append(args["image"])
    argv += args.get("command", [])
    return argv


def make_group(client_root):
    """Build the podman command group with client-root-aware file params."""
    build = Command(
        name="build",
        description="Build a container image from a Containerfile in the project directory",
        params={
            "file": Param(
                GenericLocalReadableFileType(client_root),
                "Path to the Containerfile, relative to the project directory",
                required=True,
            ),
        },
        build_argv=build_argv,
    )
    run = Command(
        name="run",
        description="Run a command in a new container (removed after it exits)",
        params={
            "image": Param(
                PodmanImageNameType(),
                "Container image to run",
                required=True,
            ),
            "volume": Param(
                GenericListType(PodmanVolumeSpecType(client_root)),
                "Bind mounts as src:dst[:options]; repeat the flag per mount;"
                " src must be an existing file or dir inside the project"
                " directory",
                required=False,
            ),
            "env": Param(
                GenericListType(GenericEnvVarType()),
                "Environment variables as KEY=VALUE; repeat the flag per variable",
                required=False,
            ),
            "command": Param(
                GenericListType(GenericStringType()),
                "Command and arguments to run in the container;"
                " given as trailing words after --",
                required=False,
            ),
        },
        build_argv=run_argv,
    )
    return Group(
        "podman", "Container image management via podman", {"build": build, "run": run}
    )
