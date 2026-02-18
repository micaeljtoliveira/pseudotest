"""Value comparison and numeric precision analysis for pseudotest."""

import logging
import re
from typing import Any, Optional

from pseudotest.formatting import display_match_status

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
        The precision implied by the string format, or 0.0 for non-numeric input.
    """
    try:
        float(value_str)
    except (ValueError, TypeError):
        return 0.0

    clean_str = value_str.strip()

    # Handle scientific notation, including Fortran-style 'D' exponent
    clean_str = re.sub(r"[dD]", "e", clean_str)
    sci_match = re.match(r"^[+-]?(\d*\.?\d*)[eE]([+-]?\d+)$", clean_str)
    if sci_match:
        mantissa, exp_str = sci_match.groups()
        exponent = int(exp_str)

        if "." in mantissa:
            decimal_digits = len(mantissa.split(".")[1])
            mantissa_precision = 10 ** (-decimal_digits)
        else:
            mantissa_precision = 1.0

        return mantissa_precision * (10**exponent)

    # Handle regular numbers
    if "." in clean_str:
        _integer_part, decimal_part = clean_str.split(".", 1)
        return 10 ** (-len(decimal_part))
    else:
        # Integer value, precision is 1
        return 1.0


# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------


def is_number(value: str | float | int) -> bool:
    """Check if *value* represents a valid number including special float values.

    Args:
        value: Value to test. Can be string, float, or int

    Returns:
        True if *value* represents a valid number (including inf, -inf, nan),
        False otherwise.
    """
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return str(value).lower() in ["nan", "inf", "-inf", "+inf"]


# ---------------------------------------------------------------------------
# Main comparison
# ---------------------------------------------------------------------------


def match_compare_result(
    match_name: str,
    calculated_value: str,
    reference_value: Any,
    tolerance: Optional[float] = None,
    extra_indent: int = 0,
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
        extra_indent: Additional indentation spaces for nested output display

    Returns:
        True if values match within tolerance (or exactly for strings),
        False otherwise.
    """
    is_numeric_comparison = is_number(str(reference_value)) and is_number(calculated_value)
    if is_numeric_comparison:
        difference = abs(float(calculated_value) - float(reference_value))
        success = difference <= tolerance if tolerance else difference == 0.0

        # Check if tolerance is smaller than the effective precision
        if tolerance and tolerance > 0:
            effective_precision = get_precision_from_string_format(calculated_value)
            if tolerance < effective_precision:
                indent = " " * (6 + extra_indent)
                logging.warning(
                    f"{indent}Tolerance {tolerance} is smaller than the effective precision "
                    f"{effective_precision} of calculated value '{calculated_value}'. Consider using "
                    f"tolerance >= {effective_precision:.2e}"
                )
    else:
        success = str(calculated_value) == str(reference_value)
        difference = None

    display_match_status(match_name, success, extra_indent)

    if not success:
        indent = " " * (6 + extra_indent)
        print(f"{indent}" + "-" * 40)
        if difference is not None:
            print(f"{indent}Calculated value : {calculated_value}")
            print(f"{indent}Reference value  : {reference_value}")
            print(f"{indent}Difference       : {difference}")
            if abs(float(reference_value)) > 1e-10:
                rel_diff = abs(float(calculated_value) - float(reference_value)) / abs(float(reference_value)) * 100.0
                print(f"{indent}Deviation [%]    : {rel_diff:.6f}")
            if tolerance:
                print(f"{indent}Tolerance        : {tolerance}")
                if abs(float(reference_value)) > 1e-10:
                    rel_tol = tolerance / abs(float(reference_value)) * 100.0
                    print(f"{indent}Tolerance [%]    : {rel_tol:.6f}")
        else:
            print(f"{indent}Calculated value : '{calculated_value}'")
            print(f"{indent}Expected value   : '{reference_value}'")
        print(f"{indent}" + "-" * 40)

    return success
