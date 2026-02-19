"""Unit tests for pseudotest.report."""

from pseudotest.report import _cast_to_type


class TestCastToType:
    def test_value_error_fallback(self):
        """Unparseable string for given type → returns original value."""
        result = _cast_to_type("not_an_int", int)
        assert result == "not_an_int"

    def test_none_returns_none(self):
        result = _cast_to_type(None, int)
        assert result is None

    def test_successful_cast(self):
        result = _cast_to_type("42", int)
        assert result == 42
