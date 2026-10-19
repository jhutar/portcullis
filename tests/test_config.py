"""Tests for config loading and merging."""

from portcullis import config


def test_deep_merge_nested_override():
    """Override wins key-by-key, nested dicts merge recursively."""
    base = {"a": 1, "endpoints": {"podman": True, "other": False}, "keep": {"x": 1}}
    override = {"b": 2, "endpoints": {"testing": True}, "keep": {"y": 2}}
    merged = config.deep_merge(base, override)
    assert merged == {
        "a": 1,
        "b": 2,
        "keep": {"x": 1, "y": 2},
        "endpoints": {"podman": True, "other": False, "testing": True},
    }
    # base is not mutated
    assert base == {
        "a": 1,
        "endpoints": {"podman": True, "other": False},
        "keep": {"x": 1},
    }


def test_deep_merge_scalar_replaces_dict():
    """A scalar override replaces a dict value wholesale."""
    merged = config.deep_merge({"a": {"x": 1}}, {"a": 5})
    assert merged == {"a": 5}


def test_load_config_merges_user_and_local(tmp_path):
    """Local config wins over user config; both are merged."""
    user = tmp_path / "user.toml"
    user.write_text("[endpoints]\npodman = true\n")
    local = tmp_path / "local.toml"
    local.write_text('[endpoints]\ntesting = true\n[client]\nroot_base = "/tmp/base"\n')
    cfg = config.load_config(user_path=user, local_path=local)
    assert cfg == {
        "endpoints": {"podman": True, "testing": True},
        "client": {"root_base": "/tmp/base"},
    }


def test_load_config_missing_files(tmp_path):
    """Missing config files are skipped; result is an empty dict."""
    assert (
        config.load_config(
            user_path=tmp_path / "nope.toml", local_path=tmp_path / "nada.toml"
        )
        == {}
    )


def test_load_config_local_overrides_user(tmp_path):
    """Same key in both files: local wins."""
    user = tmp_path / "user.toml"
    user.write_text('[client]\nroot_base = "/a"\n')
    local = tmp_path / "local.toml"
    local.write_text('[client]\nroot_base = "/b"\n')
    cfg = config.load_config(user_path=user, local_path=local)
    assert cfg["client"]["root_base"] == "/b"


def test_compute_client_root_configured(project_dir):
    """Configured root_base + cwd basename."""
    cfg = {"client": {"root_base": "/tmp/clienthome"}}
    assert config.compute_client_root(cfg) == f"/tmp/clienthome/{project_dir.name}"


def test_compute_client_root_default(project_dir):
    """Without config, home directory is the base."""
    from pathlib import Path

    assert config.compute_client_root({}) == f"{Path.home()}/{project_dir.name}"
