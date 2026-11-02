"""Unit tests for pseudotest.comparator."""

import pytest

from pseudotest.comparator import (
    Comparison,
    compare,
    get_precision_from_string_format,
    is_number,
    parse_number,
)

# ---------------------------------------------------------------------------
# Number parsing
# ---------------------------------------------------------------------------


class TestParseNumber:
    def test_special_values(self):
        assert is_number("nan") is True
        assert is_number("inf") is True
        assert is_number("-inf") is True
        assert is_number("+inf") is True
        assert is_number("not_a_num") is False

    def test_fortran_exponent(self):
        assert parse_number("1.5D+00") == 1.5
        assert parse_number("-2.5d-01") == -0.25
        assert is_number("1.5D+00") is True

    def test_not_a_number(self):
        assert parse_number("D") is None
        assert parse_number("***") is None
        assert parse_number(None) is None
        assert is_number(None) is False


# ---------------------------------------------------------------------------
# get_precision_from_string_format
# ---------------------------------------------------------------------------


class TestGetPrecision:
    @pytest.mark.parametrize(
        ("value", "precision"),
        [
            ("abc", 0.0),
            ("42", 1.0),
            ("3.14", 0.01),
            ("0.000", 0.001),
            ("1.23e+02", 1.0),
            ("5e+03", 1000.0),
            ("1.5D+01", 1.0),
            # A single power of ten avoids rounding noise such as 1.0000000000000001e-24
            ("-1.40343322E-16", 1e-24),
            # A zero in scientific notation, inf and nan are exact
            ("0.00000000E+000", 0.0),
            ("-0.0000E+00", 0.0),
            ("inf", 0.0),
            ("nan", 0.0),
        ],
    )
    def test_precision(self, value, precision):
        assert get_precision_from_string_format(value) == pytest.approx(precision, rel=1e-12)


# ---------------------------------------------------------------------------
# compare
# ---------------------------------------------------------------------------


class TestCompare:
    def test_numbers_equal(self):
        assert compare("-42.5000", -42.5) == Comparison(True, 0.0)

    def test_numbers_within_tolerance(self):
        assert compare("10.0", 10.2, tolerance=0.5) == Comparison(True, pytest.approx(0.2))

    def test_numbers_differ(self):
        assert compare("0.0001", 0.0) == Comparison(False, 0.0001, reason="Values differ")

    def test_difference_larger_than_tolerance(self):
        assert compare("10.0", 20.0, tolerance=0.5) == Comparison(
            False, 10.0, reason="Difference larger than the tolerance"
        )

    def test_tolerance_smaller_than_precision(self):
        """A tolerance smaller than the precision of the calculated value fails, even for equal values."""
        comparison = compare("1.23", 1.23, tolerance=1e-6)
        assert not comparison.passed
        assert comparison.precision == pytest.approx(0.01)
        assert comparison.reason == "Tolerance smaller than the precision of the calculated value"

    def test_any_tolerance_is_reliable_for_scientific_zero(self):
        assert compare("0.00000000E+000", 0.0, tolerance=4.7e-22).passed

    def test_strings(self):
        assert compare("converged", "converged") == Comparison(True)
        assert compare("converged", "diverged") == Comparison(False, reason="Values differ")

    def test_fortran_exponent_matches_float_reference(self):
        assert compare("1.5D+00", 1.5).passed

    def test_equal_infinities_match(self):
        assert compare("inf", float("inf")).passed
        assert compare("-Infinity", float("-inf")).passed
        assert compare("inf", float("inf"), tolerance=1e-6).passed

    def test_opposite_infinities_do_not_match(self):
        assert not compare("-inf", float("inf")).passed

    def test_nan_matches_nan_only(self):
        assert compare("NaN", float("nan")).passed
        assert not compare("NaN", 1.0).passed
