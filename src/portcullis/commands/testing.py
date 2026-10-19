"""The testing command group: safe commands for tests and smoke checks.

These commands run real, universally-present binaries (echo, sh, cat)
with strictly validated parameters, so they are safe to enable anywhere
and give tests and smoke checks a stable target that does not depend on
podman being installed.
"""

from ..params import (
    GenericIntegerType,
    GenericLocalReadableFileType,
    GenericStringType,
)
from .base import Command, Group, Param


def echo_argv(args):
    """Assemble the echo argv from validated params."""
    return ["echo", args["text"]]


def fail_argv(args):
    """Assemble the sh argv exiting with the validated numeric exit code.

    The code is a validated int, so splicing it into the sh -c string
    cannot inject shell commands.
    """
    return ["sh", "-c", f"exit {args['code']}"]


def readfile_argv(args):
    """Assemble the cat argv from the validated file param."""
    return ["cat", str(args["file"])]


def make_group(client_root):
    """Build the testing command group with client-root-aware file params."""
    echo = Command(
        name="echo",
        description="Echo the text parameter back (no shell involved)",
        params={
            "text": Param(
                GenericStringType(),
                "Text to echo back",
                required=True,
            ),
        },
        build_argv=echo_argv,
    )
    fail = Command(
        name="fail",
        description="Exit with the given numeric exit code",
        params={
            "code": Param(
                GenericIntegerType(),
                "Exit code to exit with",
                required=True,
            ),
        },
        build_argv=fail_argv,
    )
    readfile = Command(
        name="readfile",
        description="Print an existing file inside the project directory",
        params={
            "file": Param(
                GenericLocalReadableFileType(client_root),
                "Path to the file, relative to the project directory",
                required=True,
            ),
        },
        build_argv=readfile_argv,
    )
    return Group(
        "testing",
        "Safe commands for tests and smoke checks",
        {"echo": echo, "fail": fail, "readfile": readfile},
    )
