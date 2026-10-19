"""Tests for Command/Group/Param core building blocks."""

import pytest

from portcullis.commands.base import Command, Group, Param
from portcullis.params import GenericIntegerType, GenericStringType, ParamError


def make_command():
    """Build a small command with one required and one optional param."""
    return Command(
        name="demo",
        description="demo command",
        params={
            "name": Param(GenericStringType(), "a name", required=True),
            "count": Param(GenericIntegerType(), "a count", required=False),
        },
        build_argv=lambda args: ["echo", args["name"]],
    )


class TestParam:
    def test_describe_shape(self):
        doc = Param(GenericStringType(), "a name").describe()
        assert doc == {"type": "string", "required": True, "description": "a name"}

    def test_describe_optional(self):
        doc = Param(GenericStringType(), "d", required=False).describe()
        assert doc["required"] is False


class TestCommandDescribe:
    def test_shape(self):
        doc = make_command().describe()
        assert doc["command"] == "demo"
        assert doc["method"] == "POST"
        assert set(doc["params"]) == {"name", "count"}
        assert doc["params"]["name"]["required"] is True
        assert doc["params"]["count"]["required"] is False


class TestCommandValidate:
    def test_valid_payload(self):
        cleaned = make_command().validate({"name": "x", "count": 3})
        assert cleaned == {"name": "x", "count": 3}

    def test_optional_missing_ok(self):
        assert make_command().validate({"name": "x"}) == {"name": "x"}

    def test_missing_required(self):
        with pytest.raises(ParamError, match="missing required parameter: name"):
            make_command().validate({})

    def test_unknown_param(self):
        with pytest.raises(ParamError, match="unknown parameter"):
            make_command().validate({"name": "x", "bogus": 1})

    def test_non_dict_payload(self):
        with pytest.raises(ParamError, match="JSON object"):
            make_command().validate(["name"])

    def test_value_error_wrapped(self):
        with pytest.raises(ParamError,
                           match="invalid value for parameter 'count'"):
            make_command().validate({"name": "x", "count": "three"})


class TestGroupDescribe:
    def test_shape(self):
        group = Group("g", "group desc", {"demo": make_command()})
        doc = group.describe()
        assert doc == {
            "group": "g",
            "description": "group desc",
            "commands": [{"path": "/g/demo", "description": "demo command"}],
        }
