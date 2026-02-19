"""Unit tests for pseudotest.matchers."""

import math
from collections import ChainMap

import pytest

from pseudotest.exceptions import UsageError
from pseudotest.matchers import (
    _handle_content_from_file,
    handle_content_matches,
    handle_directory_matches,
    handle_file_matches,
    match,
)

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
    def test_missing_value_key_raises(self):
        """Content match with field but no 'value' key → UsageError."""
        lines = ["Energy: -42.5 Ry\n"]
        params = ChainMap({"grep": "Energy:", "field": 2})
        with pytest.raises(UsageError, match="'value' parameter"):
            handle_content_matches(lines, params)

    def test_grep_field(self):
        params = ChainMap({"grep": "Total force:", "field": 3, "value": "1.2345e-03"})
        calc, ref = handle_content_matches(SAMPLE_LINES, params)
        assert calc == "1.2345e-03"
        assert ref == "1.2345e-03"

    def test_grep_count(self):
        params = ChainMap({"grep": "WARNING", "count": 2})
        calc, ref = handle_content_matches(SAMPLE_LINES, params)
        assert calc == "2"
        assert ref == 2

    def test_line_field(self):
        params = ChainMap({"line": 4, "field": 2, "value": 10})
        calc, ref = handle_content_matches(SAMPLE_LINES, params)
        assert calc == "10"
        assert ref == 10

    def test_column_extraction(self):
        params = ChainMap({"line": 1, "column": 9, "value": "-42.5000"})
        calc, ref = handle_content_matches(SAMPLE_LINES, params)
        assert calc == "-42.5000"

    def test_field_re_im_abs(self):
        """field_re + field_im → sqrt(re² + im²)."""
        params = ChainMap({"grep": "Energy:", "field_re": 4, "field_im": 5, "value": 0.5})
        calc, ref = handle_content_matches(SAMPLE_LINES, params)
        assert float(calc) == pytest.approx(math.sqrt(0.3**2 + 0.4**2))
        assert ref == 0.5

    def test_grep_with_line_offset(self):
        """grep + line offset reads the line *after* the match."""
        params = ChainMap({"grep": "Energy:", "line": 1, "field": 3, "value": "1.2345e-03"})
        calc, ref = handle_content_matches(SAMPLE_LINES, params)
        assert calc == "1.2345e-03"

    def test_no_grep_or_line_raises(self):
        params = ChainMap({"field": 1, "value": "x", "file": "f.txt"})
        with pytest.raises(UsageError, match="grep.*or.*line"):
            handle_content_matches(SAMPLE_LINES, params)

    def test_no_field_column_or_complex_raises(self):
        params = ChainMap({"grep": "Energy:", "value": "x"})
        with pytest.raises(UsageError, match="field.*column.*field_re"):
            handle_content_matches(SAMPLE_LINES, params)

    def test_field_out_of_bounds_returns_none(self):
        params = ChainMap({"grep": "Energy:", "field": 99, "value": "x"})
        calc, ref = handle_content_matches(SAMPLE_LINES, params)
        assert calc is None

    def test_field_re_im_none_field(self):
        """field_re out of bounds → calculated_value is None."""
        params = ChainMap({"grep": "Energy:", "field_re": 99, "field_im": 5, "value": 1.0})
        calc, _ = handle_content_matches(SAMPLE_LINES, params)
        assert calc is None

    def test_field_re_im_non_numeric(self):
        """Non-numeric values for field_re/field_im → None."""
        params = ChainMap({"grep": "Status", "field_re": 1, "field_im": 2, "value": 1.0})
        calc, _ = handle_content_matches(SAMPLE_LINES, params)
        assert calc is None


# ---------------------------------------------------------------------------
# handle_directory_matches
# ---------------------------------------------------------------------------


class TestHandleDirectoryMatches:
    def test_directory_missing(self, tmp_path):
        dirpath = tmp_path / "nonexistent"
        params = ChainMap({"file_is_present": "foo.txt"})
        calc, ref = handle_directory_matches(dirpath, params)
        assert calc == "False"
        assert ref == "True"

    def test_file_is_present_found(self, tmp_path):
        d = tmp_path / "output"
        d.mkdir()
        (d / "data.txt").write_text("ok\n")
        params = ChainMap({"file_is_present": "data.txt"})
        calc, ref = handle_directory_matches(d, params)
        assert calc == "True"

    def test_file_is_present_missing(self, tmp_path):
        d = tmp_path / "output"
        d.mkdir()
        params = ChainMap({"file_is_present": "missing.txt"})
        calc, ref = handle_directory_matches(d, params)
        assert calc == "False"

    def test_count_files(self, tmp_path):
        d = tmp_path / "output"
        d.mkdir()
        (d / "a.txt").write_text("a")
        (d / "b.txt").write_text("b")
        params = ChainMap({"count_files": 2})
        calc, ref = handle_directory_matches(d, params)
        assert calc == "2"
        assert ref == 2

    def test_no_predicate_raises(self, tmp_path):
        d = tmp_path / "output"
        d.mkdir()
        params = ChainMap({"directory": "output"})
        with pytest.raises(UsageError, match="file_is_present.*count_files"):
            handle_directory_matches(d, params)

    def test_file_is_present_non_string_raises(self, tmp_path):
        d = tmp_path / "output"
        d.mkdir()
        params = ChainMap({"file_is_present": 42})
        with pytest.raises(UsageError, match="file_is_present.*must be a string"):
            handle_directory_matches(d, params)


# ---------------------------------------------------------------------------
# handle_file_matches
# ---------------------------------------------------------------------------


class TestHandleFileMatches:
    def test_size_match(self, tmp_path):
        f = tmp_path / "data.bin"
        f.write_bytes(b"x" * 100)
        params = ChainMap({"size": 100})
        calc, ref = handle_file_matches(f, params)
        assert calc == "100"
        assert ref == 100

    def test_missing_file_returns_none(self, tmp_path):
        f = tmp_path / "nonexistent.bin"
        params = ChainMap({"size": 100})
        calc, ref = handle_file_matches(f, params)
        assert calc is None


# ---------------------------------------------------------------------------
# _handle_content_from_file — missing output file
# ---------------------------------------------------------------------------


class TestHandleContentFromFile:
    def test_missing_file_returns_none(self, tmp_path):
        filepath = tmp_path / "nonexistent.txt"
        params = ChainMap({"line": 1, "field": 1, "value": "foo"})
        calc, ref = _handle_content_from_file(filepath, params)
        assert calc is None
        assert ref is None


# ---------------------------------------------------------------------------
# match() dispatch — verify the top-level router works
# ---------------------------------------------------------------------------


class TestMatchDispatch:
    def test_file_content_match_via_dispatch(self, tmp_path):
        """Verify match() dispatches to the content handler."""
        f = tmp_path / "results.txt"
        f.write_text("Energy: -42.5000 Ry\n")
        params = ChainMap({"file": "results.txt", "grep": "Energy:", "field": 2, "value": -42.5})
        success, calc = match("energy", params, tmp_path)
        assert success is True
        assert calc == "-42.5000"

    def test_directory_count_via_dispatch(self, tmp_path):
        d = tmp_path / "outdir"
        d.mkdir()
        (d / "a.txt").write_text("a")
        (d / "b.txt").write_text("b")
        params = ChainMap({"directory": "outdir", "count_files": 2})
        success, calc = match("count", params, tmp_path)
        assert success is True

    def test_file_size_via_dispatch(self, tmp_path):
        f = tmp_path / "data.bin"
        f.write_bytes(b"x" * 50)
        params = ChainMap({"file": "data.bin", "size": 50})
        success, calc = match("sz", params, tmp_path)
        assert success is True
