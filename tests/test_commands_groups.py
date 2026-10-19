"""Tests for the podman and testing command groups."""

from portcullis.commands import podman, testing
from portcullis.commands.base import Group


class TestPodmanGroup:
    def test_build_argv(self):
        argv = podman.build_argv({"file": "Containerfile"})
        assert argv == ["podman", "build", "-f", "Containerfile", "."]

    def test_run_argv_minimal(self):
        argv = podman.run_argv({"image": "fedora:41"})
        assert argv == ["podman", "run", "--rm", "-it", "fedora:41"]

    def test_run_argv_full(self):
        """Volumes and env come before the image; command words after it."""
        argv = podman.run_argv(
            {
                "image": "fedora:41",
                "volume": ["./src:/src:z,ro"],
                "env": ["FOO=bar"],
                "command": ["ls", "-la", "/src"],
            }
        )
        assert argv == [
            "podman",
            "run",
            "--rm",
            "-it",
            "-v",
            "./src:/src:z,ro",
            "-e",
            "FOO=bar",
            "fedora:41",
            "ls",
            "-la",
            "/src",
        ]

    def test_command_words_can_look_like_podman_flags(self):
        """Words after the image can never be parsed as podman flags."""
        argv = podman.run_argv(
            {
                "image": "fedora:41",
                "command": ["--privileged", "--net=host"],
            }
        )
        assert argv[-2:] == ["--privileged", "--net=host"]
        assert argv.index("fedora:41") < len(argv) - 2

    def test_make_group_structure(self):
        group = podman.make_group("/client/root")
        assert isinstance(group, Group)
        assert group.name == "podman"
        assert set(group.commands) == {"build", "run"}
        assert group.commands["build"].params["file"].required
        assert not group.commands["run"].params["volume"].required
        assert not group.commands["run"].params["command"].required
        # client-root-aware param types get the client root
        file_type = group.commands["build"].params["file"].ptype
        assert str(file_type.client_root) == "/client/root"


class TestTestingGroup:
    def test_echo_argv(self):
        assert testing.echo_argv({"text": "hello"}) == ["echo", "hello"]

    def test_fail_argv(self):
        assert testing.fail_argv({"code": 7}) == ["sh", "-c", "exit 7"]

    def test_readfile_argv(self):
        from pathlib import Path

        argv = testing.readfile_argv({"file": Path("/proj/f.txt")})
        assert argv == ["cat", "/proj/f.txt"]

    def test_make_group_structure(self):
        group = testing.make_group(None)
        assert group.name == "testing"
        assert set(group.commands) == {"echo", "fail", "readfile"}
        for cmd in group.commands.values():
            assert cmd.params, f"{cmd.name} has no params"
