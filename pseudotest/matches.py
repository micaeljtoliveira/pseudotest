#!/usr/bin/env python3
"""
Match execution functions for pseudotest

This module contains all the functions responsible for executing different types
of matches (grepfield, line, size, etc.) and validating their results.
"""

import logging
import math
from pathlib import Path
from typing import Any, Callable, ChainMap, List, Optional

from pseudotest.utils import UsageError, display_match_status


def _get_target_line(lines: List[str], line_num: int) -> Optional[str]:
    """Extract target line handling positive and negative indexing

    Args:
        lines: File content as list of lines
        line_num: 1-indexed line number (positive) or negative index from end

    Returns:
        Target line content or None if line number is out of bounds
    """
    if line_num > 0:
        # Positive line numbers (1-indexed)
        if line_num > len(lines):
            return None
        return lines[line_num - 1]
    else:
        # Negative line numbers count from end
        if abs(line_num) > len(lines):
            return None
        return lines[line_num]


def line_matcher(lines: List[str], params: List[Any]) -> Optional[str]:
    """Execute line match: extract field from specific line

    Args:
        lines: File content as list of lines
        params: [line_number, column_position] where line is 1-indexed, column is 1-indexed

    Returns:
        Extracted string value or None if extraction fails
    """
    line_num = params[0]
    column_pos = params[1]

    logging.debug(f"   Line match: line={line_num}, column={column_pos}")

    target_line = _get_target_line(lines, line_num)
    if target_line is None:
        return None

    # Extract from character position (column_pos is 1-indexed column position)
    # cut -c column_pos- extracts from position 'column_pos' to end
    if column_pos > len(target_line):
        return None

    # Extract substring from column position onwards
    substring = target_line[column_pos - 1 :].lstrip()

    # Get first whitespace-separated token (equivalent to awk '{print $1}')
    return substring.split()[0] if substring.split() else ""


def linefield_matcher(lines: List[str], params: List[Any]) -> Optional[str]:
    """Execute linefield match: extract field from line

    Args:
        lines: File content as list of lines
        params: [line_number, field_number] where both are 1-indexed

    Returns:
        Extracted field value or None if extraction fails
    """
    line_num = params[0]
    field_num = params[1]

    logging.debug(f"   Linefield match: line={line_num}, field={field_num}")

    target_line = _get_target_line(lines, line_num)
    if target_line is None:
        return None

    # Split line into fields (whitespace-separated)
    fields = target_line.split()

    # Extract the specified field (1-indexed)
    if field_num < 1 or field_num > len(fields):
        return None

    return fields[field_num - 1]


def linefield_abs_matcher(lines: List[str], params: List[Any]) -> Optional[str]:
    """Execute linefield_abs match: extract absolute value from complex number fields

    Args:
        lines: File content as list of lines
        params: [line_number, real_field_number, imaginary_field_number] all 1-indexed

    Returns:
        String representation of absolute value or None if extraction fails
    """
    line_num = params[0]
    real_field_num = params[1]
    imag_field_num = params[2]

    logging.debug(f"   Linefield_abs match: line={line_num}, field_re={real_field_num}, field_im={imag_field_num}")

    target_line = _get_target_line(lines, line_num)
    if target_line is None:
        return None

    # Split line into fields (whitespace-separated)
    fields = target_line.split()

    # Extract the specified fields (1-indexed)
    if real_field_num < 1 or real_field_num > len(fields) or imag_field_num < 1 or imag_field_num > len(fields):
        return None

    try:
        real_part = float(fields[real_field_num - 1])
        imag_part = float(fields[imag_field_num - 1])
        abs_value = math.sqrt(real_part**2 + imag_part**2)
        return str(abs_value)
    except (ValueError, IndexError):
        return None


def _find_pattern_line_index(lines: List[str], pattern: str) -> Optional[int]:
    """Find the index of the first line containing the pattern

    Args:
        lines: File content as list of lines
        pattern: Pattern to search for

    Returns:
        Line index (0-based) or None if pattern not found
    """
    for i, line in enumerate(lines):
        if pattern in line:
            return i
    return None


def grep_matcher(lines: List[str], params: List[Any]) -> Optional[str]:
    """Execute grep match: find pattern and return value at offset

    Args:
        lines: File content as list of lines
        params: [pattern, column_position, line_offset] where column is 1-indexed

    Returns:
        Extracted string value or None if extraction fails
    """
    pattern = params[0]
    column_pos = params[1]
    line_offset = params[2]

    logging.debug(f"   Grep match: pattern={pattern}, column={column_pos}, offset={line_offset}")

    # Find the first line matching the pattern
    match_index = _find_pattern_line_index(lines, pattern)
    if match_index is None:
        return None

    # Get the line at offset from the match
    target_index = match_index + line_offset
    if target_index < 0 or target_index >= len(lines):
        return None

    target_line = lines[target_index]

    # Extract from byte position (column is 1-indexed)
    if column_pos > len(target_line):
        return None

    # Extract substring from column position onwards
    substring = target_line[column_pos - 1 :].lstrip()

    # Get first whitespace-separated token
    return substring.split()[0] if substring.split() else ""


def grepfield_matcher(lines: List[str], params: List[Any]) -> Optional[str]:
    """Execute grepfield match: find pattern and extract field from offset line"""
    pattern = params[0]
    field = params[1]
    offset = params[2]

    logging.debug(f"   Grepfield match: pattern={pattern}, field={field}, offset={offset}")

    # Find the first line matching the pattern
    match_index = None
    for i, line in enumerate(lines):
        if pattern in line:
            match_index = i
            break

    if match_index is None:
        return None

    # Get the line at offset from the match
    target_index = match_index + offset
    if target_index >= len(lines):
        return None

    target_line = lines[target_index]
    # Split line into fields (whitespace-separated)
    fields = target_line.split()

    # Extract the specified field (1-indexed)
    if field < 1 or field > len(fields):
        return None

    return fields[field - 1]


def grepcount_matcher(lines: List[str], params: List[Any]) -> Optional[str]:
    """Execute grepcount match: count lines containing pattern"""
    pattern = params[0]

    logging.debug(f"   Grepcount match: pattern={pattern}")

    # Count lines containing the pattern
    return str(sum(1 for line in lines if pattern in line))


def size_matcher(lines: List[str], params: List[Any]) -> Optional[str]:
    """Execute size match: get file size in bytes from text file lines

    Args:
        lines: File content as list of lines
        params: Empty list (not used)

    Returns:
        String representation of total character count
    """
    # Calculate file size from lines (sum of line lengths)
    # This works for text files that have been read with readlines()
    total_chars = sum(len(line) for line in lines)
    return str(total_chars)


MATCHER_DISPATCH: dict[str, Callable[[Any, List[Any]], Optional[str]]] = {
    "line": line_matcher,
    "linefield": linefield_matcher,
    "linefield_abs": linefield_abs_matcher,
    "grep": grep_matcher,
    "grepfield": grepfield_matcher,
    "grepcount": grepcount_matcher,
    "size": size_matcher,
}


def is_number(value: str | float | int) -> bool:
    """Check if a string represents a number"""
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        # Handle special cases like NaN, inf
        return str(value).lower() in ["nan", "inf", "-inf", "+inf"]


def match_compare_result(
    match_name: str,
    calculated_value: str,
    reference_value: Any,
    tolerance: Optional[float] = None,
    extra_indent: int = 0,
) -> bool:
    """Compare calculated and reference values and display results

    Args:
        match_name: Name of the match for display
        calculated_value: Value calculated from file
        reference_value: Expected reference value
        tolerance: Numerical tolerance for floating point comparison
        extra_indent: Additional indentation for nested output

    Returns:
        True if match succeeds, False otherwise
    """
    is_numeric_comparison = is_number(str(reference_value)) and is_number(calculated_value)
    if is_numeric_comparison:
        difference = abs(float(calculated_value) - float(reference_value))
        success = difference <= tolerance if tolerance else difference == 0.0
    else:
        success = str(calculated_value) == str(reference_value)
        difference = None

    display_match_status(match_name, success, extra_indent)

    if not success:
        indent = " " * (6 + extra_indent)
        print(f"{indent}" + "-" * 40)
        if difference is not None:
            # String comparison
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
            # String comparison
            print(f"{indent}Calculated value : '{calculated_value}'")
            print(f"{indent}Expected value   : '{reference_value}'")
        print(f"{indent}" + "-" * 40)

    return success


def match(name: str, params: ChainMap[str, Any], work_dir: Path, extra_indent: int = 0) -> bool:
    """Execute a single match with a single parameter set (no broadcasting)"""

    file = params["file"]

    filepath = work_dir / file
    try:
        with filepath.open("r", errors="replace") as f:
            lines = f.readlines()
    except (FileNotFoundError, UnicodeDecodeError) as e:
        logging.debug(f"   Error reading file {file}: {e}")
        return False

    reference_value = params.get("value")

    if "size" in params:
        reference_value = params["size"]
        calculated_value = size_matcher(lines, [])
    elif "grep" in params and "field" in params and "line" in params:
        calculated_value = grepfield_matcher(lines, [params["grep"], params["field"], params["line"]])
    elif "grep" in params and "column" in params and "line" in params:
        calculated_value = grep_matcher(lines, [params["grep"], params["column"], params["line"]])
    elif "grep" in params and "count" in params:
        reference_value = params["count"]
        calculated_value = grepcount_matcher(lines, [params["grep"]])
    elif "line" in params and "field" in params:
        calculated_value = linefield_matcher(lines, [params["line"], params["field"]])
    elif "line" in params and "column" in params:
        calculated_value = line_matcher(lines, [params["line"], params["column"]])
    elif "line" in params and "field_re" in params and "field_im" in params:
        calculated_value = linefield_abs_matcher(lines, [params["line"], params["field_re"], params["field_im"]])
    else:
        raise UsageError("Invalid match parameters")

    if calculated_value is None:
        return False

    tolerance = params.get("tol")

    match_success = match_compare_result(name, calculated_value, reference_value, tolerance, extra_indent=extra_indent)

    return match_success
