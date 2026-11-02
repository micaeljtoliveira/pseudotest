"""Match handlers and extensible dispatch for pseudotest.

This module owns the mapping from match parameters to handler functions and the top-level ``match()`` entry point.
The actual value extraction and comparison live in dedicated modules.

New match types can be added by registering a handler function via ``register_match_handler()``.
"""

import math
from collections import ChainMap
from collections.abc import Callable
from itertools import chain
from pathlib import Path
from typing import Any

from pseudotest.comparator import compare
from pseudotest.exceptions import ExtractionError, UsageError
from pseudotest.results import MatchResult
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
# (work_dir, params) -> (calculated_value, reference_key), raising ExtractionError when no value can be extracted
MatchHandler = Callable[[Path, ChainMap[str, Any]], tuple[str, str]]

# Handlers registered by users, which are evaluated before the built-in ones
_MATCH_HANDLERS: list[tuple[MatchPredicate, MatchHandler]] = []
_BUILTIN_MATCH_HANDLERS: list[tuple[MatchPredicate, MatchHandler]] = []

# Accumulated key sets. These are populated by register_match_handler()
RESERVED_KEYS: set[str] = set()
REFERENCE_KEYS: set[str] = set()
INTERNAL_KEYS: set[str] = set()
NON_UPDATABLE_KEYS: set[str] = set()


def _register_keys(
    keys: set[str] | None = None,
    reference_keys: set[str] | None = None,
    internal_keys: set[str] | None = None,
    non_updatable_keys: set[str] | None = None,
) -> None:
    """Add the keys of a match handler to the key sets, see :func:`register_match_handler`."""
    if keys:
        RESERVED_KEYS.update(keys)
    if reference_keys:
        REFERENCE_KEYS.update(reference_keys)
    if internal_keys:
        INTERNAL_KEYS.update(internal_keys)
        RESERVED_KEYS.update(internal_keys)
    if non_updatable_keys:
        NON_UPDATABLE_KEYS.update(non_updatable_keys)


def register_match_handler(
    predicate: MatchPredicate,
    handler: MatchHandler,
    *,
    keys: set[str] | None = None,
    reference_keys: set[str] | None = None,
    internal_keys: set[str] | None = None,
    non_updatable_keys: set[str] | None = None,
) -> None:
    """Register a match handler with an explicit selection predicate.

    Handlers are evaluated in registration order, before the built-in ones,
    which handle any match with a ``file`` or a ``directory``; the first
    whose *predicate(params)* returns ``True`` wins.

    Args:
        predicate: A callable ``(params) -> bool`` that returns True when
                   *handler* should process this match.
        handler: A callable ``(work_dir, params) -> (calculated, reference_key)``
                 that extracts the calculated value from the files of the
                 working directory, and returns it with the parameter
                 holding the reference value. It raises
                 :class:`~pseudotest.exceptions.ExtractionError` when no
                 value can be extracted.
        keys: Parameter keys recognised by this handler
              (added to :data:`RESERVED_KEYS`).
        reference_keys: Subset of *keys* that hold a reference value
                        (added to :data:`REFERENCE_KEYS`).
        internal_keys: Subset of *keys* that are internal and should not
                       appear in reports (added to :data:`INTERNAL_KEYS`).
        non_updatable_keys: Subset of *reference_keys* whose values should
                            never be modified by ``pseudotest-update``
                            (added to :data:`NON_UPDATABLE_KEYS`).
    """
    _MATCH_HANDLERS.append((predicate, handler))
    _register_keys(keys, reference_keys, internal_keys, non_updatable_keys)


def _register_builtin_handler(predicate: MatchPredicate, handler: MatchHandler, **key_sets: set[str]) -> None:
    """Register a built-in match handler, evaluated after those registered with :func:`register_match_handler`."""
    _BUILTIN_MATCH_HANDLERS.append((predicate, handler))
    _register_keys(**key_sets)


# =============================================================================
# Built-in match handlers
# =============================================================================


def _cannot_read(name: str, error: OSError, reference_key: str) -> ExtractionError:
    """Return the extraction error of a file or directory *name* that cannot be read."""
    if isinstance(error, FileNotFoundError):
        return ExtractionError(f"'{name}' not found", reference_key)
    return ExtractionError(f"'{name}' cannot be read: {error.strerror}", reference_key)


def handle_directory_matches(work_dir: Path, params: ChainMap[str, Any]) -> tuple[str, str]:
    """Handle directory-based matches.

    Supports two types of directory operations:
    - file_is_present: Check if a specific file exists in the directory; the
      calculated value is the name of the file
    - count_files: Count the number of files (excluding subdirectories)

    Args:
        work_dir: Working directory, containing the directory to examine
        params: Match parameters containing 'directory', and either 'file_is_present' or 'count_files'

    Returns:
        Tuple of (calculated_value, reference_key)

    Raises:
        ExtractionError: If the file or the directory does not exist
        UsageError: If neither 'file_is_present' nor 'count_files' is provided,
                   or if 'file_is_present' parameter is not a string
    """
    directory = params["directory"]
    dirpath = work_dir / directory

    if "file_is_present" in params:
        filename = params["file_is_present"]
        if not isinstance(filename, str):
            raise UsageError("file_is_present parameter must be a string")
        # A file inside a missing directory is not present either
        if not (dirpath / filename).is_file():
            raise ExtractionError(f"'{filename}' not found in '{directory}'", "file_is_present")
        return filename, "file_is_present"

    if "count_files" in params:
        try:
            file_count = sum(1 for item in dirpath.iterdir() if item.is_file())
        except OSError as e:
            raise _cannot_read(directory, e, "count_files") from e
        return str(file_count), "count_files"

    raise UsageError("Directory parameter requires either 'file_is_present' or 'count_files'")


def handle_file_matches(work_dir: Path, params: ChainMap[str, Any]) -> tuple[str, str]:
    """Handle file-based matches (size).

    Args:
        work_dir: Working directory, containing the file to examine
        params: Match parameters containing 'file', and 'size' for expected file size

    Returns:
        Tuple of (calculated_value, reference_key)

    Raises:
        ExtractionError: If the file does not exist
    """
    try:
        return str((work_dir / params["file"]).stat().st_size), "size"
    except OSError as e:
        raise _cannot_read(params["file"], e, "size") from e


def _select_line(lines: list[str], params: ChainMap[str, Any], reference_key: str) -> str:
    """Return the line selected by the 'grep' and 'line' parameters.

    Raises:
        ExtractionError: If the line does not exist
        UsageError: If neither 'grep' nor 'line' is given, or if 'line' is 0
    """
    file = params.get("file")
    if "grep" in params:
        # With grep, 'line' is an offset from the first line containing the pattern
        pattern = params["grep"]
        offset = params.get("line", 0)
        line = find_pattern_line(lines, pattern, offset)
        if line is not None:
            return line
        if any(pattern in line for line in lines):
            raise ExtractionError(
                f"No line {offset:+d} from the line containing '{pattern}' in '{file}'", reference_key
            )
        raise ExtractionError(f"'{pattern}' not found in '{file}'", reference_key)

    if "line" in params:
        # 1-based from the start, or counted from the end when negative (-1 = last line)
        line_num = params["line"]
        if line_num == 0:
            raise UsageError("'line' is 1-based: use a positive number, or a negative one to count from the end")
        line = get_target_line(lines, line_num - 1 if line_num > 0 else line_num)
        if line is None:
            raise ExtractionError(f"No line {line_num} in '{file}', which has {len(lines)} lines", reference_key)
        return line

    raise UsageError("Content-based match requires either 'grep' or 'line' parameter")


def _extract_field(line: str, field: int, reference_key: str) -> str:
    """Return the 1-based *field* of *line*, or raise ExtractionError if it does not exist."""
    value = extract_field_from_line(line, field)
    if value is None:
        raise ExtractionError(f"No field {field} in line '{line.strip()}'", reference_key)
    return value


def handle_content_matches(lines: list[str], params: ChainMap[str, Any]) -> tuple[str, str]:
    """Handle content-based matches.

    Supports pattern searching, line indexing, field extraction, column
    extraction, and complex-number absolute-value calculation.

    Args:
        lines: File content as list of lines
        params: Match parameters containing extraction and reference specs

    Returns:
        Tuple of (calculated_value, reference_key)

    Raises:
        ExtractionError: If the line, field or column does not exist
        UsageError: If required parameters are missing or invalid
    """
    # Grep count takes precedence over all other content-based matches
    if "grep" in params and "count" in params:
        return str(sum(1 for line in lines if params["grep"] in line)), "count"

    if "value" not in params:
        raise UsageError("Content-based match requires 'value' parameter for reference value")

    line = _select_line(lines, params, "value")

    # Extract the value based on field, column, or field_re/field_im
    if "field" in params:
        return _extract_field(line, params["field"], "value"), "value"

    if "column" in params:
        value = extract_column_from_line(line, params["column"])
        if value is None:
            raise ExtractionError(f"No column {params['column']} in line '{line.rstrip()}'", "value")
        return value, "value"

    if "field_re" in params and "field_im" in params:
        real_field = _extract_field(line, params["field_re"], "value")
        imag_field = _extract_field(line, params["field_im"], "value")
        try:
            real_part = float(real_field)
            imag_part = float(imag_field)
        except ValueError as e:
            raise ExtractionError(f"'{real_field}' and '{imag_field}' are not both numbers", "value") from e
        return str(math.sqrt(real_part**2 + imag_part**2)), "value"

    raise UsageError("Content-based match requires 'field', 'column', or both 'field_re' and 'field_im' parameters")


def _handle_content_from_file(work_dir: Path, params: ChainMap[str, Any]) -> tuple[str, str]:
    """Read the file of the match and delegate to :func:`handle_content_matches`."""
    reference_key = "count" if "grep" in params and "count" in params else "value"
    try:
        with (work_dir / params["file"]).open("r", errors="replace") as f:
            lines = f.readlines()
    except OSError as e:
        raise _cannot_read(params["file"], e, reference_key) from e

    return handle_content_matches(lines, params)


# ---------------------------------------------------------------------------
# Register built-in handlers
# ---------------------------------------------------------------------------

# Shared keys used across all handlers
_register_keys(keys={"tol", "protected"}, internal_keys={"match"})

_register_builtin_handler(
    predicate=lambda params: "directory" in params,
    handler=handle_directory_matches,
    keys={"directory", "count_files", "file_is_present"},
    reference_keys={"count_files", "file_is_present"},
    non_updatable_keys={"file_is_present"},
)
_register_builtin_handler(
    predicate=lambda params: "file" in params and "size" in params,
    handler=handle_file_matches,
    keys={"file", "size"},
    reference_keys={"size"},
)
_register_builtin_handler(
    predicate=lambda params: "file" in params and "size" not in params,
    handler=_handle_content_from_file,
    keys={"file", "grep", "field", "column", "line", "field_re", "field_im", "value", "count"},
    reference_keys={"value", "count"},
)


# =============================================================================
# Main match entry point
# =============================================================================


def match(name: str, params: ChainMap[str, Any], work_dir: Path) -> MatchResult:
    """Evaluate a match: extract its value and compare it against its reference.

    Routes to the first registered handler whose predicate accepts the parameters.

    Args:
        name: Name of the match
        params: Configuration parameters (target, match type, expected value, …)
        work_dir: Working directory containing the target files

    Returns:
        The result of the match, which failed when no value could be extracted.

    Raises:
        UsageError: If no handler accepts the parameters, or they are invalid
    """
    handlers = chain(_MATCH_HANDLERS, _BUILTIN_MATCH_HANDLERS)
    handler = next((handler for predicate, handler in handlers if predicate(params)), None)
    if handler is None:
        raise UsageError(f"Match '{name}' requires a 'file' or 'directory' parameter")

    try:
        calculated_value, reference_key = handler(work_dir, params)
    except ExtractionError as e:
        reference = params.get(e.reference_key) if e.reference_key else None
        return MatchResult(name, params, False, reference=reference, reference_key=e.reference_key, reason=str(e))

    reference_value = params[reference_key]
    tolerance = params.get("tol")
    comparison = compare(calculated_value, reference_value, tolerance)
    return MatchResult(
        name,
        params,
        comparison.passed,
        calculated_value,
        reference_value,
        reference_key,
        tolerance,
        comparison.difference,
        comparison.precision,
        comparison.reason,
    )
