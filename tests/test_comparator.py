"""Unit tests for pseudotest.comparator."""

from pseudotest.comparator import (
    get_precision_from_string_format,
    is_number,
    match_compare_result,
    parse_number,
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
        """Cover the tolerance-vs-precision error path."""
        # tolerance smaller than the effective precision => triggers error
        result = match_compare_result("test_prec", "1.2345e+02", 123.46, tolerance=1e-6)
        assert result is False  # difference is ~0.01 > 1e-6

    def test_tolerance_too_small_fails_even_when_values_appear_to_match(self):
        """tolerance < effective precision must fail even if calculated == reference."""
        # "1.23" has precision 0.01; tolerance 1e-6 < 0.01 => error
        result = match_compare_result("too_tight", "1.23", 1.23, tolerance=1e-6)
        assert result is False

    def test_any_tolerance_is_reliable_for_scientific_zero(self):
        """A zero in scientific notation is exact, so a tolerance below its mantissa's precision passes."""
        result = match_compare_result("sci_zero", "0.00000000E+000", 0.0, tolerance=4.7e-22)
        assert result is True

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
        p = get_precision_from_string_format("1.5D+01")
        assert abs(p - 1.0) < 1e-12  # 0.1 * 10 = 1.0

    def test_integer_precision(self):
        p = get_precision_from_string_format("42")
        assert p == 1.0

    def test_decimal_precision(self):
        p = get_precision_from_string_format("3.14")
        assert abs(p - 0.01) < 1e-12

    def test_scientific_notation_zero_is_exact(self):
        assert get_precision_from_string_format("0.00000000E+000") == 0.0
        assert get_precision_from_string_format("-0.0000E+00") == 0.0

    def test_fixed_notation_zero_keeps_precision(self):
        p = get_precision_from_string_format("0.000")
        assert abs(p - 0.001) < 1e-12


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


# ---------------------------------------------------------------------------
# Number parsing and special values
# ---------------------------------------------------------------------------


class TestParseNumber:
    def test_fortran_exponent(self):
        assert parse_number("1.5D+00") == 1.5
        assert parse_number("-2.5d-01") == -0.25
        assert is_number("1.5D+00") is True

    def test_not_a_number(self):
        assert parse_number("D") is None
        assert parse_number("***") is None
        assert parse_number(None) is None


class TestSpecialValues:
    def test_fortran_exponent_matches_float_reference(self):
        assert match_compare_result("fort", "1.5D+00", 1.5) is True

    def test_equal_infinities_match(self):
        assert match_compare_result("inf", "inf", float("inf")) is True
        assert match_compare_result("inf", "-Infinity", float("-inf")) is True

    def test_opposite_infinities_do_not_match(self):
        assert match_compare_result("inf", "-inf", float("inf")) is False

    def test_infinity_is_exact_with_tolerance(self):
        assert get_precision_from_string_format("inf") == 0.0
        assert match_compare_result("inf", "inf", float("inf"), tolerance=1e-6) is True

    def test_nan_matches_nan_only(self):
        assert match_compare_result("nan", "NaN", float("nan")) is True
        assert match_compare_result("nan", "NaN", 1.0) is False


class TestFailureDetails:
    def test_tolerance_too_small_details_on_separate_lines(self, capsys):
        match_compare_result("too_tight", "1.23", 1.23, tolerance=1e-6)
        lines = [line.strip() for line in capsys.readouterr().out.splitlines()]
        assert any(line.startswith("Unreliable comparison") for line in lines)
        assert "Calculated value    : 1.23" in lines
        assert "Effective precision : 0.01" in lines
        assert "Tolerance           : 1e-06" in lines
        assert any("at least 0.01" in line for line in lines)

    def test_precision_has_no_rounding_noise(self):
        assert get_precision_from_string_format("-1.40343322E-16") == 1e-24
