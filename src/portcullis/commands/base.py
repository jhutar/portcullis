"""Core building blocks for command groups: Param, Command, Group."""

from ..params import ParamError


class Param:
    """Declarative spec of one command parameter."""

    def __init__(self, ptype, description, required=True):
        """Store the param type instance, human description and required flag."""
        self.ptype = ptype
        self.description = description
        self.required = required

    def describe(self):
        """Return the JSON-serializable description for GET docs."""
        doc = {"type": self.ptype.name, "required": self.required,
               "description": self.description}
        return doc


class Command:
    """One executable command exposed via HTTP under a group."""

    def __init__(self, name, description, params, build_argv):
        """Store name, description, param specs and the argv builder."""
        self.name = name
        self.description = description
        self.params = params
        self.build_argv = build_argv

    def describe(self):
        """Return the JSON-serializable GET docs for this command."""
        return {
            "command": self.name,
            "description": self.description,
            "method": "POST",
            "params": {name: spec.describe() for name, spec in self.params.items()},
        }

    def validate(self, payload):
        """Strictly validate a JSON payload, return cleaned param values.

        Raises ParamError on unknown params, missing required params or
        values that fail their type check.
        """
        if not isinstance(payload, dict):
            raise ParamError("request body must be a JSON object")
        unknown = set(payload) - set(self.params)
        if unknown:
            raise ParamError(f"unknown parameter(s): {', '.join(sorted(unknown))}")
        cleaned = {}
        for name, spec in self.params.items():
            if name not in payload:
                if spec.required:
                    raise ParamError(f"missing required parameter: {name}")
                continue
            try:
                cleaned[name] = spec.ptype.validate(payload[name])
            except ParamError as exc:
                raise ParamError(f"invalid value for parameter {name!r}: {exc}") from exc
        return cleaned


class Group:
    """A group of related commands exposed under /<name>."""

    def __init__(self, name, description, commands):
        """Store group name, description and its Command objects."""
        self.name = name
        self.description = description
        self.commands = commands

    def describe(self):
        """Return the JSON-serializable GET docs listing child endpoints."""
        return {
            "group": self.name,
            "description": self.description,
            "commands": [
                {"path": f"/{self.name}/{cmd.name}", "description": cmd.description}
                for cmd in self.commands.values()
            ],
        }
