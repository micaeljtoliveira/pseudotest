"""Unit tests for pseudotest.config_updater."""

import io

import pytest

from pseudotest.config_updater import (
    _update_reference,
    _update_tolerance,
    cast_like,
    compute_tolerance,
    save_config,
)
from pseudotest.test_config import yaml


class TestComputeTolerance:
    def test_zero_difference(self):
        assert compute_tolerance(0) == 0.0

    def test_nonzero_difference(self):
        tol = compute_tolerance(0.0034)
        assert tol > 0.0034


class TestCastToReferenceType:
    def test_successful_int_cast(self):
        result = cast_like("123", 42)
        assert result == 123
        assert isinstance(result, int)

    def test_failed_cast_falls_back_to_string(self):
        result = cast_like("hello", 42)
        assert result == "hello"
        assert isinstance(result, str)

    def test_successful_float_cast(self):
        result = cast_like("3.14", 1.0)
        assert result == 3.14
        assert isinstance(result, float)

    def test_successful_str_cast(self):
        result = cast_like("anything", "ref")
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

    def test_zero_difference_tol_too_small_resets_to_zero(self):
        """When tol < effective precision and difference is 0, tolerance is reset to 0.0."""
        # "1.23" has precision 0.01; tol 1e-6 < 0.01 → too small → reset to 0.0
        match_def = {"value": 1.23, "tol": 1e-6}
        param_set = {"value": 1.23, "tol": 1e-6}
        result = _update_tolerance(match_def, 0, 1, "1.23", param_set)
        assert result is True
        assert match_def["tol"] == 0.0

    def test_zero_difference_scientific_zero_keeps_tolerance(self):
        """A zero in scientific notation is exact, so a tolerance below 1e-8 is not reset."""
        match_def = {"value": 0.0, "tol": 4.7e-22}
        param_set = {"value": 0.0, "tol": 4.7e-22}
        assert _update_tolerance(match_def, 0, 1, "0.00000000E+000", param_set) is False
        assert match_def["tol"] == 4.7e-22

    def test_zero_difference_tol_ok_returns_false(self):
        """When tol >= effective precision and difference is 0, no update needed."""
        # "1.23" has precision 0.01; tol 0.05 >= 0.01 → fine → no update
        match_def = {"value": 1.23, "tol": 0.05}
        param_set = {"value": 1.23, "tol": 0.05}
        assert _update_tolerance(match_def, 0, 1, "1.23", param_set) is False

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


def _rewrite(template: str, calculated: str) -> str:
    """Replace the reference written as *template* by *calculated* and return how it is written back."""
    data = yaml.load(f"value: {template}\n")
    data["value"] = cast_like(calculated, data["value"])
    out = io.StringIO()
    yaml.dump(data, out)
    return out.getvalue().strip().split(": ", 1)[1]


class TestReferenceFormat:
    """Updated references keep the notation of the old ones without losing digits."""

    @pytest.mark.parametrize(
        ("template", "calculated"),
        [
            ("1.25568282E-01", "1.25568286E-01"),
            ("-1.40343322E-16", "-1.52345678E-16"),
            ("2.05890416E+01", "2.05890414E+01"),
            ("9.99999999E-02", "1.00000001E-01"),
            ("1.2345e-03", "1.2346e-03"),
        ],
    )
    def test_scientific_notation(self, template, calculated):
        assert _rewrite(template, calculated) == calculated

    @pytest.mark.parametrize("calculated", ["-1.40343322E-16", "1.40343322E-16", "0.00000000E+00"])
    def test_mantissa_with_leading_zero_is_normalised(self, calculated):
        assert _rewrite("0.00000000E+09", calculated) == calculated

    @pytest.mark.parametrize(
        ("template", "calculated"),
        [
            ("-1.40343322E-16", "2.10000000E-17"),
            ("1.25568282E-01", "-1.25568286E-01"),
            ("-0.5000", "0.2500"),
            ("0.5000", "-0.2500"),
        ],
    )
    def test_sign_follows_value(self, template, calculated):
        assert _rewrite(template, calculated) == calculated

    def test_fixed_notation_keeps_decimal_places(self):
        assert _rewrite("-42.5000", "-42.505") == "-42.5050"

    def test_long_flow_sequence_not_wrapped(self, tmp_path):
        line = "value: [" + ", ".join(f"{-215.070201 + i:.6f}" for i in range(14)) + "]\n"
        path = tmp_path / "test.yaml"
        path.write_text(line)
        save_config(yaml.load(path), path)
        assert path.read_text() == line


class TestCastLikeSpecialValues:
    @pytest.mark.parametrize(("value", "expected"), [("false", False), ("TRUE", True), ("no", False), ("yes", True)])
    def test_bool_reference(self, value, expected):
        """bool("false") is True, so booleans are parsed from their spelling."""
        assert cast_like(value, not expected) is expected

    def test_bool_reference_unrecognised_value_kept_as_string(self):
        assert cast_like("maybe", True) == "maybe"

    def test_int_reference_with_fractional_value(self):
        assert cast_like("12.5", 12) == 12.5

    def test_infinity_replaces_float_reference(self):
        assert _rewrite("1.5", "inf") == ".inf"


class TestUpdateReferenceNonNumeric:
    def test_numeric_reference_not_replaced_by_text(self, caplog):
        """A Fortran overflow such as '***' must not replace a numeric reference."""
        match_def = {"value": 1.5}
        assert _update_reference(match_def, 0, 1, "***") is False
        assert match_def["value"] == 1.5
        assert "Not replacing numeric reference" in caplog.text

    def test_string_reference_replaced_by_text(self):
        match_def = {"value": "converged"}
        assert _update_reference(match_def, 0, 1, "diverged") is True
        assert match_def["value"] == "diverged"


class TestUpdateToleranceLimits:
    def test_tolerance_not_below_precision_of_calculated_value(self):
        """The difference 0.005 needs tol 0.0055, but '1.23' is only precise to 0.01."""
        match_def = {"value": 1.225}
        assert _update_tolerance(match_def, 0, 1, "1.23", {"value": 1.225}) is True
        assert match_def["tol"] == 0.01

    def test_infinite_difference_not_covered(self, caplog):
        match_def = {"value": 1.5}
        assert _update_tolerance(match_def, 0, 1, "inf", {"value": 1.5}) is False
        assert "tol" not in match_def
        assert "No tolerance can cover" in caplog.text
