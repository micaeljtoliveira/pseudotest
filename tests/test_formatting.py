"""Unit tests for pseudotest.formatting."""

import io
import logging
from collections import ChainMap
from pathlib import PosixPath
from unittest.mock import patch

import pytest

from pseudotest.formatting import Colors, OutputFormatter, display_match_result
from pseudotest.results import MatchResult


class TestColorsTTY:
    def test_colors_enabled_on_tty(self):
        """Cover the isatty=True branch of Colors.__init__."""
        fake_tty = io.StringIO()
        fake_tty.isatty = lambda: True
        with patch("sys.stdout", fake_tty):
            c = Colors()
        assert c.BLUE == "\033[34m"
        assert c.RED == "\033[31m"
        assert c.GREEN == "\033[32m"
        assert c.RESET == "\033[0m"


class TestPrintExecutionOutput:
    """Directly call OutputFormatter.print_execution_output to cover edge-case branches."""

    def test_output_files_dont_exist(self, tmp_path, capsys):
        """Cover the 'does not exist' branch."""
        formatter = OutputFormatter()
        formatter.print_execution_output(tmp_path, "test_input.txt")
        captured = capsys.readouterr()
        assert "does not exist" in captured.out

    def test_output_files_empty(self, tmp_path, capsys):
        """Cover the 'is empty' branch."""
        (tmp_path / "stdout").write_text("")
        (tmp_path / "stderr").write_text("")
        formatter = OutputFormatter()
        formatter.print_execution_output(tmp_path, "test_input.txt")
        captured = capsys.readouterr()
        assert "is empty" in captured.out

    def test_output_with_short_content(self, tmp_path, capsys):
        """Cover the branch that prints full content (<=10 lines)."""
        (tmp_path / "stdout").write_text("line 1\nline 2\n")
        (tmp_path / "stderr").write_text("")
        formatter = OutputFormatter()
        formatter.print_execution_output(tmp_path, "test_input.txt")
        captured = capsys.readouterr()
        assert "line 1" in captured.out

    def test_output_read_exception(self, tmp_path, capsys):
        """Cover the except branch when reading the file raises an error."""
        stdout_file = tmp_path / "stdout"
        stdout_file.write_text("some content")
        (tmp_path / "stderr").write_text("")

        # Make read_text raise an exception after the file existence check
        original_read = PosixPath.read_text

        def exploding_read(self, *args, **kwargs):
            if self.name == "stdout":
                raise OSError("Simulated read error")
            return original_read(self, *args, **kwargs)

        with patch.object(PosixPath, "read_text", exploding_read):
            formatter = OutputFormatter()
            formatter.print_execution_output(tmp_path, "test_input.txt")
        # The exception is caught and logged at DEBUG level; nothing printed for stdout


class TestLongExecutionOutput:
    @pytest.fixture
    def work_dir(self, tmp_path):
        (tmp_path / "stdout").write_text("".join(f"line {i}\n" for i in range(20)))
        (tmp_path / "stderr").write_text("")
        return tmp_path

    def test_last_lines_shown(self, work_dir, capsys):
        OutputFormatter().print_execution_output(work_dir, "input.txt")
        out = capsys.readouterr().out
        assert "showing last 10 lines" in out
        assert "line 10\n" in out
        assert "line 9\n" not in out

    def test_all_lines_shown_in_debug(self, work_dir, capsys, caplog):
        caplog.set_level(logging.DEBUG)
        OutputFormatter().print_execution_output(work_dir, "input.txt")
        out = capsys.readouterr().out
        assert "showing last 10 lines" not in out
        assert "line 0\n" in out


class TestDisplayMatchResult:
    def _lines(self, capsys, result):
        display_match_result(result, indent_level=0)
        return [line.strip() for line in capsys.readouterr().out.splitlines()]

    def test_passed(self, capsys):
        lines = self._lines(capsys, MatchResult("energy", ChainMap(), True, "1.0", 1.0, "value"))
        assert lines == ["energy" + " " * 53 + "[ OK ]"]

    def test_tolerance_smaller_than_precision(self, capsys):
        result = MatchResult("short", ChainMap(), False, "1.23", 1.23, "value", 1e-6, 0.0, 0.01, "reason")
        assert self._lines(capsys, result)[1:] == [
            "-" * 45,
            "Unreliable comparison: the tolerance is smaller than the precision of the calculated value",
            "Calculated value    : 1.23",
            "Effective precision : 0.01",
            "Tolerance           : 1e-06",
            "Use a tolerance of at least 0.01, or print the value with more digits",
            "-" * 45,
        ]

    def test_numeric_difference(self, capsys):
        result = MatchResult("energy", ChainMap(), False, "10.0", 20.0, "value", 0.5, 10.0)
        assert self._lines(capsys, result)[2:-1] == [
            "Calculated value : 10.0",
            "Reference value  : 20.0",
            "Difference       : 10.0",
            "Deviation [%]    : 50.000000",
            "Tolerance        : 0.5",
            "Tolerance [%]    : 2.500000",
        ]

    def test_string_difference(self, capsys):
        result = MatchResult("status", ChainMap(), False, "converged", "diverged", "value")
        assert self._lines(capsys, result)[2:-1] == ["Calculated value : 'converged'", "Expected value   : 'diverged'"]

    def test_failed_extraction(self, capsys):
        result = MatchResult("energy", ChainMap(), False, reason="'results.txt' not found")
        assert self._lines(capsys, result)[2:-1] == ["'results.txt' not found"]
