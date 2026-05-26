"""Unit tests for core.settings helpers."""

import pytest

from core.settings import get_bool, get_float, get_int, get_optional, get_str


class TestGetOptional:
    def test_returns_yaml_value_when_no_env(self):
        result = get_optional("key1", {"key1": "value1"})
        assert result == "value1"

    def test_env_overrides_yaml(self, monkeypatch):
        monkeypatch.setenv("KEY1", "from_env")
        result = get_optional("key1", {"key1": "from_yaml"})
        assert result == "from_env"

    def test_empty_env_is_ignored(self, monkeypatch):
        monkeypatch.setenv("KEY1", "")
        result = get_optional("key1", {"key1": "from_yaml"})
        assert result == "from_yaml"

    def test_returns_none_when_missing(self):
        result = get_optional("missing", {})
        assert result is None


class TestGetBool:
    @pytest.mark.parametrize("raw,expected", [
        ("1", True), ("true", True), ("yes", True), ("y", True), ("on", True),
        ("True", True), ("TRUE", True),
        ("0", False), ("false", False), ("no", False), ("off", False),
    ])
    def test_truthy_values(self, raw, expected):
        defaults = {"flag": raw}
        assert get_bool("flag", defaults, False) == expected

    def test_default_when_missing(self):
        assert get_bool("missing", {}, True) is True
        assert get_bool("missing", {}, False) is False

    def test_bool_type_passthrough(self):
        assert get_bool("flag", {"flag": True}, False) is True


class TestGetInt:
    def test_returns_int(self):
        assert get_int("count", {"count": "5"}, 0) == 5

    def test_falls_back_to_default(self):
        assert get_int("missing", {}, 10) == 10

    def test_invalid_value_returns_default(self):
        assert get_int("count", {"count": "abc"}, 10) == 10


class TestGetFloat:
    def test_returns_float(self):
        assert get_float("rate", {"rate": "1.5"}, 0.0) == 1.5

    def test_falls_back_to_default(self):
        assert get_float("missing", {}, 1.0) == 1.0


class TestGetStr:
    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("HOST", "localhost:6650")
        result = get_str("host", {"host": "pulsar:6650"})
        assert result == "localhost:6650"
