"""Value comparison and numeric precision analysis for pseudotest."""

import math
import re
from typing import Any

from pseudotest.formatting import display_failure_details, display_match_status

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


def _numeric_failure_details(
    calculated_value: str,
    calculated: float,
    reference_value: Any,
    reference: float,
    difference: float,
    tolerance: float | None,
) -> list[str]:
    """Return the detail lines describing a failed numeric comparison."""
    details = [
        f"Calculated value : {calculated_value}",
        f"Reference value  : {reference_value}",
        f"Difference       : {difference}",
    ]
    if abs(reference) > 1e-10:
        details.append(f"Deviation [%]    : {abs(calculated - reference) / abs(reference) * 100.0:.6f}")
    if tolerance:
        details.append(f"Tolerance        : {tolerance}")
        if abs(reference) > 1e-10:
            details.append(f"Tolerance [%]    : {tolerance / abs(reference) * 100.0:.6f}")
    return details


def match_compare_result(
    match_name: str,
    calculated_value: str,
    reference_value: Any,
    tolerance: float | None = None,
    indent_level: int = 2,
) -> bool:
    """Compare *calculated_value* against *reference_value* and display results.

    Performs numerical comparison with tolerance for numeric values, or exact
    string comparison for non-numeric values. Displays detailed comparison
    results including differences, deviations, and tolerance information when
    a match fails.

    Args:
        match_name: Descriptive name for the match (used in output display)
        calculated_value: Value calculated/extracted by the matcher
        reference_value: Expected reference value to compare against
        tolerance: Optional numerical tolerance for floating point comparison.
                  If None, exact equality is required for numbers.
        indent_level: Nesting level for output display

    Returns:
        True if values match within tolerance (or exactly for strings),
        False otherwise.
    """
    calculated = parse_number(calculated_value)
    reference = parse_number(reference_value)

    if calculated is None or reference is None:
        success = str(calculated_value) == str(reference_value)
        details = [f"Calculated value : '{calculated_value}'", f"Expected value   : '{reference_value}'"]
    else:
        # Equal infinities, or two nans, match although their difference is nan
        both_nan = math.isnan(calculated) and math.isnan(reference)
        difference = 0.0 if calculated == reference or both_nan else abs(calculated - reference)
        success = difference <= tolerance if tolerance else difference == 0.0
        details = _numeric_failure_details(
            calculated_value, calculated, reference_value, reference, difference, tolerance
        )

        # Check if tolerance is smaller than the effective precision — treat as error
        if tolerance and tolerance > 0:
            effective_precision = get_precision_from_string_format(calculated_value)
            if tolerance < effective_precision:
                success = False
                details = [
                    "Unreliable comparison: the tolerance is smaller than the precision of the calculated value",
                    f"Calculated value    : {calculated_value}",
                    f"Effective precision : {effective_precision:g}",
                    f"Tolerance           : {tolerance}",
                    f"Use a tolerance of at least {effective_precision:g}, or print the value with more digits",
                ]

    display_match_status(match_name, success, indent_level)
    if not success:
        display_failure_details(details, indent_level)

    return success
