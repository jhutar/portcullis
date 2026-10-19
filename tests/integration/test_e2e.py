"""End-to-end tests: real HTTP socket, real subprocesses, real client."""

import threading

import pytest
from werkzeug.serving import make_server

from portcullis import client
from portcullis.server import create_app, write_session_file

pytestmark = pytest.mark.integration

TOKEN = "e2e-token"

INJECTION_PAYLOAD = 'foo"; rm /etc/passwd; "bar'


@pytest.fixture
def server(project_dir, tmp_path):
    """Start the real Flask app on an ephemeral port in a daemon thread."""
    cfg = {
        "endpoints": {"testing": True},
        "client": {"root_base": str(tmp_path / "clienthome")},
    }
    app = create_app(cfg, TOKEN, str(tmp_path / "clienthome" / project_dir.name))
    srv = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()


@pytest.fixture
def session_file(server, tmp_path):
    """Write a valid session file pointing at the running server."""
    path = tmp_path / "client-session.toml"
    write_session_file(path, srv_port(server), TOKEN)
    return path


def srv_port(server):
    """Return the ephemeral port the test server listens on."""
    return server.socket.getsockname()[1]


def run_client(session_file, *argv):
    """Run the real client main(); return its exit status.

    Successful command runs exit via sys.exit(exit_code), while usage
    errors return 2; both are normalized to an int exit status.
    """
    try:
        return client.main(["--session-file", str(session_file), *argv])
    except SystemExit as exc:
        return exc.code


def test_echo_roundtrip(session_file, capsys):
    assert run_client(session_file, "testing", "echo", "--text", "hello") == 0
    assert capsys.readouterr().out == "hello\n"


def test_command_line_injection_is_inert(session_file, capsys):
    """A shell injection payload must be echoed back verbatim.

    The server builds argv lists (no shell), so the payload can only
    ever reach echo as a single literal argument.
    """
    code = run_client(session_file, "testing", "echo", "--text", INJECTION_PAYLOAD)
    assert code == 0
    assert capsys.readouterr().out == INJECTION_PAYLOAD + "\n"


def test_exit_code_propagates_to_client(session_file):
    assert run_client(session_file, "testing", "fail", "--code", "7") == 7


def test_readfile_with_client_root_translation(
    server, session_file, project_dir, tmp_path, capsys
):
    """Client-side absolute path is translated to the server project dir."""
    (project_dir / "hello.txt").write_text("translated content\n")
    client_path = tmp_path / "clienthome" / project_dir.name / "hello.txt"
    code = run_client(session_file, "testing", "readfile", "--file", str(client_path))
    assert code == 0
    assert capsys.readouterr().out == "translated content\n"


def test_readfile_escape_rejected(session_file, capsys):
    code = run_client(session_file, "testing", "readfile", "--file", "/etc/passwd")
    assert code == 2
    assert "invalid_param" in capsys.readouterr().err


def test_wrong_token_rejected(server, tmp_path, capsys):
    path = tmp_path / "bad-session.toml"
    write_session_file(path, srv_port(server), "wrong-token")
    code = run_client(path, "testing", "echo", "--text", "x")
    assert code == 2
    assert "401" in capsys.readouterr().err
