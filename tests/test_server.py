"""Tests for the Flask server: auth, deny-by-default, validation, streaming."""

import json

import pytest

from portcullis.server import create_app, write_session_file

TOKEN = "test-token"


def ndjson_lines(resp):
    """Parse an NDJSON response body into a list of event dicts."""
    return [json.loads(line) for line in resp.text.splitlines() if line]


class TestAuth:
    def test_no_token_401(self, tclient):
        c = tclient.application.test_client()
        resp = c.get("/")
        assert resp.status_code == 401
        assert json.loads(resp.data)["type"] == "error"
        assert json.loads(resp.data)["code"] == "unauthorized"

    def test_wrong_token_401(self, tclient):
        c = tclient.application.test_client()
        resp = c.get("/", headers={"Authorization": "Bearer wrong"})
        assert resp.status_code == 401

    @pytest.mark.parametrize(
        "method,path",
        [
            ("GET", "/"),
            ("GET", "/podman"),
            ("GET", "/podman/build"),
            ("POST", "/testing/echo"),
        ],
    )
    def test_auth_covers_all_routes(self, app, method, path):
        c = app.test_client()
        kwargs = {"json": {}} if method == "POST" else {}
        resp = c.open(path, method=method, **kwargs)
        assert resp.status_code == 401


class TestDenyByDefault:
    def test_unmentioned_group_disabled_with_warning(
        self, project_dir, client_root, capsys
    ):
        cfg = {"endpoints": {"podman": True}}
        app = create_app(cfg, TOKEN, client_root)
        assert "testing" in capsys.readouterr().err
        c = app.test_client()
        c.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {TOKEN}"
        assert c.get("/testing").status_code == 404

    def test_false_group_disabled_without_warning(
        self, project_dir, client_root, capsys
    ):
        cfg = {"endpoints": {"podman": True, "testing": False}}
        app = create_app(cfg, TOKEN, client_root)
        assert "warning" not in capsys.readouterr().err
        c = app.test_client()
        c.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {TOKEN}"
        assert c.get("/testing").status_code == 404

    def test_no_groups_configured(self, project_dir, client_root):
        app = create_app({}, TOKEN, client_root)
        c = app.test_client()
        c.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {TOKEN}"
        assert c.get("/").json == {"groups": []}
        assert c.get("/podman").status_code == 404


class TestDocsRoutes:
    def test_root_lists_groups(self, tclient):
        resp = tclient.get("/")
        assert resp.status_code == 200
        paths = [g["path"] for g in json.loads(resp.data)["groups"]]
        assert paths == ["/podman", "/testing"]

    def test_group_docs(self, tclient):
        resp = tclient.get("/podman")
        assert resp.status_code == 200
        assert json.loads(resp.data)["group"] == "podman"
        cmd_paths = [c["path"] for c in json.loads(resp.data)["commands"]]
        assert "/podman/build" in cmd_paths

    def test_command_docs(self, tclient):
        resp = tclient.get("/podman/build")
        assert resp.status_code == 200
        assert json.loads(resp.data)["path"] == "/podman/build"
        assert json.loads(resp.data)["method"] == "POST"
        assert "file" in json.loads(resp.data)["params"]

    def test_unknown_group_404(self, tclient):
        resp = tclient.get("/bogus")
        assert resp.status_code == 404
        assert json.loads(resp.data)["code"] == "not_found"

    def test_unknown_command_404(self, tclient):
        assert tclient.get("/podman/bogus").status_code == 404

    def test_unknown_command_in_unknown_group_404(self, tclient):
        assert tclient.get("/bogus/bogus").status_code == 404


class TestRunCommand:
    def post(self, tclient, path, payload):
        return tclient.post(path, json=payload)

    def test_echo_streams_output_and_done(self, tclient):
        resp = self.post(tclient, "/testing/echo", {"text": "hello"})
        assert resp.status_code == 200
        assert resp.mimetype == "application/x-ndjson"
        events = ndjson_lines(resp)
        assert events[0] == {"type": "output", "data": "hello\n"}
        assert events[-1] == {"type": "done", "exit_code": 0}

    def test_fail_propagates_exit_code(self, tclient):
        resp = self.post(tclient, "/testing/fail", {"code": 7})
        events = ndjson_lines(resp)
        assert events[-1] == {"type": "done", "exit_code": 7}

    def test_readfile_serves_project_file(self, tclient, project_dir):
        (project_dir / "f.txt").write_text("file content\n")
        resp = self.post(tclient, "/testing/readfile", {"file": "f.txt"})
        events = ndjson_lines(resp)
        assert events[0]["data"] == "file content\n"

    def test_invalid_param_400(self, tclient):
        resp = self.post(tclient, "/testing/echo", {"text": 5})
        assert resp.status_code == 400
        assert json.loads(resp.data)["code"] == "invalid_param"

    def test_missing_required_400(self, tclient):
        resp = self.post(tclient, "/testing/echo", {})
        assert resp.status_code == 400
        assert json.loads(resp.data)["code"] == "invalid_param"

    def test_unknown_param_400(self, tclient):
        resp = self.post(tclient, "/testing/echo", {"text": "x", "bogus": 1})
        assert resp.status_code == 400

    def test_non_json_body_400(self, tclient):
        resp = tclient.post("/testing/echo", data="not json", content_type="text/plain")
        assert resp.status_code == 400
        assert json.loads(resp.data)["code"] == "invalid_param"

    def test_path_escape_rejected(self, tclient):
        resp = self.post(tclient, "/testing/readfile", {"file": "/etc/passwd"})
        assert resp.status_code == 400
        assert json.loads(resp.data)["code"] == "invalid_param"

    def test_unknown_command_post_404(self, tclient):
        assert self.post(tclient, "/testing/bogus", {}).status_code == 404

    def test_binary_not_found(self, tclient, monkeypatch):
        monkeypatch.setattr("portcullis.server.shutil.which", lambda name: None)
        resp = self.post(tclient, "/testing/echo", {"text": "x"})
        assert resp.status_code == 400
        assert json.loads(resp.data)["code"] == "binary_not_found"


class TestSessionFile:
    def test_write_session_file(self, tmp_path):
        path = tmp_path / "session.toml"
        write_session_file(path, 8931, "sekret")
        assert path.read_text() == 'port = 8931\ntoken = "sekret"\n'
        assert (path.stat().st_mode & 0o777) == 0o600


class TestServerMain:
    def test_main_writes_session_file_and_configures_app(
        self, project_dir, tmp_path, monkeypatch, capsys
    ):
        """main() loads config, writes the session file and starts the app."""
        import flask

        from portcullis import server

        monkeypatch.setattr(flask.Flask, "run", lambda self, **kw: None)
        cfg = tmp_path / "cfg.toml"
        cfg.write_text("[endpoints]\ntesting = true\n")
        session = tmp_path / "session.toml"
        server.main(
            ["--config", str(cfg), "--port", "8931", "--session-file", str(session)]
        )
        out = capsys.readouterr().out
        assert "listening on http://127.0.0.1:8931" in out
        assert "enabled groups: testing" in out
        assert "client root:" in out
        assert session.exists()

    def test_main_help_exits_zero(self, capsys):
        from portcullis import server

        with pytest.raises(SystemExit) as exc:
            server.main(["--help"])
        assert exc.value.code == 0
        assert "portcullis-server" in capsys.readouterr().out
