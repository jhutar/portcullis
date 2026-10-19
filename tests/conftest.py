"""Shared fixtures for portcullis tests."""

import pytest

from portcullis.server import create_app

TOKEN = "test-token"


@pytest.fixture
def project_dir(tmp_path, monkeypatch):
    """Create an empty project directory and make it the server cwd."""
    d = tmp_path / "proj"
    d.mkdir()
    monkeypatch.chdir(d)
    return d


@pytest.fixture
def client_root(tmp_path, project_dir):
    """Return the client-side equivalent root of the project directory."""
    root = tmp_path / "clienthome" / project_dir.name
    return str(root)


@pytest.fixture
def app(project_dir, client_root):
    """Flask test app with podman and testing groups enabled."""
    cfg = {"endpoints": {"podman": True, "testing": True}}
    return create_app(cfg, TOKEN, client_root)


@pytest.fixture
def tclient(app):
    """Flask test client with valid auth headers."""
    c = app.test_client()
    c.environ_base["HTTP_AUTHORIZATION"] = f"Bearer {TOKEN}"
    return c
