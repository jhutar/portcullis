"""Tests for the CLI client: parsing, conversion, help and main()."""

from typing import ClassVar

import pytest

from portcullis import client
from portcullis.client import (
    ClientError,
    convert_value,
    load_session,
    parse_args,
    parse_params,
)


@pytest.fixture
def session_file(tmp_path):
    """Write a valid session file and return its path."""
    from portcullis.server import write_session_file

    path = tmp_path / "session.toml"
    write_session_file(path, 8931, "sekret")
    return path


class TestLoadSession:
    def test_valid(self, session_file):
        data = load_session(session_file)
        assert data == {"port": 8931, "token": "sekret"}

    def test_missing_file(self, tmp_path):
        with pytest.raises(ClientError, match="session file not found"):
            load_session(tmp_path / "nope.toml")

    def test_missing_key(self, tmp_path):
        path = tmp_path / "bad.toml"
        path.write_text("port = 8931\n")
        with pytest.raises(ClientError, match="missing 'token'"):
            load_session(path)


class TestApiHelpers:
    def test_api_base(self):
        assert client.api_base({"port": 1234}) == "http://127.0.0.1:1234"

    def test_api_headers(self):
        assert client.api_headers({"token": "t"}) == {"Authorization": "Bearer t"}


class TestConvertValue:
    def test_string_passthrough(self):
        assert convert_value("x", {"type": "string"}, "v") == "v"

    @pytest.mark.parametrize("ptype", ["local_readable_file", "local_path"])
    def test_path_types_passthrough(self, ptype):
        assert convert_value("x", {"type": ptype}, "v") == "v"

    def test_integer(self):
        assert convert_value("n", {"type": "integer"}, "42") == 42

    def test_integer_error(self):
        with pytest.raises(ClientError, match="expected integer"):
            convert_value("n", {"type": "integer"}, "x")

    @pytest.mark.parametrize(
        "raw,expected", [("true", True), ("false", False), ("True", True)]
    )
    def test_boolean(self, raw, expected):
        assert convert_value("b", {"type": "boolean"}, raw) is expected

    def test_boolean_error(self):
        with pytest.raises(ClientError, match="true/false"):
            convert_value("b", {"type": "boolean"}, "yes")

    def test_list_elementwise(self):
        spec = {"type": "list", "item": "integer"}
        assert convert_value("l", spec, ["1", "2"]) == [1, 2]

    def test_list_item_error(self):
        spec = {"type": "list", "item": "integer"}
        with pytest.raises(ClientError, match="expected integer"):
            convert_value("l", spec, ["1", "x"])

    def test_unknown_helper_type_passthrough(self):
        """Unknown types pass through; the server validates them."""
        assert convert_value("x", {"type": "image_name"}, "v") == "v"


class TestParseParams:
    SPEC: ClassVar[dict] = {
        "image": {"type": "string"},
        "volume": {"type": "list", "item": "string"},
        "command": {"type": "list", "item": "string"},
    }

    def test_simple_pairs(self):
        params = parse_params(["--image", "fedora"], self.SPEC)
        assert params == {"image": "fedora"}

    def test_repeated_list_flag(self):
        params = parse_params(["--volume", "a:1", "--volume", "b:2"], self.SPEC)
        assert params == {"volume": ["a:1", "b:2"]}

    def test_duplicate_scalar_rejected(self):
        with pytest.raises(ClientError, match="more than once"):
            parse_params(["--image", "a", "--image", "b"], self.SPEC)

    def test_unknown_param_rejected(self):
        with pytest.raises(ClientError, match="unknown parameter"):
            parse_params(["--bogus", "x"], self.SPEC)

    def test_missing_value_rejected(self):
        with pytest.raises(ClientError, match="missing value"):
            parse_params(["--image"], self.SPEC)

    def test_positional_rejected(self):
        with pytest.raises(ClientError, match="unexpected argument"):
            parse_params(["image"], self.SPEC)

    def test_trailing_words_become_command(self):
        params = parse_params(["--image", "f", "--", "ls", "-la"], self.SPEC)
        assert params == {"image": "f", "command": ["ls", "-la"]}

    def test_trailing_words_without_command_param(self):
        spec = {"image": {"type": "string"}}
        with pytest.raises(ClientError, match="no 'command' parameter"):
            parse_params(["--image", "f", "--", "ls"], spec)


class TestParseArgs:
    def test_plain(self):
        session, help_mode, parts, rest = parse_args(["podman", "run", "--image", "f"])
        assert session == client.DEFAULT_SESSION_FILE
        assert help_mode is False
        assert parts == ["podman", "run"]
        assert rest == ["--image", "f"]

    def test_session_file(self):
        session, _, parts, rest = parse_args(
            ["--session-file", "/tmp/s", "podman", "--image", "f"]
        )
        assert str(session) == "/tmp/s"
        assert parts == ["podman"]
        assert rest == ["--image", "f"]

    def test_session_file_requires_value(self):
        with pytest.raises(ClientError, match="requires a value"):
            parse_args(["--session-file"])

    def test_help_mode(self):
        _, help_mode, parts, _ = parse_args(["podman", "run", "-h"])
        assert help_mode is True
        assert parts == ["podman", "run"]

    def test_separator_protects_client_flags(self):
        """After --, even -h belongs to the container command."""
        _session, help_mode, parts, rest = parse_args(
            ["podman", "run", "--", "cmd", "-h"]
        )
        assert help_mode is False
        assert parts == ["podman", "run"]
        assert rest == ["--", "cmd", "-h"]

    def test_path_stops_at_first_flag(self):
        _, _, parts, rest = parse_args(["podman", "--image", "f", "run"])
        assert parts == ["podman"]
        assert rest == ["--image", "f", "run"]


class TestPrintHelp:
    def test_root(self, capsys):
        doc = {"groups": [{"path": "/podman", "description": "d"}]}
        client.print_help(doc, [])
        out = capsys.readouterr().out
        assert "/podman" in out and "d" in out

    def test_group(self, capsys):
        doc = {
            "group": "podman",
            "description": "g",
            "commands": [{"path": "/podman/build", "description": "b"}],
        }
        client.print_help(doc, ["podman"])
        out = capsys.readouterr().out
        assert "/podman/build" in out

    def test_command(self, capsys):
        doc = {
            "description": "c",
            "params": {
                "file": {"type": "string", "required": True, "description": "the file"}
            },
        }
        client.print_help(doc, ["podman", "build"])
        out = capsys.readouterr().out
        assert "--file" in out and "required" in out

    def test_command_list_type(self, capsys):
        doc = {
            "description": "c",
            "params": {
                "volume": {
                    "type": "list",
                    "item": "string",
                    "required": False,
                    "description": "v",
                }
            },
        }
        client.print_help(doc, ["podman", "run"])
        assert "list<string>" in capsys.readouterr().out


class TestMain:
    def test_no_command_returns_2(self, capsys):
        assert client.main([]) == 2
        assert "no command given" in capsys.readouterr().err

    def test_root_help_without_session(self, capsys, monkeypatch):
        monkeypatch.setattr(client, "DEFAULT_SESSION_FILE", "/nonexistent")
        assert client.main(["-h"]) == 0
        captured = capsys.readouterr()
        assert "Usage" in captured.out
        assert "Command groups:" in captured.out
        assert "server unreachable" in captured.err

    def test_root_help_with_session_lists_enabled_groups(
        self, session_file, requests_mock, capsys
    ):
        requests_mock.get(
            "http://127.0.0.1:8931/",
            json={
                "groups": [
                    {"path": "/podman", "description": "d1"},
                    {"path": "/testing", "description": "d2"},
                ]
            },
        )
        rc = client.main(["--session-file", str(session_file), "-h"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "Command groups:" in captured.out
        assert "  podman               d1" in captured.out
        assert "  testing              d2" in captured.out
        assert "server unreachable" not in captured.err

    def test_root_help_server_down_falls_back(
        self, session_file, requests_mock, capsys
    ):
        import requests as requests_mod

        requests_mock.get(
            "http://127.0.0.1:8931/",
            exc=requests_mod.exceptions.ConnectionError("boom"),
        )
        rc = client.main(["--session-file", str(session_file), "-h"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "Command groups:" in captured.out
        assert "server unreachable" in captured.err
        assert "podman" in captured.out

    def test_group_help_without_session_degrades(self, capsys, monkeypatch):
        monkeypatch.setattr(client, "DEFAULT_SESSION_FILE", "/nonexistent")
        assert client.main(["podman", "-h"]) == 0
        captured = capsys.readouterr()
        assert "showing local usage" in captured.err
        assert "Usage" in captured.out

    def test_group_help_with_session(self, session_file, requests_mock, capsys):
        requests_mock.get(
            "http://127.0.0.1:8931/podman",
            json={"group": "podman", "description": "g", "commands": []},
        )
        rc = client.main(["--session-file", str(session_file), "podman", "-h"])
        assert rc == 0
        assert "Commands:" in capsys.readouterr().out

    def test_help_docs_error_returns_2(self, session_file, requests_mock, capsys):
        requests_mock.get("http://127.0.0.1:8931/podman", status_code=404, text="nope")
        assert client.main(["--session-file", str(session_file), "podman", "-h"]) == 2
        assert "404" in capsys.readouterr().err

    def test_run_streams_output_and_exits_with_code(
        self, session_file, requests_mock, capsys
    ):
        requests_mock.get(
            "http://127.0.0.1:8931/testing/echo",
            json={
                "command": "echo",
                "description": "d",
                "method": "POST",
                "params": {
                    "text": {"type": "string", "required": True, "description": "t"}
                },
            },
        )
        ndjson = (
            '{"type": "output", "data": "hello\\n"}\n\n'
            '{"type": "done", "exit_code": 3}\n'
        )
        requests_mock.post("http://127.0.0.1:8931/testing/echo", text=ndjson)
        with pytest.raises(SystemExit) as exc:
            client.main(
                [
                    "--session-file",
                    str(session_file),
                    "testing",
                    "echo",
                    "--text",
                    "hello",
                ]
            )
        assert exc.value.code == 3
        assert capsys.readouterr().out == "hello\n"

    def test_run_missing_required_param(self, session_file, requests_mock, capsys):
        requests_mock.get(
            "http://127.0.0.1:8931/testing/echo",
            json={
                "command": "echo",
                "description": "d",
                "method": "POST",
                "params": {
                    "text": {"type": "string", "required": True, "description": "t"}
                },
            },
        )
        rc = client.main(["--session-file", str(session_file), "testing", "echo"])
        assert rc == 2
        assert "missing required parameter" in capsys.readouterr().err

    def test_run_server_error_event(self, session_file, requests_mock, capsys):
        requests_mock.get(
            "http://127.0.0.1:8931/testing/echo",
            json={
                "command": "echo",
                "description": "d",
                "method": "POST",
                "params": {
                    "text": {"type": "string", "required": True, "description": "t"}
                },
            },
        )
        requests_mock.post(
            "http://127.0.0.1:8931/testing/echo",
            status_code=400,
            text='{"type": "error", "code": "invalid_param", "message": "bad"}\n',
        )
        rc = client.main(
            ["--session-file", str(session_file), "testing", "echo", "--text", "x"]
        )
        assert rc == 2
        assert "400" in capsys.readouterr().err

    def test_run_error_event_raises(self, session_file, requests_mock, capsys):
        requests_mock.get(
            "http://127.0.0.1:8931/testing/echo",
            json={
                "command": "echo",
                "description": "d",
                "method": "POST",
                "params": {
                    "text": {"type": "string", "required": True, "description": "t"}
                },
            },
        )
        requests_mock.post(
            "http://127.0.0.1:8931/testing/echo",
            status_code=200,
            text='{"type": "error", "code": "invalid_param", "message": "bad"}\n',
        )
        rc = client.main(
            ["--session-file", str(session_file), "testing", "echo", "--text", "x"]
        )
        assert rc == 2
        assert "invalid_param: bad" in capsys.readouterr().err

    def test_connection_error_returns_2(self, session_file, requests_mock, capsys):
        import requests

        requests_mock.get(
            "http://127.0.0.1:8931/testing/echo", exc=requests.ConnectionError
        )
        rc = client.main(
            ["--session-file", str(session_file), "testing", "echo", "--text", "x"]
        )
        assert rc == 2
        assert "cannot reach the server" in capsys.readouterr().err
