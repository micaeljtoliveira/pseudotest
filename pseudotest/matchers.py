"""Match handlers and extensible dispatch for pseudotest.

This module owns the mapping from match parameters to handler functions and the top-level ``match()`` entry point.
The actual value extraction and comparison live in dedicated modules.

New match types can be added by registering a handler function via ``register_match_handler()``.
"""

import logging
import math
from collections import ChainMap
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pseudotest.comparator import match_compare_result
from pseudotest.exceptions import UsageError
from pseudotest.value_extractors import (
    extract_column_from_line,
    extract_field_from_line,
    find_pattern_line,
    get_target_line,
)

# =============================================================================
# Handler registry
# =============================================================================

MatchPredicate = Callable[[ChainMap[str, Any]], bool]
MatchHandler = Callable[[Path, ChainMap[str, Any]], tuple[str | None, Any]]

_MATCH_HANDLERS: list[tuple[MatchPredicate, MatchHandler]] = []


def register_match_handler(predicate: MatchPredicate, handler: MatchHandler) -> None:
    """Register a match handler with an explicit selection predicate.

    Handlers are evaluated in registration order; the first whose
    *predicate(params)* returns ``True`` wins.

    Args:
        predicate: A callable ``(params) -> bool`` that returns True when
                   *handler* should process this match.
        handler: A callable ``(Path, ChainMap) -> (str | None, Any)``
                 that computes the (calculated, reference) value pair.
    """
    _MATCH_HANDLERS.append((predicate, handler))


# =============================================================================
# Built-in match handlers
# =============================================================================


def handle_directory_matches(dirpath: Path, params: ChainMap[str, Any]) -> tuple[str | None, Any]:
    """Handle directory-based matches and return calculated and reference values.

    Supports two types of directory operations:
    - file_is_present: Check if a specific file exists in the directory
    - count_files: Count the number of files (excluding subdirectories)

    Args:
        dirpath: Path to the directory to examine
        params: Match parameters containing either 'file_is_present' or 'count_files'

    Returns:
        Tuple of (calculated_value, reference_value)

    Raises:
        UsageError: If neither 'file_is_present' nor 'count_files' is provided,
                   or if 'file_is_present' parameter is not a string
    """
    if not dirpath.is_dir():
        calculated_value = "False"
        reference_value = "True"

    elif "file_is_present" in params:
        filename = params["file_is_present"]
        if not isinstance(filename, str):
            raise UsageError("file_is_present parameter must be a string")

        file_path = dirpath / filename
        calculated_value = "False" if not file_path.is_file() else "True"
        reference_value = "True"

    elif "count_files" in params:
        file_count = sum(1 for item in dirpath.iterdir() if item.is_file())
        calculated_value = str(file_count)
        reference_value = params["count_files"]

    else:
        raise UsageError("Directory parameter requires either 'file_is_present' or 'count_files'")

    return calculated_value, reference_value


def handle_file_matches(filepath: Path, params: ChainMap[str, Any]) -> tuple[str | None, Any]:
    """Handle file-based matches (size) and return calculated and reference values.

    Args:
        filepath: Path to the file to examine
        params: Match parameters containing 'size' for expected file size

    Returns:
        Tuple of (calculated_value, reference_value)
    """
    try:
        file_size = filepath.stat().st_size
        calculated_value = str(file_size)
    except (FileNotFoundError, OSError):
        calculated_value = None

    reference_value = params["size"]
    return calculated_value, reference_value


def handle_content_matches(lines: list[str], params: ChainMap[str, Any]) -> tuple[str | None, Any]:
    """Handle content-based matches and return calculated and reference values.

    Supports pattern searching, line indexing, field extraction, column
    extraction, and complex-number absolute-value calculation.

    Args:
        lines: File content as list of lines
        params: Match parameters containing extraction and reference specs

    Returns:
        Tuple of (calculated_value, reference_value) where calculated_value
        may be None if extraction fails

    Raises:
        UsageError: If required parameters are missing or invalid
    """
    # Grep count takes precedence over all other content-based matches
    if "grep" in params and "count" in params:
        calculated_value = str(sum(1 for line in lines if params["grep"] in line))
        return calculated_value, params["count"]

    # Get line content based on grep or line parameters
    if "grep" in params:
        offset = params.get("line", 0)
        line = find_pattern_line(lines, params["grep"], offset)
    elif "line" in params:
        line = get_target_line(lines, params["line"] - 1)
    else:
        raise UsageError("Content-based match requires either 'grep' or 'line' parameter")

    # Extract the value based on field, column, or field_re/field_im
    if "field" in params:
        calculated_value = extract_field_from_line(line, params["field"])
    elif "column" in params:
        calculated_value = extract_column_from_line(line, params["column"])
    elif "field_re" in params and "field_im" in params:
        real_field = extract_field_from_line(line, params["field_re"])
        imag_field = extract_field_from_line(line, params["field_im"])
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


# ---------------------------------------------------------------------------
# Internal: read-and-match for content-based handlers
# ---------------------------------------------------------------------------


def _handle_content_from_file(filepath: Path, params: ChainMap[str, Any]) -> tuple[str | None, Any]:
    """Read *filepath* and delegate to :func:`handle_content_matches`.

    Returns ``(None, None)`` when the file cannot be read, which causes the
    top-level ``match()`` to report a failure.
    """
    try:
        with filepath.open("r", errors="replace") as f:
            lines = f.readlines()
    except (FileNotFoundError, UnicodeDecodeError) as e:
        logging.debug(f"   Error reading file {filepath.name}: {e}")
        return None, None

    return handle_content_matches(lines, params)


# ---------------------------------------------------------------------------
# Register built-in handlers
# ---------------------------------------------------------------------------

register_match_handler(
    predicate=lambda params: "directory" in params,
    handler=handle_directory_matches,
)
register_match_handler(
    predicate=lambda params: "file" in params and "size" in params,
    handler=handle_file_matches,
)
register_match_handler(
    predicate=lambda params: "file" in params and "size" not in params,
    handler=_handle_content_from_file,
)


# =============================================================================
# Main match entry point
# =============================================================================


def match(name: str, params: ChainMap[str, Any], work_dir: Path, extra_indent: int = 0) -> bool:
    """Execute a match operation and compare the result against the expected value.

    Routes to the appropriate registered handler based on the parameter keys.

    Args:
        name: Descriptive name for the match (used in output display)
        params: Configuration parameters (target, match type, expected value, …)
        work_dir: Working directory containing the target files
        extra_indent: Additional indentation for nested output display

    Returns:
        True if match succeeds, False otherwise.
    """
    # Determine the target path — directory parameter takes precedence over file
    filepath = work_dir / params["directory"] if "directory" in params else work_dir / params["file"]

    # Route to the first registered handler whose predicate matches
    for predicate, handler in _MATCH_HANDLERS:
        if predicate(params):
            calculated_value, reference_value = handler(filepath, params)
            break
    else:
        raise UsageError(f"No registered match handler for params: {dict(params)}")

    # Check if calculation succeeded
    if calculated_value is None:
        return False

    # Perform comparison and return result
    tolerance = params.get("tol")
    return match_compare_result(name, calculated_value, reference_value, tolerance, extra_indent=extra_indent)
