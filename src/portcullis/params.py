"""Strict parameter types with optional extra validation.

Guidelines for parameter types (codified for future additions):

* Every parameter type lives in this module. Command modules only
  combine types; they never define validation logic of their own.
* One class per concept, named ``<Domain><Concept>Type``:
  * ``Generic...`` prefix: the type is shared and usable by any
    command group.
  * A group prefix (e.g. ``Podman...``): the type is specific to one
    command group. Rename to ``Generic...`` the moment another group
    reuses it; the prefix describes current reuse, not a prediction.
* The ``name`` class attribute is the docs/API identifier: snake_case,
  describing the value, not the class taxonomy.
* Logic shared by several types goes into a module-level helper
  function; classes compose those helpers instead of copying code.
* Lists of values are always expressed with ``GenericListType``, never
  with bespoke per-type list classes.
* Constructors take context (e.g. ``client_root``) as the first
  argument; types otherwise stay stateless.
* Every type carries a docstring describing exactly what it checks.
"""

import re
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


class GenericStringType(ParamType):
    """Plain JSON string; accepts only str instances."""

    name = "string"

    def validate(self, value):
        """Accept only str instances."""
        if not isinstance(value, str):
            raise ParamError(f"expected string, got {type(value).__name__}")
        return value


class GenericIntegerType(ParamType):
    """Plain JSON integer; booleans are rejected (bool is a subclass of int)."""

    name = "integer"

    def validate(self, value):
        """Accept only real ints, not bools."""
        if isinstance(value, bool) or not isinstance(value, int):
            raise ParamError(f"expected integer, got {type(value).__name__}")
        return value


class GenericBooleanType(ParamType):
    """Plain JSON boolean; accepts only bool instances."""

    name = "boolean"

    def validate(self, value):
        """Accept only bool instances."""
        if not isinstance(value, bool):
            raise ParamError(f"expected boolean, got {type(value).__name__}")
        return value


def resolve_local_path(value, client_root=None):
    """Translate, resolve and containment-check one path for a param value.

    Client-absolute paths under the client-side project root are remapped
    into the server-side project directory. The resolved path must stay
    inside the server cwd (traversal and symlink escapes are rejected).
    Returns the resolved Path or raises ParamError.
    """
    path = Path(value)
    if path.is_absolute() and client_root is not None:
        try:
            path = Path.cwd() / path.relative_to(client_root)
        except ValueError:
            pass
    # Not under the client root: maybe already a server-side path.
    # The containment check below decides if it is acceptable.
    resolved = path.resolve()
    root = Path.cwd().resolve()
    if not resolved.is_relative_to(root):
        raise ParamError(f"{value!r} escapes the project directory")
    return resolved


class GenericLocalReadableFileType(ParamType):
    """String path that must resolve to an existing file inside the server cwd.

    Absolute paths coming from the client are translated first: paths under
    the client-side project root are remapped into the server-side project
    directory.
    """

    name = "local_readable_file"

    def __init__(self, client_root=None):
        """Store the client-side project root used for path translation."""
        self.client_root = Path(client_root) if client_root else None

    def validate(self, value):
        """Require a str path resolving to an existing file inside cwd."""
        if not isinstance(value, str):
            raise ParamError(f"expected string path, got {type(value).__name__}")
        resolved = resolve_local_path(value, self.client_root)
        if not resolved.is_file():
            raise ParamError(f"{value!r} is not an existing file")
        return resolved


class GenericLocalPathType(ParamType):
    """String path that must resolve to an existing file or dir inside the server cwd.

    Absolute paths coming from the client are translated first: paths under
    the client-side project root are remapped into the server-side project
    directory.
    """

    name = "local_path"

    def __init__(self, client_root=None):
        """Store the client-side project root used for path translation."""
        self.client_root = Path(client_root) if client_root else None

    def validate(self, value):
        """Require a str path resolving to an existing file or dir inside cwd."""
        if not isinstance(value, str):
            raise ParamError(f"expected string path, got {type(value).__name__}")
        resolved = resolve_local_path(value, self.client_root)
        if not (resolved.is_file() or resolved.is_dir()):
            raise ParamError(f"{value!r} is not an existing file or directory")
        return resolved


class GenericEnvVarType(ParamType):
    """Environment variable assignment string in ``KEY=VALUE`` form.

    KEY must match ``[A-Za-z_][A-Za-z0-9_]*``; VALUE must be non-empty.
    """

    name = "env_var"

    _RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.+")

    def validate(self, value):
        """Require a str matching the KEY=VALUE pattern."""
        if not isinstance(value, str):
            raise ParamError(f"expected string, got {type(value).__name__}")
        if not self._RE.fullmatch(value):
            raise ParamError(f"{value!r} is not a KEY=VALUE environment assignment")
        return value


class GenericListType(ParamType):
    """JSON list of values, each validated by the wrapped item type.

    The list must be a real JSON list and must not be empty; empty lists
    are expressed by omitting the (optional) parameter entirely.
    """

    name = "list"

    def __init__(self, item_type):
        """Store the param type instance applied to each list element."""
        self.item_type = item_type

    def describe(self):
        """Return the type description including the item type name."""
        doc = super().describe()
        doc["item"] = self.item_type.name
        return doc

    def validate(self, value):
        """Require a non-empty list; validate and return each cleaned item."""
        if not isinstance(value, list):
            raise ParamError(f"expected list, got {type(value).__name__}")
        if not value:
            raise ParamError("empty list is not allowed; omit the parameter instead")
        cleaned = []
        for index, item in enumerate(value):
            try:
                cleaned.append(self.item_type.validate(item))
            except ParamError as exc:
                raise ParamError(f"item {index}: {exc}") from exc
        return cleaned


class PodmanImageNameType(ParamType):
    """Container image reference such as ``quay.io/org/image:tag``.

    Must start with an alphanumeric character and may then contain
    alphanumerics, dots, colons, at-signs, slashes, underscores and
    dashes. The leading-character rule also blocks values that could
    be mistaken for podman flags (argv injection).
    """

    name = "image_name"

    _RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@/-]*")

    def validate(self, value):
        """Require a str matching the image name pattern."""
        if not isinstance(value, str):
            raise ParamError(f"expected string, got {type(value).__name__}")
        if not self._RE.fullmatch(value):
            raise ParamError(f"{value!r} is not a valid image name")
        return value


class PodmanVolumeSpecType(ParamType):
    """Podman bind-mount spec ``src:dst[:options]`` with a local source.

    Splits on ``:`` into 2 or 3 parts; ``src`` (part 0) must resolve to an
    existing file or directory inside the server cwd (with client-root
    path translation). Destination and options are passed through
    untouched: they live inside the container and carry no host risk.
    Named volumes and tmpfs mounts are rejected implicitly because their
    source is not a local path.
    """

    name = "volume_spec"

    def __init__(self, client_root=None):
        """Store the client-side project root used for path translation."""
        self.client_root = Path(client_root) if client_root else None

    def validate(self, value):
        """Require a str in src:dst[:options] form with a contained src."""
        if not isinstance(value, str):
            raise ParamError(f"expected string, got {type(value).__name__}")
        parts = value.split(":")
        if len(parts) not in (2, 3):
            raise ParamError(f"{value!r} is not a src:dst[:options] volume spec")
        GenericLocalPathType(self.client_root).validate(parts[0])
        return value
