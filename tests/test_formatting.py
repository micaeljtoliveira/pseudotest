"""Unit tests for pseudotest.formatting."""

import io
from pathlib import PosixPath
from unittest.mock import patch

from pseudotest.formatting import Colors, OutputFormatter


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
