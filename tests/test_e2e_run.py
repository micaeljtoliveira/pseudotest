"""End-to-end tests of ``pseudotest``: matches, input methods and the execution of the inputs."""

import re
from pathlib import Path

import pytest

from pseudotest.exceptions import ExitCode
from pseudotest.matchers import register_match_handler
from pseudotest.runner import PseudoTestRunner

ENERGY = "energy: {file: results.txt, grep: 'Energy:', field: 2, value: -42.5000}"


def work_dir_of(out: str) -> Path:
    """Return the working directory printed in the output of a run."""
    return Path(re.search(r"Using workdir: (.+)", out).group(1))


def status_line(out: str, name: str) -> str:
    """Return the status, OK or FAIL, displayed for the match or step *name*."""
    found = re.search(rf"^ *{re.escape(name)} +\[ ?(OK|FAIL) ?\]$", out, re.MULTILINE)
    assert found, f"no status line for {name!r} in:\n{out}"
    return found.group(1)


# ---------------------------------------------------------------------------
# Matches
# ---------------------------------------------------------------------------


class TestMatches:
    def test_match_types(self, ws):
        ws.mock()
        ws.matches(
            """\
            by_field: {file: results.txt, grep: 'Energy:', field: 2, value: -42.5000}
            string: {file: results.txt, grep: Status, field: 2, value: converged}
            by_line: {file: results.txt, line: 4, field: 2, value: 10}
            last_line: {file: results.txt, line: -1, field: 1, value: 'WARNING:'}
            offset: {file: results.txt, grep: 'Energy:', line: 1, field: 3, value: 1.2345e-03}
            by_column: {file: results.txt, line: 1, column: 9, value: -42.5000}
            complex: {file: results.txt, grep: 'Energy:', field_re: 4, field_im: 5, value: 0.5}
            line_count: {file: results.txt, grep: WARNING, count: 2}
            file_size: {file: results.txt, size: 135}
            present: {directory: output_dir, file_is_present: data_a.txt}
            files: {directory: output_dir, count_files: 2}
            """
        )
        result = ws.run()
        assert result.rc == ExitCode.OK
        names = ["by_field", "string", "by_line", "last_line", "offset", "by_column", "complex", "line_count"]
        for name in [*names, "file_size", "present", "files"]:
            assert status_line(result.out, name) == "OK"
        assert "Total matches     :    11" in result.out

    def test_mismatch_is_detailed(self, ws):
        ws.mock()
        ws.matches("energy: {file: results.txt, grep: 'Energy:', field: 2, value: 999.9}")
        result = ws.run()
        assert result.rc == ExitCode.TEST_FAILURE
        assert status_line(result.out, "energy") == "FAIL"
        assert "Calculated value : -42.5000" in result.out
        assert "Reference value  : 999.9" in result.out
        assert "Failed matches    :     1" in result.out

    def test_extraction_failure_is_reported(self, ws):
        ws.mock()
        ws.matches("missing_pattern: {file: results.txt, grep: 'Not there', field: 2, value: 1}")
        result = ws.run()
        assert result.rc == ExitCode.TEST_FAILURE
        assert status_line(result.out, "missing_pattern") == "FAIL"
        assert "No value found in 'results.txt'" in result.out

    def test_group_parameters_are_inherited(self, ws):
        ws.mock()
        ws.matches(
            """\
            results_group:
              file: results.txt
              energy: {grep: 'Energy:', field: 2, value: -42.5000}
              iterations: {grep: Iterations, field: 2, value: 10}
            """
        )
        result = ws.run()
        assert result.rc == ExitCode.OK
        assert "      results_group\n" in result.out
        assert status_line(result.out, "iterations") == "OK"

    @pytest.mark.parametrize(
        ("names", "expected"),
        [("match: [energy, iterations]", ["energy", "iterations"]), ("", ["multi[0]", "multi[1]"])],
        ids=["named", "indexed"],
    )
    def test_broadcast(self, ws, names, expected):
        ws.mock()
        ws.matches(
            f"""\
            multi:
              {names}
              file: results.txt
              grep: ['Energy:', Iterations]
              field: 2
              value: [-42.5000, 10]
            """
        )
        result = ws.run()
        assert result.rc == ExitCode.OK
        for name in expected:
            assert status_line(result.out, name) == "OK"

    def test_registered_match_type(self, ws, restore_match_registry):
        """The example of a new match type of the developer guide."""

        def handle_line_count(filepath, params):
            try:
                lines = filepath.read_text().splitlines()
            except OSError:
                return None, None
            return str(len(lines)), params["line_count"]

        register_match_handler(
            predicate=lambda params: "file" in params and "line_count" in params,
            handler=handle_line_count,
            keys={"file", "line_count"},
            reference_keys={"line_count"},
        )
        ws.mock()
        ws.matches("output_lines: {file: results.txt, line_count: 6}")
        assert ws.run().rc == ExitCode.OK


# ---------------------------------------------------------------------------
# Input methods and input files
# ---------------------------------------------------------------------------

STDIN_READER = """\
#!/usr/bin/env python3
import sys

data = sys.stdin.read()
with open("results.txt", "w") as f:
    f.write(f"got {len(data)} bytes\\n")
"""

ARGUMENT_READER = """\
#!/usr/bin/env python3
import sys

with open(sys.argv[1]) as f:
    data = f.read()
with open("results.txt", "w") as f:
    f.write(f"got {len(data)} bytes\\n")
"""


class TestInputs:
    @pytest.mark.parametrize(("method", "script"), [("argument", ARGUMENT_READER), ("stdin", STDIN_READER)])
    def test_input_method(self, ws, method, script):
        ws.executable(script)
        ws.input(content="hello world\n")
        ws.config(
            f"""\
            Name: Input method
            Executable: mock.py
            InputMethod: {method}
            Inputs:
              input.txt:
                Matches:
                  bytes: {{file: results.txt, line: 1, field: 2, value: 12}}
            """
        )
        assert ws.run().rc == ExitCode.OK

    def test_rename_method(self, ws):
        ws.mock({"results.txt": "rename_ok 1\n"}, requires=("inp.dat",))
        ws.config(
            """\
            Name: Rename method
            Executable: mock.py
            InputMethod: rename
            RenameTo: inp.dat
            Inputs:
              input.txt:
                Matches:
                  ok: {file: results.txt, line: 1, field: 2, value: 1}
            """
        )
        assert ws.run().rc == ExitCode.OK

    @pytest.mark.parametrize(
        ("method", "working_name"), [("argument", "input.txt"), ("stdin", "input.txt"), ("rename", "inp")]
    )
    def test_input_file_removed_after_run(self, ws, method, working_name):
        """The input file is not mistaken for an output, whatever the input method."""
        ws.mock()
        ws.config(
            f"Name: Cleanup\nExecutable: mock.py\nInputMethod: {method}\nRenameTo: inp\nInputs:\n  input.txt: {{}}\n"
        )
        result = ws.run("--preserve")
        assert result.rc == ExitCode.OK
        work_dir = work_dir_of(result.out)
        assert (work_dir / "results.txt").exists()
        assert not (work_dir / working_name).exists()

    def test_input_in_subdirectory_is_used_by_name(self, ws):
        ws.executable(ARGUMENT_READER)
        ws.input("inputs/case.in", content="hello world\n")
        ws.config(
            """\
            Name: Input in subdirectory
            Executable: mock.py
            Inputs:
              inputs/case.in:
                Matches:
                  bytes: {file: results.txt, line: 1, field: 2, value: 12}
            """
        )
        assert ws.run().rc == ExitCode.OK

    def test_input_without_parameters(self, ws):
        """An input written as 'input.txt:' runs with the top-level parameters."""
        ws.mock()
        ws.config("Name: No parameters\nExecutable: mock.py\nInputs:\n  input.txt:\n")
        assert ws.run().rc == ExitCode.OK

    def test_extra_files_are_copied(self, ws):
        ws.mock({"results.txt": "extra_ok 1\n"}, requires=("extra.dat",))
        ws.input("data/extra.dat", content="extra content\n")
        ws.config(
            """\
            Name: Extra files
            Executable: mock.py
            Inputs:
              input.txt:
                ExtraFiles: [data/extra.dat]
                Matches:
                  ok: {file: results.txt, line: 1, field: 2, value: 1}
            """
        )
        assert ws.run().rc == ExitCode.OK


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


class TestExecution:
    def test_failed_execution_shows_end_of_output(self, ws):
        ws.mock({}, exit_code=1, stdout="".join(f"line {i}\n" for i in range(20)))
        ws.matches(ENERGY)
        result = ws.run()
        assert result.rc == ExitCode.TEST_FAILURE
        assert status_line(result.out, "Execution") == "FAIL"
        assert "=== STDOUT from input.txt ===" in result.out
        assert "showing last 10 lines" in result.out
        assert "line 19\n" in result.out
        assert "line 5\n" not in result.out
        # Matches are not evaluated after a failed execution
        assert "Total matches     :     0" in result.out

    def test_expected_failure(self, ws):
        ws.mock({}, exit_code=1, stdout="some output\n")
        ws.config("Name: Expected failure\nExecutable: mock.py\nInputs:\n  input.txt:\n    ExpectedFailure: true\n")
        result = ws.run()
        assert result.rc == ExitCode.OK
        assert status_line(result.out, "Failed execution") == "OK"
        assert "STDOUT" not in result.out

    def test_expected_failure_that_succeeds_fails(self, ws):
        ws.mock()
        ws.config("Name: Expected failure\nExecutable: mock.py\nInputs:\n  input.txt:\n    ExpectedFailure: true\n")
        result = ws.run()
        assert result.rc == ExitCode.TEST_FAILURE
        assert status_line(result.out, "Failed execution") == "FAIL"

    def test_stderr_of_successful_execution_not_shown(self, ws):
        ws.mock(stderr="some warning on stderr\n")
        ws.matches(ENERGY)
        result = ws.run()
        assert result.rc == ExitCode.OK
        assert "some warning on stderr" not in result.out

    def test_timeout_is_reported(self, ws):
        ws.mock(sleep=30)
        ws.matches(ENERGY)
        result = ws.run("-t", "1")
        assert result.rc == ExitCode.TEST_FAILURE
        assert "=== input.txt: timed out after 1 s ===" in result.out

    def test_disabled_test_is_skipped(self, ws):
        ws.config("Name: Disabled\nEnabled: false\nExecutable: missing.py\nInputs:\n  input.txt: {}\n")
        result = ws.run()
        assert result.rc == ExitCode.OK
        assert "Test disabled: skipping test" in result.out

    def test_inputs_share_the_working_directory(self, ws):
        """Each input runs in the working directory of the previous ones, e.g. to restart from their outputs."""
        ws.executable(
            """\
            #!/usr/bin/env python3
            with open("history.txt", "a") as f:
                f.write("run\\n")
            """
        )
        ws.input("second.txt")
        ws.config(
            """\
            Name: Shared working directory
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  runs: {file: history.txt, grep: run, count: 1}
              second.txt:
                Matches:
                  runs: {file: history.txt, grep: run, count: 2}
            """
        )
        assert ws.run().rc == ExitCode.OK

    @pytest.mark.parametrize("preserve", [True, False])
    def test_working_directory_removed_unless_preserved(self, ws, preserve):
        ws.mock()
        ws.matches(ENERGY)
        result = ws.run(*(["--preserve"] if preserve else []))
        assert result.rc == ExitCode.OK
        assert (work_dir_of(result.out) / "results.txt").exists() is preserve

    def test_runner_reuse_resets_counters(self, ws):
        ws.mock()
        ws.matches("wrong: {file: results.txt, grep: 'Energy:', field: 2, value: 1}")
        runner = PseudoTestRunner()
        runner.run(str(ws.test_file), str(ws.bin), False, 60)
        runner.run(str(ws.test_file), str(ws.bin), False, 60)
        assert runner.failed_matches == 1
        assert runner.total_matches == 1


class TestMPI:
    def test_processors_ignored_without_mpiexec(self, ws, monkeypatch):
        monkeypatch.delenv("MPIEXEC", raising=False)
        ws.mock()
        ws.config("Name: Serial\nExecutable: mock.py\nInputs:\n  input.txt:\n    Processors: 4\n")
        assert ws.run().rc == ExitCode.OK

    def test_launcher_runs_executable(self, ws, monkeypatch):
        """A fake launcher records its process-count arguments, then runs the executable."""
        record = ws.root / "launcher_args.txt"
        launcher = ws.executable(
            f"""\
            #!/usr/bin/env python3
            import os, sys

            with open({str(record)!r}, "w") as f:
                f.write(" ".join(sys.argv[1:3]))
            os.execv(sys.argv[3], sys.argv[3:])
            """,
            name="mpiexec",
        )
        monkeypatch.setenv("MPIEXEC", str(launcher))
        ws.mock()
        ws.config(
            f"""\
            Name: MPI
            Executable: mock.py
            Inputs:
              input.txt:
                Processors: 4
                Matches:
                  {ENERGY}
            """
        )
        assert ws.run().rc == ExitCode.OK
        assert record.read_text() == "-np 4"
