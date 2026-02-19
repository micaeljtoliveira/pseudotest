"""Unit tests for pseudotest.comparator."""

from pseudotest.comparator import (
    get_precision_from_string_format,
    is_number,
    match_compare_result,
)

# ---------------------------------------------------------------------------
# is_number
# ---------------------------------------------------------------------------


class TestIsNumber:
    def test_special_values(self):
        assert is_number("nan") is True
        assert is_number("inf") is True
        assert is_number("-inf") is True
        assert is_number("+inf") is True
        assert is_number("not_a_num") is False

    def test_none(self):
        assert is_number(None) is False


# ---------------------------------------------------------------------------
# match_compare_result
# ---------------------------------------------------------------------------


class TestMatchCompareResult:
    def test_numeric_mismatch_with_tolerance_detail(self):
        """Cover the tolerance-vs-precision warning path."""
        # tolerance smaller than the effective precision => triggers warning
        result = match_compare_result("test_prec", "1.2345e+02", 123.46, tolerance=1e-6)
        assert result is False  # difference is ~0.01 > 1e-6

    def test_numeric_match_near_zero_reference(self):
        """Cover the branch where |reference| <= 1e-10 (no deviation % printed)."""
        result = match_compare_result("zero_ref", "0.0001", 0.0, tolerance=None)
        assert result is False

    def test_numeric_match_with_tol_and_deviation(self):
        """Cover full failure output including tolerance percentage."""
        result = match_compare_result("tol_dev", "10.0", 20.0, tolerance=0.5)
        assert result is False


# ---------------------------------------------------------------------------
# get_precision_from_string_format
# ---------------------------------------------------------------------------


class TestGetPrecision:
    def test_non_numeric_string(self):
        assert get_precision_from_string_format("abc") == 0.0

    def test_scientific_notation_with_decimal(self):
        p = get_precision_from_string_format("1.23e+02")
        assert abs(p - 1.0) < 1e-12  # 0.01 * 100 = 1.0

    def test_scientific_notation_integer_mantissa(self):
        p = get_precision_from_string_format("5e+03")
        assert abs(p - 1000.0) < 1e-6

    def test_fortran_d_notation(self):
        # Python's float() cannot parse Fortran D notation, so it returns 0.0
        p = get_precision_from_string_format("1.5D+01")
        assert p == 0.0

    def test_integer_precision(self):
        p = get_precision_from_string_format("42")
        assert p == 1.0

    def test_decimal_precision(self):
        p = get_precision_from_string_format("3.14")
        assert abs(p - 0.01) < 1e-12


# ---------------------------------------------------------------------------
# String comparison
# ---------------------------------------------------------------------------


class TestStringComparison:
    def test_string_mismatch_prints_details(self):
        """Non-numeric string mismatch is correctly detected."""
        result = match_compare_result("status", "converged", "diverged")
        assert result is False

    def test_string_match(self):
        result = match_compare_result("status", "converged", "converged")
        assert result is True
