"""Value comparison and numeric precision analysis for pseudotest."""

import math
import re
from typing import Any, NamedTuple

# Fortran writes exponents with 'D' (e.g. 1.5D+00), which Python's float() does not accept
_FORTRAN_EXPONENT = re.compile(r"(?<=[\d.])[dD](?=[+-]?\d)")

# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------


def parse_number(value: Any) -> float | None:
    """Parse *value* as a float, accepting Fortran-style ``D`` exponents.

    Args:
        value: Value to parse, usually a string extracted from an output file

    Returns:
        The parsed number (which may be inf or nan), or None if *value* is not a number.
    """
    try:
        return float(_FORTRAN_EXPONENT.sub("e", str(value)))
    except ValueError:
        return None


def is_number(value: Any) -> bool:
    """Check if *value* represents a valid number including special float values.

    Args:
        value: Value to test. Can be string, float, or int

    Returns:
        True if *value* represents a valid number (including inf, -inf, nan and
        Fortran-style ``D`` exponents), False otherwise.
    """
    return parse_number(value) is not None


# ---------------------------------------------------------------------------
# Numeric precision
# ---------------------------------------------------------------------------


def get_precision_from_string_format(value_str: str) -> float:
    """Get the precision/resolution from a numeric string representation.

    Analyzes the string format of a number to determine the smallest
    representable difference using that format.

    Args:
        value_str: String representation of a number (e.g. "3.14", "1.23e+02")

    Returns:
        The precision implied by the string format, or 0.0 for non-numeric input,
        for inf and nan, and for a zero written in scientific notation, which are exact.
    """
    number = parse_number(value_str)
    if number is None or not math.isfinite(number):
        return 0.0

    # Handle scientific notation, including Fortran-style 'D' exponent
    clean_str = _FORTRAN_EXPONENT.sub("e", value_str.strip())
    sci_match = re.match(r"^[+-]?(\d*\.?\d*)[eE]([+-]?\d+)$", clean_str)
    if sci_match:
        mantissa, exp_str = sci_match.groups()
        # Every non-zero value is written with its own exponent, so a zero is exact
        if float(mantissa) == 0.0:
            return 0.0
        exponent = int(exp_str)
        decimal_digits = len(mantissa.split(".")[1]) if "." in mantissa else 0

        # A single power of ten avoids rounding noise such as 1.0000000000000001e-24
        return 10.0 ** (exponent - decimal_digits)

    # Handle regular numbers
    if "." in clean_str:
        _integer_part, decimal_part = clean_str.split(".", 1)
        return 10 ** (-len(decimal_part))
    else:
        # Integer value, precision is 1
        return 1.0


# ---------------------------------------------------------------------------
# Main comparison
# ---------------------------------------------------------------------------


class Comparison(NamedTuple):
    """Outcome of the comparison of a calculated value with its reference."""

    passed: bool
    # Absolute difference of a numeric comparison, None for strings
    difference: float | None = None
    # Precision of the calculated value, set when the tolerance is smaller than it
    precision: float | None = None
    # Why the comparison failed
    reason: str | None = None


def compare(calculated_value: str, reference_value: Any, tolerance: float | None = None) -> Comparison:
    """Compare *calculated_value* against *reference_value*.

    Performs a numerical comparison with tolerance when both values are numbers, or an exact string comparison
    otherwise. A tolerance smaller than the precision of the calculated value, as printed, makes the comparison fail.

    Args:
        calculated_value: Value calculated/extracted by the matcher
        reference_value: Expected reference value to compare against
        tolerance: Optional numerical tolerance for floating point comparison.
                  If None, exact equality is required for numbers.

    Returns:
        The outcome of the comparison.
    """
    calculated = parse_number(calculated_value)
    reference = parse_number(reference_value)

    if calculated is None or reference is None:
        if str(calculated_value) == str(reference_value):
            return Comparison(True)
        return Comparison(False, reason="Values differ")

    # Equal infinities, or two nans, match although their difference is nan
    both_nan = math.isnan(calculated) and math.isnan(reference)
    difference = 0.0 if calculated == reference or both_nan else abs(calculated - reference)

    # A tolerance smaller than the effective precision cannot be checked: treat it as an error
    if tolerance and tolerance > 0:
        precision = get_precision_from_string_format(calculated_value)
        if tolerance < precision:
            return Comparison(
                False, difference, precision, "Tolerance smaller than the precision of the calculated value"
            )

    if difference <= tolerance if tolerance else difference == 0.0:
        return Comparison(True, difference)
    return Comparison(
        False, difference, reason="Difference larger than the tolerance" if tolerance else "Values differ"
    )
