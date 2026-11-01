"""End-to-end tests of errors: mistakes in test files, exit codes, and the installed command-line scripts."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from pseudotest.exceptions import ExitCode

ENERGY = "energy: {file: results.txt, grep: 'Energy:', field: 2, value: -42.5000}"


class TestTestFileErrors:
    """Mistakes in the test file are usage errors, reported in one line, without leaving a working directory."""

    @pytest.mark.parametrize(
        ("matches", "message"),
        [
            # A misspelled parameter used to turn the match into a group
            (
                "energy: {fiel: results.txt, grep: 'Energy:', field: 2, value: -42.5}",
                "Unknown match parameter 'fiel' in 'Inputs > input.txt > Matches > energy'",
            ),
            (
                "results: {fiel: results.txt, energy: {grep: 'Energy:', field: 2, value: -42.5}}",
                "Unknown match parameter 'fiel' in 'Inputs > input.txt > Matches > results'",
            ),
            # 'matches' is not the key naming broadcast elements
            (
                "multi: {matches: [a, b], file: results.txt, line: [1, 2], field: 2, value: [1, 2]}",
                "Unknown match parameter 'matches'",
            ),
            ("energy: {grep: 'Energy:', field: 2, value: -42.5}", "requires a 'file' or 'directory' parameter"),
            ("energy: {file: results.txt, line: 0, field: 2, value: -42.5}", "'line' is 1-based"),
            ("energy:", "Match 'Inputs > input.txt > Matches > energy' has no parameters"),
            # A match named after a parameter used to be passed down as a parameter
            (
                "count: {directory: output_dir, count_files: 2}",
                "Match 'Inputs > input.txt > Matches > count' is named after a match parameter",
            ),
        ],
    )
    def test_invalid_match(self, ws, matches, message):
        ws.mock()
        ws.matches(matches)
        result = ws.run()
        assert result.rc == ExitCode.USAGE
        assert message in result.log
        assert list(ws.work_root.iterdir()) == []

    @pytest.mark.parametrize(
        ("inputs", "message"),
        [
            ("input.txt:\n    ExtraFiles: [missing.dat]", "Extra file not found"),
            ("missing.txt: {}", "Input file not found"),
            ("input.txt:\n    Executable: missing.py", "Executable 'missing.py' not available"),
            ("input.txt:\n    InputMethod: rename", "uses InputMethod 'rename' but has no 'RenameTo'"),
            ("input.txt:\n    Matches: [energy]", "'Matches' of input 'input.txt' must be a mapping of matches"),
            # A default placed under Inputs would be run as an input
            ("ExpectedFailure: true\n  input.txt: {}", "Parameters of input 'ExpectedFailure' must be a mapping"),
        ],
    )
    def test_invalid_input(self, ws, inputs, message):
        ws.mock()
        ws.config(f"Name: Invalid input\nExecutable: mock.py\nInputs:\n  {inputs}\n")
        result = ws.run()
        assert result.rc == ExitCode.USAGE
        assert message in result.log
        assert list(ws.work_root.iterdir()) == []

    @pytest.mark.parametrize(
        ("content", "message"),
        [
            (None, "Test file not found"),
            ("Name: [unbalanced", "Failed to load test file"),
            ("Executable: mock.py\nInputs: {}\n", "has no 'Name'"),
            ("Name: No inputs\nExecutable: mock.py\n", "'Inputs' must be a mapping"),
        ],
        ids=["missing", "invalid-yaml", "no-name", "no-inputs"],
    )
    def test_invalid_test_file(self, ws, content, message):
        if content is not None:
            ws.config(content)
        result = ws.run()
        assert result.rc == ExitCode.USAGE
        assert message in result.log


class TestCommandLineErrors:
    def test_update_modes_are_exclusive(self, ws):
        with pytest.raises(SystemExit) as exit_info:
            ws.update("-t", "-r")
        assert exit_info.value.code == ExitCode.USAGE

    def test_update_mode_is_required(self, ws):
        with pytest.raises(SystemExit) as exit_info:
            ws.update("--timeout", "10")
        assert exit_info.value.code == ExitCode.USAGE


# ---------------------------------------------------------------------------
# Installed scripts
# ---------------------------------------------------------------------------


def installed_command(name: str) -> list[str]:
    """Return the command running the script *name* installed with the Python running the tests."""
    script = Path(sys.executable).parent / name
    if not script.exists():
        pytest.skip(f"{name} is not installed next to {sys.executable}")
    return [str(script)]


COMMANDS = {
    "pseudotest": lambda: installed_command("pseudotest"),
    "pseudotest-update": lambda: [*installed_command("pseudotest-update"), "-r"],
    "python-m-pseudotest": lambda: [sys.executable, "-m", "pseudotest"],
}


class TestInstalledScripts:
    """The scripts installed by pip handle errors as main() does, which was not the case of the entry points."""

    def _run(self, ws, command: list[str]) -> subprocess.CompletedProcess:
        env = {**os.environ, "TMPDIR": str(ws.work_root)}
        return subprocess.run(
            [*command, str(ws.test_file), "-D", str(ws.bin)], capture_output=True, text=True, env=env, check=False
        )

    @pytest.mark.parametrize(
        ("value", "rc"), [("-42.5000", ExitCode.OK), ("999.0", ExitCode.TEST_FAILURE)], ids=["pass", "fail"]
    )
    def test_exit_code(self, ws, value, rc):
        ws.mock()
        ws.matches(f"energy: {{file: results.txt, grep: 'Energy:', field: 2, value: {value}}}")
        result = self._run(ws, installed_command("pseudotest"))
        assert result.returncode == rc
        assert result.stderr == ""

    @pytest.mark.parametrize("command", COMMANDS.values(), ids=COMMANDS.keys())
    def test_usage_error_in_one_line(self, ws, command):
        ws.mock()
        ws.matches("energy: {fiel: results.txt, grep: 'Energy:', field: 2, value: -42.5}")
        result = self._run(ws, command())
        assert result.returncode == ExitCode.USAGE
        assert result.stderr == "ERROR: Unknown match parameter 'fiel' in 'Inputs > input.txt > Matches > energy'\n"
        assert list(ws.work_root.iterdir()) == []
