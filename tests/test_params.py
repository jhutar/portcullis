"""Tests for the strict parameter types."""

import pytest

from portcullis.params import (
    GenericBooleanType,
    GenericEnvVarType,
    GenericIntegerType,
    GenericListType,
    GenericLocalPathType,
    GenericLocalReadableFileType,
    GenericStringType,
    ParamError,
    PodmanImageNameType,
    PodmanVolumeSpecType,
)


class TestParamBase:
    def test_validate_not_implemented(self):
        from portcullis.params import ParamType

        with pytest.raises(NotImplementedError):
            ParamType().validate("x")

    def test_describe_default(self):
        from portcullis.params import ParamType

        assert ParamType().describe() == {"type": "string"}


class TestGenericStringType:
    def test_accepts_str(self):
        assert GenericStringType().validate("x") == "x"

    def test_rejects_non_str(self):
        with pytest.raises(ParamError):
            GenericStringType().validate(5)


class TestGenericIntegerType:
    def test_accepts_int(self):
        assert GenericIntegerType().validate(5) == 5

    @pytest.mark.parametrize("value", [True, False, "5", 5.0, None])
    def test_rejects_non_int(self, value):
        with pytest.raises(ParamError):
            GenericIntegerType().validate(value)


class TestGenericBooleanType:
    def test_accepts_bool(self):
        assert GenericBooleanType().validate(True) is True

    @pytest.mark.parametrize("value", ["true", 1, 0, None])
    def test_rejects_non_bool(self, value):
        with pytest.raises(ParamError):
            GenericBooleanType().validate(value)


class TestLocalPaths:
    def make_file(self, project_dir, name="f.txt", content="data"):
        """Create a file inside the project directory."""
        p = project_dir / name
        p.write_text(content)
        return p

    def test_readable_file_accepts_existing_relative(self, project_dir):
        self.make_file(project_dir)
        resolved = GenericLocalReadableFileType().validate("f.txt")
        assert resolved == project_dir / "f.txt"

    def test_readable_file_rejects_missing(self, project_dir):
        with pytest.raises(ParamError, match="not an existing file"):
            GenericLocalReadableFileType().validate("nope.txt")

    def test_readable_file_rejects_directory(self, project_dir):
        (project_dir / "sub").mkdir()
        with pytest.raises(ParamError, match="not an existing file"):
            GenericLocalReadableFileType().validate("sub")

    def test_local_path_accepts_directory(self, project_dir):
        (project_dir / "sub").mkdir()
        resolved = GenericLocalPathType().validate("sub")
        assert resolved == project_dir / "sub"

    @pytest.mark.parametrize("value", [5, None, ["f.txt"]])
    def test_rejects_non_str(self, value, project_dir):
        self.make_file(project_dir)
        with pytest.raises(ParamError, match="expected string path"):
            GenericLocalReadableFileType().validate(value)
        with pytest.raises(ParamError, match="expected string path"):
            GenericLocalPathType().validate(value)

    def test_rejects_traversal_escape(self, project_dir, tmp_path):
        with pytest.raises(ParamError, match="escapes the project directory"):
            GenericLocalReadableFileType().validate("../outside.txt")

    def test_rejects_absolute_outside_root(self, project_dir):
        with pytest.raises(ParamError, match="escapes the project directory"):
            GenericLocalReadableFileType().validate("/etc/passwd")

    def test_rejects_symlink_escape(self, project_dir, tmp_path):
        """Symlink inside cwd pointing outside cwd must be rejected."""
        outside = tmp_path / "outside.txt"
        outside.write_text("secret")
        (project_dir / "link").symlink_to(outside)
        with pytest.raises(ParamError):
            GenericLocalReadableFileType().validate("link")

    def test_accepts_symlink_inside_root(self, project_dir):
        """Symlink pointing inside cwd is fine."""
        self.make_file(project_dir, "real.txt")
        (project_dir / "link").symlink_to(project_dir / "real.txt")
        resolved = GenericLocalReadableFileType().validate("link")
        assert resolved == project_dir / "real.txt"

    def test_client_root_translation(self, project_dir, client_root):
        """Absolute client-side path under client_root maps into cwd."""
        from pathlib import Path

        self.make_file(project_dir)
        value = str(Path(client_root) / "f.txt")
        resolved = GenericLocalReadableFileType(client_root).validate(value)
        assert resolved == project_dir / "f.txt"

    def test_absolute_not_under_client_root_rejected(self, project_dir, client_root):
        with pytest.raises(ParamError, match="escapes"):
            GenericLocalReadableFileType(client_root).validate("/etc/passwd")


class TestGenericEnvVarType:
    @pytest.mark.parametrize("value", ["FOO=bar", "A_1=x", "k=v=w"])
    def test_accepts_key_value(self, value):
        assert GenericEnvVarType().validate(value) == value

    @pytest.mark.parametrize(
        "value",
        [
            "FOO",  # no =
            "=bar",  # empty key
            "1FOO=bar",  # key starts with digit
            "FOO=",  # empty value
            "FOO bar=baz",  # space in key
            5,  # not a str
        ],
    )
    def test_rejects_bad(self, value):
        with pytest.raises(ParamError):
            GenericEnvVarType().validate(value)


class TestPodmanImageNameType:
    @pytest.mark.parametrize(
        "value",
        [
            "quay.io/org/image:41",
            "fedora:latest",
            "image@sha256:abc123",
            "org/img",
        ],
    )
    def test_accepts_valid(self, value):
        assert PodmanImageNameType().validate(value) == value

    @pytest.mark.parametrize(
        "value",
        [
            "-flag",  # could be mistaken for a podman flag
            "--privileged",
            "foo bar",  # space
            "",  # empty
            "foo;rm",  # semicolon
            "foo|bar",
            5,  # not a str
        ],
    )
    def test_rejects_invalid(self, value):
        with pytest.raises(ParamError):
            PodmanImageNameType().validate(value)


class TestPodmanVolumeSpecType:
    def make_file(self, project_dir, name="src"):
        p = project_dir / name
        p.write_text("x")
        return p

    def test_accepts_two_parts(self, project_dir):
        self.make_file(project_dir)
        assert PodmanVolumeSpecType().validate("src:dst") == "src:dst"

    def test_accepts_three_parts_with_options(self, project_dir):
        self.make_file(project_dir)
        assert PodmanVolumeSpecType().validate("src:dst:z,ro") == "src:dst:z,ro"

    @pytest.mark.parametrize(
        "value",
        [
            "justone",  # 1 part
            "a:b:c:d",  # 4 parts
            "missing:dst",  # nonexistent src
            "myvol:/dst",  # named volume: src not a local path
            5,  # not a str
        ],
    )
    def test_rejects_bad(self, value, project_dir):
        with pytest.raises(ParamError):
            PodmanVolumeSpecType().validate(value)

    def test_rejects_src_escaping_root(self, project_dir):
        with pytest.raises(ParamError):
            PodmanVolumeSpecType().validate("../outside:dst")


class TestGenericListType:
    def test_describe_includes_item(self):
        doc = GenericListType(GenericIntegerType()).describe()
        assert doc == {"type": "list", "item": "integer"}

    def test_validates_each_item(self):
        assert GenericListType(GenericIntegerType()).validate([1, 2]) == [1, 2]

    def test_rejects_non_list(self):
        with pytest.raises(ParamError, match="expected list"):
            GenericListType(GenericIntegerType()).validate(5)

    def test_rejects_empty_list(self):
        with pytest.raises(ParamError, match="empty list"):
            GenericListType(GenericIntegerType()).validate([])

    def test_item_error_carries_index(self):
        with pytest.raises(ParamError, match="item 1"):
            GenericListType(GenericIntegerType()).validate([1, "x"])
