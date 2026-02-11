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

from pseudotest.utils import UsageError, display_match_status

# =============================================================================
# Helper Functions
# =============================================================================


def _get_target_line(lines: List[str], line_num: int) -> Optional[str]:
    """Extract target line handling positive and negative indexing.

    Supports both positive line numbers (1-indexed from start) and negative
    line numbers (counted from end). This provides flexible line access
    similar to Python list indexing but with 1-based positive indexing.

    Args:
        lines: File content as list of lines
        line_num: Line number where positive values are 1-indexed from start,
                 negative values count from end (-1 = last line)

    Returns:
        Target line content or None if line number is out of bounds

    Examples:
        >>> lines = ["first", "second", "third"]
        >>> _get_target_line(lines, 1)  # "first"
        >>> _get_target_line(lines, -1)  # "third"
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


def _find_pattern_line_index(lines: List[str], pattern: str) -> Optional[int]:
    """Find the index of the first line containing the pattern.

    Performs simple substring matching to locate the first occurrence
    of the pattern within any line of the input text.

    Args:
        lines: File content as list of lines
        pattern: Text pattern to search for (case-sensitive substring match)

    Returns:
        Zero-based line index of first match, or None if pattern not found

    Examples:
        >>> lines = ["hello world", "test pattern", "final line"]
        >>> _find_pattern_line_index(lines, "pattern")  # Returns 1
        >>> _find_pattern_line_index(lines, "missing")  # Returns None
    """
    for i, line in enumerate(lines):
        if pattern in line:
            return i
    return None


# =============================================================================
# Line-Based Matchers
# =============================================================================


def line_matcher(lines: List[str], params: List[Any]) -> Optional[str]:
    """Extract the first token starting from a specific column position in a line.

    Similar to the shell command: cut -c<column>- <file> | awk '{print $1}'
    Extracts a substring from the specified column position to the end of the line,
    then returns the first whitespace-separated token from that substring.

    Args:
        lines: File content as list of lines
        params: [line_number, column_position] where:
               - line_number: 1-indexed line number (supports negative indexing)
               - column_position: 1-indexed character position to start extraction

    Returns:
        First whitespace-separated token from the specified position,
        or None if extraction fails (line/column out of bounds)

    Examples:
        >>> lines = ["  hello world test"]
        >>> line_matcher(lines, [1, 3])  # "hello" (starts from column 3)
        >>> line_matcher(lines, [1, 9])  # "world" (starts from column 9)
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
    """Extract a specific whitespace-separated field from a target line.

    Splits the target line on whitespace and extracts the field at the
    specified position. Similar to: awk '{print $N}' where N is the field number.

    Args:
        lines: File content as list of lines
        params: [line_number, field_number] where:
               - line_number: 1-indexed line number (supports negative indexing)
               - field_number: 1-indexed field position after whitespace splitting

    Returns:
        Content of the specified field as string, or None if line doesn't exist
        or field number is out of bounds

    Examples:
        >>> lines = ["first second third"]
        >>> linefield_matcher(lines, [1, 2])  # "second"
        >>> linefield_matcher(lines, [1, 5])  # None (field doesn't exist)
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
    """Calculate absolute value from real and imaginary parts in separate fields.

    Extracts real and imaginary components from specified fields in a line,
    then calculates the absolute value: sqrt(real² + imag²). Useful for
    processing complex number outputs from scientific computations.

    Args:
        lines: File content as list of lines
        params: [line_number, real_field_number, imaginary_field_number] where:
               - line_number: 1-indexed line number (supports negative indexing)
               - real_field_number: 1-indexed field containing real part
               - imaginary_field_number: 1-indexed field containing imaginary part

    Returns:
        String representation of absolute value, or None if line doesn't exist,
        fields are out of bounds, or values cannot be converted to float

    Examples:
        >>> lines = ["result: 3.0 4.0 units"]
        >>> linefield_abs_matcher(lines, [1, 2, 3])  # "5.0" (sqrt(3² + 4²))
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


# =============================================================================
# Grep-Based Matchers
# =============================================================================


def grep_matcher(lines: List[str], params: List[Any]) -> Optional[str]:
    """Find pattern and extract first token from specified column in offset line.

    Searches for the first line containing the pattern, navigates to a line
    at the specified offset, extracts substring from column position, and
    returns the first whitespace-separated token from that substring.

    Args:
        lines: File content as list of lines
        params: [pattern, column_position, line_offset] where:
               - pattern: Text pattern to search for (substring match)
               - column_position: 1-indexed character position to start extraction
               - line_offset: Line offset from pattern match (0=same line, 1=next line, etc.)

    Returns:
        First whitespace-separated token from the specified position,
        or None if pattern not found, offset line doesn't exist, or column out of bounds

    Examples:
        >>> lines = ["HEADER", "  value1 value2"]
        >>> grep_matcher(lines, ["HEADER", 3, 1])  # "value1"
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
    target_index = match_index + 1 + line_offset
    target_line = _get_target_line(lines, target_index)
    if target_line is None:
        return None

    # Extract from byte position (column is 1-indexed)
    if column_pos > len(target_line):
        return None

    # Extract substring from column position onwards
    substring = target_line[column_pos - 1 :].lstrip()

    # Get first whitespace-separated token
    return substring.split()[0] if substring.split() else ""


def grepfield_matcher(lines: List[str], params: List[Any]) -> Optional[str]:
    """Find a pattern and extract a whitespace-separated field from an offset line.

    Searches for the first line containing the pattern, then extracts a specific
    field from a line at the given offset from the match. Fields are determined
    by splitting the line on whitespace.

    Args:
        lines: File content as list of lines
        params: [pattern, field_number, line_offset] where:
               - pattern: Text pattern to search for (substring match)
               - field_number: 1-indexed field position in the target line
               - line_offset: Line offset from pattern match (0=same line, 1=next line, etc.)

    Returns:
        Extracted field content as string, or None if pattern not found,
        offset line doesn't exist, or field number is out of bounds

    Examples:
        >>> lines = ["START", "field1 field2 field3"]
        >>> grepfield_matcher(lines, ["START", 2, 1])  # "field2"
    """
    pattern = params[0]
    field = params[1]
    offset = params[2]

    logging.debug(f"   Grepfield match: pattern={pattern}, field={field}, offset={offset}")

    # Find the first line matching the pattern
    match_index = _find_pattern_line_index(lines, pattern)
    if match_index is None:
        return None

    # Get the line at offset from the match
    target_index = match_index + 1 + offset
    target_line = _get_target_line(lines, target_index)
    if target_line is None:
        return None

    # Split line into fields (whitespace-separated)
    fields = target_line.split()

    # Extract the specified field (1-indexed)
    if field < 1 or field > len(fields):
        return None

    return fields[field - 1]


def grepcount_matcher(lines: List[str], params: List[Any]) -> Optional[str]:
    """Count the number of lines containing a specific pattern.

    Performs substring matching to count how many lines contain the pattern.
    Similar to: grep -c "pattern" file

    Args:
        lines: File content as list of lines
        params: [pattern] where:
               - pattern: Text pattern to search for (substring match)

    Returns:
        String representation of the count of matching lines.
        Always returns a valid count ("0" if no matches found).

    Examples:
        >>> lines = ["test line", "another test", "final line"]
        >>> grepcount_matcher(lines, ["test"])  # "2"
        >>> grepcount_matcher(lines, ["missing"])  # "0"
    """
    pattern = params[0]

    logging.debug(f"   Grepcount match: pattern={pattern}")

    # Count lines containing the pattern
    return str(sum(1 for line in lines if pattern in line))


# =============================================================================
# File and Directory Matchers
# =============================================================================


def size_matcher(file_path: Path, params: List[Any]) -> Optional[str]:
    """Get file size in bytes for any file type.

    Uses filesystem metadata to determine file size, which works efficiently
    for both text and binary files without reading file contents.

    Args:
        file_path: Path object pointing to the file to measure
        params: Empty list (not used, kept for interface consistency)

    Returns:
        String representation of file size in bytes, or None if file
        doesn't exist or cannot be accessed due to permissions

    Examples:
        >>> size_matcher(Path("config.txt"), [])  # "1024"
        >>> size_matcher(Path("missing.txt"), [])  # None
    """
    try:
        # Get actual file size in bytes - works for both text and binary files
        file_size = file_path.stat().st_size
        return str(file_size)
    except (FileNotFoundError, OSError):
        return None


def directory_matcher(dir_path: Path, params: List[Any]) -> Optional[str]:
    """Count the number of files in a directory, excluding subdirectories.

    Performs a shallow scan of the directory to count only regular files,
    ignoring subdirectories, symbolic links, and special files.

    Args:
        dir_path: Path object pointing to the directory to scan
        params: Empty list (not used, kept for interface consistency)

    Returns:
        String representation of file count in directory, or None if
        path doesn't exist, isn't a directory, or cannot be accessed

    Examples:
        >>> directory_matcher(Path("./data"), [])  # "5" (if 5 files present)
        >>> directory_matcher(Path("./missing"), [])  # None
    """
    try:
        if not dir_path.is_dir():
            return None

        # Count only files, not subdirectories
        file_count = sum(1 for item in dir_path.iterdir() if item.is_file())
        return str(file_count)
    except (FileNotFoundError, OSError, PermissionError):
        return None


def directory_file_matcher(dir_path: Path, params: List[Any]) -> Optional[str]:
    """Check if a specific file exists within a directory.

    Validates the presence of a named file within the specified directory.
    Only checks for regular files, not subdirectories or other file types.

    Args:
        dir_path: Path object pointing to the directory to search in
        params: [filename] where:
               - filename: Name of the file to check for (string)

    Returns:
        "True" if the specified file exists in the directory,
        "False" if file doesn't exist, directory doesn't exist,
        or there are permission/access issues

    Examples:
        >>> directory_file_matcher(Path("./data"), ["config.txt"])  # "True" or "False"
        >>> directory_file_matcher(Path("./missing"), ["any.txt"])   # "False"
    """
    try:
        if not dir_path.is_dir():
            return "False"

        filename = params[0]
        if not isinstance(filename, str):
            return "False"

        # Check that the specified file exists in the directory
        file_path = dir_path / filename
        if not file_path.is_file():
            return "False"

        return "True"
    except (FileNotFoundError, OSError, PermissionError, IndexError, TypeError):
        return "False"


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


def _handle_directory_matches(filepath: Path, params: ChainMap[str, Any]) -> tuple[str | None, Any]:
    """Handle directory-based matches and return calculated and reference values"""
    if "file_is_present" in params:
        calculated_value = directory_file_matcher(filepath, [params["file_is_present"]])
        reference_value = "True"
    elif "count_files" in params:
        calculated_value = directory_matcher(filepath, [])
        reference_value = params["count_files"]
    else:
        raise UsageError("Directory parameter requires either 'file_is_present' or 'count_files'")
    return calculated_value, reference_value


def _handle_file_matches(filepath: Path, params: ChainMap[str, Any]) -> tuple[str | None, Any]:
    """Handle file-based matches (size) and return calculated and reference values"""
    calculated_value = size_matcher(filepath, [])
    reference_value = params["size"]
    return calculated_value, reference_value


def _handle_content_matches(lines: List[str], params: ChainMap[str, Any]) -> tuple[str | None, Any]:
    """Handle content-based matches and return calculated and reference values"""
    # Determine match type and get reference value
    if "grep" in params and "field" in params and "line" in params:
        calculated_value = grepfield_matcher(lines, [params["grep"], params["field"], params["line"]])
        reference_value = params.get("value")
    elif "grep" in params and "column" in params and "line" in params:
        calculated_value = grep_matcher(lines, [params["grep"], params["column"], params["line"]])
        reference_value = params.get("value")
    elif "grep" in params and "count" in params:
        calculated_value = grepcount_matcher(lines, [params["grep"]])
        reference_value = params["count"]
    elif "line" in params and "field" in params:
        calculated_value = linefield_matcher(lines, [params["line"], params["field"]])
        reference_value = params.get("value")
    elif "line" in params and "column" in params:
        calculated_value = line_matcher(lines, [params["line"], params["column"]])
        reference_value = params.get("value")
    elif "line" in params and "field_re" in params and "field_im" in params:
        calculated_value = linefield_abs_matcher(lines, [params["line"], params["field_re"], params["field_im"]])
        reference_value = params.get("value")
    else:
        raise UsageError("Invalid match parameters")
    return calculated_value, reference_value


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
