"""Unit tests for pseudotest.config_updater."""

from pseudotest.config_updater import (
    _cast_to_reference_type,
    _update_reference,
    _update_tolerance,
    compute_tolerance,
)


class TestComputeTolerance:
    def test_zero_difference(self):
        assert compute_tolerance(0) == 0.0

    def test_nonzero_difference(self):
        tol = compute_tolerance(0.0034)
        assert tol > 0.0034


class TestCastToReferenceType:
    def test_successful_int_cast(self):
        result = _cast_to_reference_type("123", 42)
        assert result == 123
        assert isinstance(result, int)

    def test_failed_cast_falls_back_to_string(self):
        result = _cast_to_reference_type("hello", 42)
        assert result == "hello"
        assert isinstance(result, str)

    def test_successful_float_cast(self):
        result = _cast_to_reference_type("3.14", 1.0)
        assert result == 3.14
        assert isinstance(result, float)

    def test_successful_str_cast(self):
        result = _cast_to_reference_type("anything", "ref")
        assert result == "anything"
        assert isinstance(result, str)


class TestUpdateTolerance:
    def test_no_reference_key_returns_false(self):
        """No reference key in param_set → returns False immediately."""
        match_def = {}
        param_set = {"something": "else"}
        assert _update_tolerance(match_def, 0, 1, "1.0", param_set) is False

    def test_non_numeric_returns_false(self):
        """Non-numeric reference or calculated value → returns False."""
        match_def = {}
        param_set = {"value": "text"}
        assert _update_tolerance(match_def, 0, 1, "also_text", param_set) is False

    def test_zero_difference_returns_false(self):
        """Calculated equals reference → difference is 0 → returns False."""
        match_def = {}
        param_set = {"value": 42.0}
        assert _update_tolerance(match_def, 0, 1, "42.0", param_set) is False

    def test_broadcast_scalar_tol_converted_to_list(self):
        """Existing scalar tol should be expanded to a list for broadcast."""
        match_def = {"value": [1.0, 2.0], "tol": 0.01}
        param_set = {"value": 1.0, "tol": 0.01}
        result = _update_tolerance(match_def, 0, 2, "1.5", param_set)
        assert result is True
        assert isinstance(match_def["tol"], list)
        assert len(match_def["tol"]) == 2


class TestUpdateReference:
    def test_no_reference_key_returns_false(self):
        """No reference key in match_def → returns False."""
        match_def = {"something": "else"}
        assert _update_reference(match_def, 0, 1, "1.0") is False
