"""Strict parameter types with optional extra validation."""

from pathlib import Path


class ParamError(ValueError):
    """Raised when a parameter value fails validation."""


class ParamType:
    """Base class for parameter types usable in command definitions."""

    name = "string"

    def describe(self):
        """Return the JSON-serializable description of this type for GET docs."""
        return {"type": self.name}

    def validate(self, value):
        """Return the cleaned value or raise ParamError. Strict: no coercion."""
        raise NotImplementedError


class StringType(ParamType):
    """Plain JSON string."""

    name = "string"

    def validate(self, value):
        """Accept only str instances."""
        if not isinstance(value, str):
            raise ParamError(f"expected string, got {type(value).__name__}")
        return value


class IntegerType(ParamType):
    """Plain JSON integer. Booleans are rejected (bool is a subclass of int)."""

    name = "integer"

    def validate(self, value):
        """Accept only real ints, not bools."""
        if isinstance(value, bool) or not isinstance(value, int):
            raise ParamError(f"expected integer, got {type(value).__name__}")
        return value


class BooleanType(ParamType):
    """Plain JSON boolean."""

    name = "boolean"

    def validate(self, value):
        """Accept only bool instances."""
        if not isinstance(value, bool):
            raise ParamError(f"expected boolean, got {type(value).__name__}")
        return value


class LocalReadableFileType(ParamType):
    """String path that must resolve to an existing file inside the server cwd.

    Absolute paths coming from the client are translated first: paths under
    the client-side project root are remapped into the server-side project
    directory. After translation the resolved path must stay inside the
    server cwd (traversal and symlink escapes are rejected).
    """

    name = "local_readable_file"

    def __init__(self, client_root=None):
        """Store the client-side project root used for path translation."""
        self.client_root = Path(client_root) if client_root else None

    def validate(self, value):
        """Translate, resolve and containment-check the given path."""
        if not isinstance(value, str):
            raise ParamError(f"expected string path, got {type(value).__name__}")
        path = self._translate(value)
        resolved = path.resolve()
        root = Path.cwd().resolve()
        if not resolved.is_relative_to(root):
            raise ParamError(f"{value!r} escapes the project directory")
        if not resolved.is_file():
            raise ParamError(f"{value!r} is not an existing file")
        return resolved

    def _translate(self, value):
        """Rewrite client-absolute paths into server-side project paths."""
        path = Path(value)
        if not path.is_absolute():
            return path
        if self.client_root is not None:
            try:
                return Path.cwd() / path.relative_to(self.client_root)
            except ValueError:
                pass
        # Not under the client root: maybe already a server-side path.
        # The containment check in validate() decides if it is acceptable.
        return path
