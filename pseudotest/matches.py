#!/usr/bin/env python3
"""
Match execution functions for pseudotest

This module contains all the functions responsible for executing different types
of matches (grepfield, line, size, etc.) and validating their results.
"""

import logging
import math
from pathlib import Path
from typing import Any, ChainMap, List, Optional

from pseudotest.utils import UsageError, display_match_status, get_precision_from_string_format

# =============================================================================
# Helper Functions
# =============================================================================


def _get_target_line(lines: List[str], line_num: int) -> Optional[str]:
    """Extract target line handling positive and negative indexing.

    Supports both positive line numbers (0-indexed from start) and negative
    line numbers (counted from end). This provides flexible line access
    similar to standard Python list indexing.

    Args:
        lines: File content as list of lines
        line_num: Line number where positive values are 0-indexed from start,
                 negative values count from end (-1 = last line)

    Returns:
        Target line content or None if line number is out of bounds

    Examples:
        >>> lines = ["first", "second", "third"]
        >>> _get_target_line(lines, 0)  # "first"
        >>> _get_target_line(lines, -1)  # "third"
    """
    if line_num >= 0:
        # Positive line numbers (0-indexed)
        if line_num >= len(lines):
            return None
        return lines[line_num]
    else:
        # Negative line numbers count from end
        if abs(line_num) > len(lines):
            return None
        return lines[line_num]


def _find_pattern_line(lines: List[str], pattern: str, offset: int = 0) -> Optional[str]:
    """Find the line content at specified offset from first line containing pattern.

    Performs simple substring matching to locate the first occurrence
    of the pattern within any line of the input text, then returns the
    content of the line at the specified offset from that match.

    Args:
        lines: File content as list of lines
        pattern: Text pattern to search for (case-sensitive substring match)
        offset: Line offset from the pattern match (0=same line, 1=next line, etc.)

    Returns:
        Content of the target line (pattern line + offset),
        or None if pattern not found or offset line doesn't exist

    Examples:
        >>> lines = ["hello world", "test pattern", "final line"]
        >>> _find_pattern_line(lines, "pattern", 0)  # Returns "test pattern"
        >>> _find_pattern_line(lines, "pattern", 1)  # Returns "final line"
        >>> _find_pattern_line(lines, "missing", 0)  # Returns None
    """
    for i, line in enumerate(lines):
        if pattern in line:
            target_index = i + offset
            if 0 <= target_index < len(lines):
                return lines[target_index]
            else:
                return None
    return None


def _extract_field_from_line(line: Optional[str], field_num: int) -> Optional[str]:
    """Extract a specific whitespace-separated field from a line.

    Splits the line on whitespace and returns the field at the specified
    position. Similar to: awk '{print $N}' where N is the field number.

    Args:
        line: Line content to extract field from, or None if line doesn't exist
        field_num: 1-indexed field position after whitespace splitting

    Returns:
        Content of the specified field as string, or None if line is None,
        or field number is out of bounds

    Examples:
        >>> _extract_field_from_line("first second third", 2)  # "second"
        >>> _extract_field_from_line("first second third", 5)  # None
        >>> _extract_field_from_line(None, 2)  # None
    """
    if line is None:
        return None

    fields = line.split()
    if field_num < 1 or field_num > len(fields):
        return None
    return fields[field_num - 1]


def _extract_column_from_line(line: Optional[str], column_pos: int) -> Optional[str]:
    """Extract first token starting from a specific column position in a line.

    Similar to the shell command: cut -c<column>- | awk '{print $1}'
    Extracts a substring from the specified column position to the end of the line,
    then returns the first whitespace-separated token from that substring.

    Args:
        line: Line content to extract token from, or None if line doesn't exist
        column_pos: 1-indexed character position to start extraction

    Returns:
        First whitespace-separated token from the specified position,
        empty string if no tokens found after column position,
        or None if line is None or column position is out of bounds

    Examples:
        >>> _extract_column_from_line("  hello world test", 3)  # "hello"
        >>> _extract_column_from_line("  hello world test", 9)  # "world"
        >>> _extract_column_from_line("short", 10)  # None
        >>> _extract_column_from_line("   ", 1)  # "" (empty string)
        >>> _extract_column_from_line(None, 3)  # None
    """
    if line is None:
        return None

    if column_pos > len(line):
        return None

    # Extract substring from column position onwards
    substring = line[column_pos - 1 :].lstrip()

    # Get first whitespace-separated token
    tokens = substring.split()
    return tokens[0] if tokens else ""


# =============================================================================
# Utility Functions
# =============================================================================


def is_number(value: str | float | int) -> bool:
    """Check if a value represents a valid number including special float values.

    Attempts to convert the value to float and handles special cases like
    infinity and NaN. Supports string representations of numbers.

    Args:
        value: Value to test - can be string, float, or int

    Returns:
        True if value represents a valid number (including inf, -inf, nan),
        False otherwise

    Examples:
        >>> is_number("123.45")  # True
        >>> is_number("inf")     # True
        >>> is_number("hello")   # False
        >>> is_number(42)        # True
    """
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
    """Compare calculated value against reference with optional tolerance and display results.

    Performs numerical comparison with tolerance for numeric values, or exact
    string comparison for non-numeric values. Displays detailed comparison
    results including differences, deviations, and tolerance information.

    Args:
        match_name: Descriptive name for the match (used in output display)
        calculated_value: Value calculated/extracted by the matcher
        reference_value: Expected reference value to compare against
        tolerance: Optional numerical tolerance for floating point comparison.
                  If None, exact equality is required for numbers.
        extra_indent: Additional indentation spaces for nested output display

    Returns:
        True if values match within tolerance (or exactly for strings),
        False otherwise

    Examples:
        >>> match_compare_result("test", "123.45", "123.50", tolerance=0.1)  # True
        >>> match_compare_result("test", "hello", "hello", None)  # True
        >>> match_compare_result("test", "hello", "world", None)  # False
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


# =============================================================================
# Match Handler Functions
# =============================================================================


def _handle_directory_matches(dirpath: Path, params: ChainMap[str, Any]) -> tuple[str | None, Any]:
    """Handle directory-based matches and return calculated and reference values.

    Supports two types of directory operations:
    - file_is_present: Check if a specific file exists in the directory
    - count_files: Count the number of files (excluding subdirectories) in the directory

    Args:
        dirpath: Path to the directory to examine
        params: Match parameters containing either 'file_is_present' or 'count_files'

    Returns:
        Tuple of (calculated_value, reference_value) where:
        - For file_is_present: ("True"/"False", "True")
        - For count_files: (str(file_count), expected_count)
        - If directory doesn't exist: ("False", "True")

    Raises:
        UsageError: If neither 'file_is_present' nor 'count_files' is provided,
                   or if 'file_is_present' parameter is not a string
    """

    # Check that the specified path is a directory
    if not dirpath.is_dir():
        calculated_value = "False"
        reference_value = "True"

    elif "file_is_present" in params:
        filename = params["file_is_present"]
        if not isinstance(filename, str):
            raise UsageError("file_is_present parameter must be a string")

        # Check that the specified file exists in the directory
        file_path = dirpath / filename
        calculated_value = "False" if not file_path.is_file() else "True"
        reference_value = "True"

    elif "count_files" in params:
        # Count only files, not subdirectories
        file_count = sum(1 for item in dirpath.iterdir() if item.is_file())
        calculated_value = str(file_count)
        reference_value = params["count_files"]

    else:
        raise UsageError("Directory parameter requires either 'file_is_present' or 'count_files'")

    return calculated_value, reference_value


def _handle_file_matches(filepath: Path, params: ChainMap[str, Any]) -> tuple[str | None, Any]:
    """Handle file-based matches (size) and return calculated and reference values.

    Gets the file size in bytes using filesystem metadata, which works efficiently
    for both text and binary files without reading file contents.

    Args:
        filepath: Path to the file to examine
        params: Match parameters containing 'size' for expected file size

    Returns:
        Tuple of (calculated_value, reference_value) where:
        - calculated_value: String representation of file size in bytes, or None if file error
        - reference_value: Expected file size from params['size']
    """

    try:
        # Get actual file size in bytes - works for both text and binary files
        file_size = filepath.stat().st_size
        calculated_value = str(file_size)
    except (FileNotFoundError, OSError):
        calculated_value = None

    reference_value = params["size"]
    return calculated_value, reference_value


def _handle_content_matches(lines: List[str], params: ChainMap[str, Any]) -> tuple[str | None, Any]:
    """Handle content-based matches and return calculated and reference values.

    Processes content-based match parameters to extract values from file lines.
    Supports pattern searching, line indexing, field extraction, column extraction,
    and complex number absolute value calculation.

    Priority order for match types:
    1. Grep count (grep + count parameters)
    2. Line selection: grep pattern with optional line offset, or direct line number
    3. Value extraction: field, column, or field_re/field_im for absolute value

    Args:
        lines: File content as list of lines
        params: Match parameters containing extraction and reference specifications

    Returns:
        Tuple of (calculated_value, reference_value) where calculated_value
        may be None if extraction fails

    Raises:
        UsageError: If required parameters are missing or invalid combinations provided
    """

    # Grep count match takes precedence over all other content-based matches
    if "grep" in params and "count" in params:
        calculated_value = str(sum(1 for line in lines if params["grep"] in line))
        return calculated_value, params["count"]

    # Next, get line content based on grep or line parameters. Grep takes precedence over line.
    if "grep" in params:
        offset = params.get("line", 0)
        line = _find_pattern_line(lines, params["grep"], offset)
    elif "line" in params:
        line = _get_target_line(lines, params["line"] - 1)
    else:
        raise UsageError("Content-based match requires either 'grep' or 'line' parameter")

    # Then extract the value based on field, column, or field_re/field_im parameters
    if "field" in params:
        calculated_value = _extract_field_from_line(line, params["field"])
    elif "column" in params:
        calculated_value = _extract_column_from_line(line, params["column"])
    elif "field_re" in params and "field_im" in params:
        real_field = _extract_field_from_line(line, params["field_re"])
        imag_field = _extract_field_from_line(line, params["field_im"])
        if real_field is not None and imag_field is not None:
            try:
                real_part = float(real_field)
                imag_part = float(imag_field)
                calculated_value = str(math.sqrt(real_part**2 + imag_part**2))
            except ValueError:
                calculated_value = None
        else:
            calculated_value = None
    else:
        raise UsageError("Content-based match requires 'field', 'column', or both 'field_re' and 'field_im' parameters")

    if "value" not in params:
        raise UsageError("Content-based match requires 'value' parameter for reference value")

    return calculated_value, params["value"]


# =============================================================================
# Main Match Function
# =============================================================================


def match(name: str, params: ChainMap[str, Any], work_dir: Path, extra_indent: int = 0) -> bool:
    """Execute a match operation and compare result against expected value.

    Main entry point for the matching system. Routes to appropriate matcher
    based on parameter types, executes the match, and compares the result
    against the expected value with optional tolerance.

    Supports multiple match types:
    - Directory operations: file presence, file counting
    - File operations: size validation
    - Content operations: line/field extraction, pattern searching

    Args:
        name: Descriptive name for the match (used in output display)
        params: Configuration parameters containing:
               - Target specification: 'file' or 'directory'
               - Match type parameters: 'line', 'grep', 'size', etc.
               - Expected value: 'value', 'count', 'files', etc.
               - Optional: 'tol' for numerical tolerance
        work_dir: Working directory containing the target files
        extra_indent: Additional indentation for nested output display

    Returns:
        True if match succeeds (calculated value matches expected within tolerance),
        False if match fails or file operations fail

    Examples:
        >>> # Line field extraction
        >>> match("test1", ChainMap({"file": "data.txt", "line": 5, "field": 2, "value": "expected"}), Path("."))

        >>> # Pattern search with counting
        >>> match("test2", ChainMap({"file": "log.txt", "grep": "ERROR", "count": 3}), Path("."))

        >>> # Directory file counting
        >>> match("test3", ChainMap({"directory": "output", "count_files": 5}), Path("."))
    """

    # Determine the target path - directory parameter takes precedence over file
    filepath = work_dir / params["directory"] if "directory" in params else work_dir / params["file"]

    # Route to appropriate match handler
    if "directory" in params:
        calculated_value, reference_value = _handle_directory_matches(filepath, params)
    elif "size" in params:
        calculated_value, reference_value = _handle_file_matches(filepath, params)
    else:
        # Content-based matches require file reading
        try:
            with filepath.open("r", errors="replace") as f:
                lines = f.readlines()
        except (FileNotFoundError, UnicodeDecodeError) as e:
            logging.debug(f"   Error reading file {filepath.name}: {e}")
            return False

        calculated_value, reference_value = _handle_content_matches(lines, params)

    # Check if calculation succeeded
    if calculated_value is None:
        return False

    # Perform comparison and return result
    tolerance = params.get("tol")
    return match_compare_result(name, calculated_value, reference_value, tolerance, extra_indent=extra_indent)
