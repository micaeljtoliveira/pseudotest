"""Unit tests for pseudotest.matchers."""

import math
from collections import ChainMap

import pytest

from pseudotest.exceptions import ExtractionError, UsageError
from pseudotest.matchers import (
    _handle_content_from_file,
    handle_content_matches,
    handle_directory_matches,
    handle_file_matches,
    match,
    register_match_handler,
)
from pseudotest.results import MatchResult

# ---------------------------------------------------------------------------
# Sample file content used by multiple tests
# ---------------------------------------------------------------------------

SAMPLE_LINES = [
    "Energy: -42.5000 Ry  0.3  0.4\n",
    "Total force: 1.2345e-03 Ha\n",
    "Status converged OK\n",
    "Iterations 10\n",
    "WARNING: step skipped\n",
    "WARNING: step skipped\n",
]


# ---------------------------------------------------------------------------
# handle_content_matches
# ---------------------------------------------------------------------------


class TestHandleContentMatches:
    @pytest.mark.parametrize(
        ("params", "calculated"),
        [
            ({"grep": "Total force:", "field": 3}, "1.2345e-03"),
            ({"line": 4, "field": 2}, "10"),
            # line: -1 is the last line, so line: -3 is the third line from the end
            ({"line": -3, "field": 2}, "10"),
            ({"line": 1, "column": 9}, "-42.5000"),
            # With grep, line is an offset from the line found
            ({"grep": "Energy:", "line": 1, "field": 3}, "1.2345e-03"),
            # field_re and field_im give the magnitude sqrt(re² + im²)
            ({"grep": "Energy:", "field_re": 4, "field_im": 5}, str(math.sqrt(0.3**2 + 0.4**2))),
        ],
    )
    def test_value_extracted(self, params, calculated):
        assert handle_content_matches(SAMPLE_LINES, ChainMap({**params, "value": 0})) == (calculated, "value")

    def test_grep_count(self):
        assert handle_content_matches(SAMPLE_LINES, ChainMap({"grep": "WARNING", "count": 2})) == ("2", "count")

    @pytest.mark.parametrize(
        ("params", "reason"),
        [
            ({"grep": "Force:", "field": 2}, "'Force:' not found in 'results.txt'"),
            (
                {"grep": "WARNING", "line": 5, "field": 2},
                "No line +5 from the line containing 'WARNING' in 'results.txt'",
            ),
            ({"line": 10, "field": 2}, "No line 10 in 'results.txt', which has 6 lines"),
            ({"grep": "Energy:", "field": 99}, "No field 99 in line 'Energy: -42.5000 Ry  0.3  0.4'"),
            ({"line": 4, "column": 99}, "No column 99 in line 'Iterations 10'"),
            ({"grep": "Energy:", "field_re": 99, "field_im": 5}, "No field 99 in line 'Energy: -42.5000 Ry  0.3  0.4'"),
            ({"grep": "Status", "field_re": 1, "field_im": 2}, "'Status' and 'converged' are not both numbers"),
        ],
    )
    def test_extraction_failure_reason(self, params, reason):
        with pytest.raises(ExtractionError, match=reason.replace("+", r"\+")) as error:
            handle_content_matches(SAMPLE_LINES, ChainMap({**params, "file": "results.txt", "value": 1.0}))
        assert str(error.value) == reason
        assert error.value.reference_key == "value"

    @pytest.mark.parametrize(
        ("params", "message"),
        [
            ({"grep": "Energy:", "field": 2}, "'value' parameter"),
            ({"field": 1, "value": "x"}, "grep.*or.*line"),
            ({"line": 0, "field": 1, "value": "x"}, "1-based"),
            ({"grep": "Energy:", "value": "x"}, "field.*column.*field_re"),
        ],
    )
    def test_usage_error(self, params, message):
        with pytest.raises(UsageError, match=message):
            handle_content_matches(SAMPLE_LINES, ChainMap(params))


# ---------------------------------------------------------------------------
# handle_directory_matches, handle_file_matches and _handle_content_from_file
# ---------------------------------------------------------------------------


@pytest.fixture
def work_dir(tmp_path):
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "a.txt").write_text("a")
    (tmp_path / "output" / "b.txt").write_text("b")
    (tmp_path / "data.bin").write_bytes(b"x" * 100)
    return tmp_path


class TestHandleDirectoryMatches:
    def test_file_is_present(self, work_dir):
        """The calculated value of a file that is present is its name."""
        params = ChainMap({"directory": "output", "file_is_present": "a.txt"})
        assert handle_directory_matches(work_dir, params) == ("a.txt", "file_is_present")

    @pytest.mark.parametrize("directory", ["output", "missing_dir"])
    def test_file_is_not_present(self, work_dir, directory):
        params = ChainMap({"directory": directory, "file_is_present": "missing.txt"})
        with pytest.raises(ExtractionError, match=f"'missing.txt' not found in '{directory}'"):
            handle_directory_matches(work_dir, params)

    def test_count_files(self, work_dir):
        params = ChainMap({"directory": "output", "count_files": 2})
        assert handle_directory_matches(work_dir, params) == ("2", "count_files")

    def test_count_files_of_missing_directory(self, work_dir):
        """A missing directory has no file count, rather than a count of zero."""
        params = ChainMap({"directory": "missing_dir", "count_files": 3})
        with pytest.raises(ExtractionError, match="'missing_dir' not found") as error:
            handle_directory_matches(work_dir, params)
        assert error.value.reference_key == "count_files"

    @pytest.mark.parametrize(
        ("params", "message"),
        [({}, "file_is_present.*count_files"), ({"file_is_present": 42}, "file_is_present.*must be a string")],
    )
    def test_usage_error(self, work_dir, params, message):
        with pytest.raises(UsageError, match=message):
            handle_directory_matches(work_dir, ChainMap({"directory": "output", **params}))


class TestHandleFileMatches:
    def test_size(self, work_dir):
        assert handle_file_matches(work_dir, ChainMap({"file": "data.bin", "size": 100})) == ("100", "size")

    def test_missing_file(self, work_dir):
        with pytest.raises(ExtractionError, match="'missing.bin' not found"):
            handle_file_matches(work_dir, ChainMap({"file": "missing.bin", "size": 100}))


class TestHandleContentFromFile:
    @pytest.mark.parametrize(
        ("params", "reference_key"),
        [({"line": 1, "field": 1, "value": "foo"}, "value"), ({"grep": "x", "count": 1}, "count")],
    )
    def test_missing_file(self, work_dir, params, reference_key):
        with pytest.raises(ExtractionError, match="'missing.txt' not found") as error:
            _handle_content_from_file(work_dir, ChainMap({"file": "missing.txt", **params}))
        assert error.value.reference_key == reference_key

    def test_unreadable_file(self, work_dir):
        """A directory cannot be read as a file."""
        with pytest.raises(ExtractionError, match="'output' cannot be read"):
            _handle_content_from_file(work_dir, ChainMap({"file": "output", "line": 1, "field": 1, "value": "x"}))


# ---------------------------------------------------------------------------
# match()
# ---------------------------------------------------------------------------


class TestMatch:
    def test_passed(self, work_dir):
        (work_dir / "results.txt").write_text("Energy: -42.5000 Ry\n")
        params = ChainMap({"file": "results.txt", "grep": "Energy:", "field": 2, "value": -42.5, "tol": 0.1})
        assert match("energy", params, work_dir) == MatchResult(
            "energy", params, True, "-42.5000", -42.5, "value", 0.1, difference=0.0
        )

    def test_failed_comparison(self, work_dir):
        params = ChainMap({"directory": "output", "count_files": 3})
        result = match("count", params, work_dir)
        assert (result.passed, result.status, result.calculated, result.reference) == (False, "fail", "2", 3)
        assert result.difference == 1.0
        assert result.reason == "Values differ"

    def test_failed_extraction(self, work_dir):
        params = ChainMap({"file": "missing.txt", "grep": "Energy:", "field": 2, "value": 1.5})
        result = match("energy", params, work_dir)
        assert (result.passed, result.calculated, result.reason) == (False, None, "'missing.txt' not found")
        assert (result.reference_key, result.reference) == ("value", 1.5)

    def test_missing_target(self, work_dir):
        params = ChainMap({"grep": "Energy:", "field": 2, "value": 1})
        with pytest.raises(UsageError, match="'file' or 'directory'"):
            match("no_target", params, work_dir)


# ---------------------------------------------------------------------------
# Handlers registered by users
# ---------------------------------------------------------------------------


def _handle_line_count(work_dir, params):
    """The example of a new match type of the developer guide."""
    try:
        lines = (work_dir / params["file"]).read_text().splitlines()
    except OSError as e:
        raise ExtractionError(f"'{params['file']}' cannot be read: {e.strerror}", "line_count") from e
    return str(len(lines)), "line_count"


class TestRegisterMatchHandler:
    def test_registered_handler_takes_precedence_over_builtin(self, tmp_path, restore_match_registry):
        """The built-in content handler accepts any match with 'file', so it must come after the registered ones."""
        register_match_handler(
            predicate=lambda params: "file" in params and "line_count" in params,
            handler=_handle_line_count,
            keys={"file", "line_count"},
            reference_keys={"line_count"},
        )
        (tmp_path / "results.txt").write_text("a\nb\n")
        result = match("lines", ChainMap({"file": "results.txt", "line_count": 2}), tmp_path)
        assert (result.passed, result.calculated, result.reference_key) == (True, "2", "line_count")

        result = match("lines", ChainMap({"file": "missing.txt", "line_count": 2}), tmp_path)
        assert (result.passed, result.reason) == (False, "'missing.txt' cannot be read: No such file or directory")

    def test_builtin_handlers_still_used(self, tmp_path, restore_match_registry):
        register_match_handler(predicate=lambda params: "line_count" in params, handler=_handle_line_count)
        (tmp_path / "results.txt").write_text("Energy: -42.5\n")
        params = ChainMap({"file": "results.txt", "grep": "Energy:", "field": 2, "value": -42.5})
        assert match("energy", params, tmp_path).calculated == "-42.5"
