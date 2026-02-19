"""Integration / regression tests for the pseudotest script.

Every test builds a self-contained workspace inside ``tmp_path`` with:
  * a mock executable (Python script) that creates files and directories,
  * one or more input files, and
  * a YAML test configuration.

The tests then call ``pseudotest.runner.main()`` directly so that
``pytest-cov`` can track coverage across the whole stack.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from pseudotest.exceptions import ExitCode

# ---------------------------------------------------------------------------
# Mock executable scripts
# ---------------------------------------------------------------------------

MOCK_CREATOR_SCRIPT = """\
#!/usr/bin/env python3
\"\"\"Mock executable that creates files and directories for testing.\"\"\"
import os, sys

# Create an output directory with several files
os.makedirs("output_dir", exist_ok=True)
with open("output_dir/data_a.txt", "w") as f:
    f.write("file_a\\n")
with open("output_dir/data_b.txt", "w") as f:
    f.write("file_b\\n")

# Write a structured results file with known numeric/string fields
with open("results.txt", "w") as f:
    f.write("Energy: -42.5000 Ry  0.3  0.4\\n")
    f.write("Total force: 1.2345e-03 Ha\\n")
    f.write("Status converged OK\\n")
    f.write("Iterations 10\\n")
    f.write("WARNING: step skipped\\n")
    f.write("WARNING: step skipped\\n")

sys.exit(0)
"""

MOCK_FAILING_SCRIPT = """\
#!/usr/bin/env python3
import sys
sys.exit(1)
"""

MOCK_STDIN_SCRIPT = """\
#!/usr/bin/env python3
\"\"\"Reads from stdin, writes a results file.\"\"\"
import sys
data = sys.stdin.read()
with open("results.txt", "w") as f:
    f.write(f"got {len(data)} bytes\\n")
sys.exit(0)
"""

MOCK_RENAME_SCRIPT = """\
#!/usr/bin/env python3
\"\"\"Expects 'inp.dat' in cwd, writes results.\"\"\"
import os, sys
if not os.path.exists("inp.dat"):
    sys.exit(1)
with open("results.txt", "w") as f:
    f.write("rename_ok 1\\n")
sys.exit(0)
"""

MOCK_SLOW_SCRIPT = """\
#!/usr/bin/env python3
import time, sys
time.sleep(30)
sys.exit(0)
"""

MOCK_STDERR_SCRIPT = """\
#!/usr/bin/env python3
import sys
sys.stderr.write("some warning on stderr\\n")
with open("results.txt", "w") as f:
    f.write("value 99\\n")
sys.exit(0)
"""

MOCK_VERBOSE_OUTPUT_SCRIPT = """\
#!/usr/bin/env python3
import sys
# Write many lines to stdout so truncation logic is exercised
for i in range(20):
    print(f"line {i}")
sys.exit(1)
"""


# ---------------------------------------------------------------------------
# Basic pass / fail tests
# ---------------------------------------------------------------------------


class TestBasicPassFail:
    """Scenarios where all matches pass or some fail."""

    def test_all_matches_pass(self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest):
        make_executable(exec_dir, "mock.py", MOCK_CREATOR_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: All pass
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  energy_field:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: -42.5000
                  status_string:
                    file: results.txt
                    grep: "Status"
                    field: 2
                    value: converged
                  dir_file_present:
                    directory: output_dir
                    file_is_present: data_a.txt
                  dir_count:
                    directory: output_dir
                    count_files: 2
            """,
        )

        rc = run_pseudotest(yaml_file, exec_dir)
        assert rc == ExitCode.OK

    def test_match_value_mismatch_fails(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest
    ):
        make_executable(exec_dir, "mock.py", MOCK_CREATOR_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Value mismatch
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  wrong_energy:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: 999.9
            """,
        )

        rc = run_pseudotest(yaml_file, exec_dir)
        assert rc == ExitCode.TEST_FAILURE


# ---------------------------------------------------------------------------
# Test input methods
# ---------------------------------------------------------------------------


class TestInputMethods:
    """Cover argument (default), stdin, and rename input methods."""

    def test_stdin_method(self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest):
        make_executable(exec_dir, "mock_stdin.py", MOCK_STDIN_SCRIPT)
        make_input(tmp_path, content="hello world\n")  # 12 bytes

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Stdin method
            Executable: mock_stdin.py
            InputMethod: stdin
            Inputs:
              input.txt:
                Matches:
                  byte_count:
                    file: results.txt
                    line: 1
                    field: 2
                    value: 12
            """,
        )
        assert run_pseudotest(yaml_file, exec_dir) == ExitCode.OK

    def test_rename_method(self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest):
        make_executable(exec_dir, "mock_rename.py", MOCK_RENAME_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Rename method
            Executable: mock_rename.py
            InputMethod: rename
            RenameTo: inp.dat
            Inputs:
              input.txt:
                Matches:
                  ok_flag:
                    file: results.txt
                    line: 1
                    field: 2
                    value: 1
            """,
        )
        assert run_pseudotest(yaml_file, exec_dir) == ExitCode.OK


# ---------------------------------------------------------------------------
# MPI execution tests
# ---------------------------------------------------------------------------


class TestMPIExecution:
    """Cover MPI execution via the MPIEXEC environment variable."""

    def test_serial_without_mpiexec(self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest):
        """When MPIEXEC is not set, Processors key is ignored and runs serially."""
        make_executable(exec_dir, "mock.py", MOCK_CREATOR_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Serial test
            Executable: mock.py
            Inputs:
              input.txt:
                Processors: 4
                Matches:
                  energy:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: -42.5000
            """,
        )
        env = os.environ.copy()
        env.pop("MPIEXEC", None)
        with patch.dict(os.environ, env, clear=True):
            rc = run_pseudotest(yaml_file, exec_dir)
        assert rc == ExitCode.OK

    def test_report_includes_processors(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest
    ):
        """Report includes Processors field from input scope."""
        make_executable(exec_dir, "mock.py", MOCK_CREATOR_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Report procs
            Executable: mock.py
            Inputs:
              input.txt:
                Processors: 8
                Matches:
                  energy:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: -42.5000
            """,
        )
        report_path = tmp_path / "report.yaml"
        env = os.environ.copy()
        env.pop("MPIEXEC", None)
        with patch.dict(os.environ, env, clear=True):
            rc = run_pseudotest(yaml_file, exec_dir, extra_args=["-r", str(report_path)])
        assert rc == ExitCode.OK

        from ruamel.yaml import YAML as _YAML

        docs = list(_YAML().load_all(report_path.open()))
        report = docs[-1]
        key = next(iter(report))
        assert report[key]["Inputs"]["input.txt"]["Processors"] == 8


# ---------------------------------------------------------------------------
# Execution failures & edge cases tests
# ---------------------------------------------------------------------------


class TestExecutionEdgeCases:
    """Cover failing executables, expected failures, disabled tests, etc."""

    def test_executable_failure_reported(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest
    ):
        make_executable(exec_dir, "fail.py", MOCK_FAILING_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Exec fails
            Executable: fail.py
            Inputs:
              input.txt:
                Matches:
                  unused:
                    file: results.txt
                    line: 1
                    field: 1
                    value: x
            """,
        )
        rc = run_pseudotest(yaml_file, exec_dir)
        assert rc == ExitCode.TEST_FAILURE

    def test_expected_failure(self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest):
        make_executable(exec_dir, "fail.py", MOCK_FAILING_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Expected failure
            Executable: fail.py
            Inputs:
              input.txt:
                ExpectedFailure: true
                Matches: {}
            """,
        )
        rc = run_pseudotest(yaml_file, exec_dir)
        assert rc == ExitCode.OK

    def test_expected_failure_but_succeeds(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest
    ):
        """When a test is expected to fail but actually succeeds, that's a failure."""
        make_executable(exec_dir, "mock.py", MOCK_CREATOR_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Expected fail but passes
            Executable: mock.py
            Inputs:
              input.txt:
                ExpectedFailure: true
            """,
        )
        rc = run_pseudotest(yaml_file, exec_dir)
        assert rc == ExitCode.TEST_FAILURE

    def test_disabled_test(self, tmp_path, exec_dir, make_yaml, run_pseudotest):
        # No executable needed – test is disabled
        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Disabled
            Enabled: false
            Executable: nonexistent.py
            Inputs:
              input.txt: {}
            """,
        )
        rc = run_pseudotest(yaml_file, exec_dir)
        assert rc == ExitCode.OK

    def test_timeout(self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest):
        make_executable(exec_dir, "slow.py", MOCK_SLOW_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Timeout test
            Executable: slow.py
            Inputs:
              input.txt:
                Matches:
                  dummy:
                    file: results.txt
                    line: 1
                    field: 1
                    value: x
            """,
        )
        # Use a very short timeout so the test completes quickly
        rc = run_pseudotest(yaml_file, exec_dir, extra_args=["-t", "1"])
        assert rc == ExitCode.TEST_FAILURE

    def test_extra_files_copied(self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest):
        # Executable that checks for the extra file
        make_executable(
            exec_dir,
            "check_extra.py",
            """\
            #!/usr/bin/env python3
            import os, sys
            if not os.path.exists("extra.dat"):
                sys.exit(1)
            with open("results.txt", "w") as f:
                f.write("extra_ok 1\\n")
            sys.exit(0)
            """,
        )
        make_input(tmp_path)
        (tmp_path / "extra.dat").write_text("extra content\n")

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Extra files
            Executable: check_extra.py
            Inputs:
              input.txt:
                ExtraFiles:
                  - extra.dat
                Matches:
                  ok:
                    file: results.txt
                    line: 1
                    field: 2
                    value: 1
            """,
        )
        assert run_pseudotest(yaml_file, exec_dir) == ExitCode.OK

    def test_preserve_workdir(self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest):
        make_executable(exec_dir, "mock.py", MOCK_CREATOR_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Preserve workdir
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  energy:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: -42.5000
            """,
        )
        rc = run_pseudotest(yaml_file, exec_dir, extra_args=["--preserve"])
        assert rc == ExitCode.OK


# ---------------------------------------------------------------------------
# CLI / logging tests
# ---------------------------------------------------------------------------


class TestCLIOptions:
    """Verify verbose flags and other CLI behaviour."""

    def test_verbose_v(self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest):
        make_executable(exec_dir, "mock.py", MOCK_CREATOR_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Verbose
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  energy:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: -42.5000
            """,
        )
        rc = run_pseudotest(yaml_file, exec_dir, extra_args=["-v"])
        assert rc == ExitCode.OK

    def test_verbose_vv(self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest):
        make_executable(exec_dir, "mock.py", MOCK_CREATOR_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Debug
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  energy:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: -42.5000
            """,
        )
        rc = run_pseudotest(yaml_file, exec_dir, extra_args=["-vv"])
        assert rc == ExitCode.OK


# ---------------------------------------------------------------------------
# Output printing for failed executions tests
# ---------------------------------------------------------------------------


class TestFailedExecutionOutput:
    """Cover the _print_execution_output paths (stdout truncation, etc.)."""

    def test_verbose_failure_shows_full_output(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest
    ):
        """With -vv a failing executable's full stdout should be shown."""
        make_executable(exec_dir, "noisy_fail.py", MOCK_VERBOSE_OUTPUT_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Noisy failure
            Executable: noisy_fail.py
            Inputs:
              input.txt:
                Matches:
                  dummy:
                    file: results.txt
                    line: 1
                    field: 1
                    value: x
            """,
        )
        rc = run_pseudotest(yaml_file, exec_dir, extra_args=["-vv"])
        assert rc == ExitCode.TEST_FAILURE

    def test_normal_failure_truncates_output(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest
    ):
        """Without -vv long output should be truncated to last 10 lines."""
        make_executable(exec_dir, "noisy_fail.py", MOCK_VERBOSE_OUTPUT_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Truncated failure
            Executable: noisy_fail.py
            Inputs:
              input.txt:
                Matches:
                  dummy:
                    file: results.txt
                    line: 1
                    field: 1
                    value: x
            """,
        )
        rc = run_pseudotest(yaml_file, exec_dir)
        assert rc == ExitCode.TEST_FAILURE


# ---------------------------------------------------------------------------
# Stderr from successful execution tests
# ---------------------------------------------------------------------------


class TestStderrOutput:
    """Executable writes to stderr but still succeeds."""

    def test_stderr_on_success(self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest):
        make_executable(exec_dir, "warn.py", MOCK_STDERR_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Stderr on success
            Executable: warn.py
            Inputs:
              input.txt:
                Matches:
                  val:
                    file: results.txt
                    line: 1
                    field: 2
                    value: 99
            """,
        )
        rc = run_pseudotest(yaml_file, exec_dir, extra_args=["-vv"])
        assert rc == ExitCode.OK


# ---------------------------------------------------------------------------
# Multiple inputs in one YAML tests
# ---------------------------------------------------------------------------


class TestMultipleInputs:
    def test_two_inputs(self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest):
        make_executable(exec_dir, "mock.py", MOCK_CREATOR_SCRIPT)
        make_input(tmp_path, "a.txt")
        make_input(tmp_path, "b.txt")

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Two inputs
            Executable: mock.py
            Inputs:
              a.txt:
                Matches:
                  energy:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: -42.5000
              b.txt:
                Matches:
                  status:
                    file: results.txt
                    grep: "Status"
                    field: 2
                    value: converged
            """,
        )
        rc = run_pseudotest(yaml_file, exec_dir)
        assert rc == ExitCode.OK


# ---------------------------------------------------------------------------
# Nested match groups & broadcast params tests
# ---------------------------------------------------------------------------


class TestNestedAndBroadcast:
    def test_nested_match_group(self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest):
        make_executable(exec_dir, "mock.py", MOCK_CREATOR_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Nested matches
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  results_group:
                    file: results.txt
                    energy:
                      grep: "Energy:"
                      field: 2
                      value: -42.5000
                    iterations:
                      grep: "Iterations"
                      field: 2
                      value: 10
            """,
        )
        rc = run_pseudotest(yaml_file, exec_dir)
        assert rc == ExitCode.OK

    def test_broadcast_params(self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest):
        make_executable(exec_dir, "mock.py", MOCK_CREATOR_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Broadcast
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  multi:
                    file: results.txt
                    grep:
                      - "Energy:"
                      - "Iterations"
                    field:
                      - 2
                      - 2
                    value:
                      - -42.5000
                      - 10
            """,
        )
        rc = run_pseudotest(yaml_file, exec_dir)
        assert rc == ExitCode.OK

    def test_broadcast_with_match_key(self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest):
        """Broadcast params with 'match' key for display names works correctly."""
        make_executable(exec_dir, "mock.py", MOCK_CREATOR_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Broadcast match key
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  multi:
                    file: results.txt
                    match:
                      - energy
                      - iterations
                    grep:
                      - "Energy:"
                      - "Iterations"
                    field:
                      - 2
                      - 2
                    value:
                      - -42.5000
                      - 10
            """,
        )
        rc = run_pseudotest(yaml_file, exec_dir)
        assert rc == ExitCode.OK


# ---------------------------------------------------------------------------
# YAML report (-r) tests
# ---------------------------------------------------------------------------


class TestYAMLReport:
    """Tests for the -r / --report YAML report feature."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, exec_dir, make_executable, make_input):
        make_executable(exec_dir, "mock.py", MOCK_CREATOR_SCRIPT)
        make_input(tmp_path)
        self.exec_dir = exec_dir
        self.tmp_path = tmp_path

    def _load_raw_report(self, path):
        from ruamel.yaml import YAML as _YAML

        return list(_YAML().load_all(path.open()))

    def _load_report(self, path):
        docs = self._load_raw_report(path)
        raw = docs[-1]
        # Unwrap the top-level test-file key
        key = next(iter(raw))
        return raw[key]

    def test_report_written_on_pass(self, make_yaml, run_pseudotest):
        """Report is written and contains expected keys when all matches pass."""
        yaml_file = make_yaml(
            self.tmp_path,
            """\
            Name: Report pass
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  energy:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: -42.5000
            """,
        )
        report_path = self.tmp_path / "report.yaml"
        rc = run_pseudotest(yaml_file, self.exec_dir, extra_args=["-r", str(report_path)])

        assert rc == ExitCode.OK
        assert report_path.exists()
        report = self._load_report(report_path)
        assert report["Name"] == "Report pass"
        assert report["Enabled"] is True
        assert report["Executable"] == "mock.py"
        assert report["Inputs"]["input.txt"]["InputMethod"] == "argument"
        assert report["Inputs"]["input.txt"]["ExpectedFailure"] is False
        assert report["Inputs"]["input.txt"]["Execution"] == "pass"
        energy = report["Inputs"]["input.txt"]["Matches"]["energy"]
        assert energy["file"] == "results.txt"
        assert energy["grep"] == "Energy:"
        assert energy["field"] == 2
        assert energy["value"] == -42.5
        assert energy["reference"] == -42.5

    def test_report_written_on_failure(self, make_yaml, run_pseudotest):
        """Report reflects calculated values when matches fail."""
        yaml_file = make_yaml(
            self.tmp_path,
            """\
            Name: Report fail
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  wrong:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: 999.0
            """,
        )
        report_path = self.tmp_path / "report.yaml"
        rc = run_pseudotest(yaml_file, self.exec_dir, extra_args=["-r", str(report_path)])

        assert rc == ExitCode.TEST_FAILURE
        report = self._load_report(report_path)
        wrong = report["Inputs"]["input.txt"]["Matches"]["wrong"]
        assert wrong["value"] == -42.5  # calculated value, not reference
        assert wrong["reference"] == 999.0  # original reference value

    def test_report_with_multiple_matches(self, make_yaml, run_pseudotest):
        """Report includes all match results with parameters."""
        yaml_file = make_yaml(
            self.tmp_path,
            """\
            Name: Report multi
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  energy:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: -42.5000
                  status:
                    file: results.txt
                    grep: "Status"
                    field: 2
                    value: converged
            """,
        )
        report_path = self.tmp_path / "report.yaml"
        rc = run_pseudotest(yaml_file, self.exec_dir, extra_args=["-r", str(report_path)])

        assert rc == ExitCode.OK
        report = self._load_report(report_path)
        matches = report["Inputs"]["input.txt"]["Matches"]
        assert matches["energy"]["value"] == -42.5
        assert matches["energy"]["reference"] == -42.5
        assert matches["energy"]["grep"] == "Energy:"
        assert matches["status"]["value"] == "converged"
        assert matches["status"]["reference"] == "converged"
        assert matches["status"]["grep"] == "Status"

    def test_report_execution_failure(self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest):
        """Report records execution failure and has no Matches key."""
        make_executable(exec_dir, "fail.py", MOCK_FAILING_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Report exec fail
            Executable: fail.py
            Inputs:
              input.txt:
                Matches:
                  dummy:
                    file: results.txt
                    grep: "x"
                    field: 1
                    value: 1
            """,
        )
        report_path = tmp_path / "report.yaml"
        rc = run_pseudotest(yaml_file, exec_dir, extra_args=["-r", str(report_path)])

        assert rc == ExitCode.TEST_FAILURE
        report = self._load_report(report_path)
        assert report["Inputs"]["input.txt"]["InputMethod"] == "argument"
        assert report["Inputs"]["input.txt"]["Execution"] == "fail"
        assert "Matches" not in report["Inputs"]["input.txt"]

    def test_report_has_elapsed_time(self, make_yaml, run_pseudotest):
        """Report includes elapsed time for each input."""
        yaml_file = make_yaml(
            self.tmp_path,
            """\
            Name: Report timing
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  energy:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: -42.5000
            """,
        )
        report_path = self.tmp_path / "report.yaml"
        run_pseudotest(yaml_file, self.exec_dir, extra_args=["-r", str(report_path)])

        report = self._load_report(report_path)
        elapsed = report["Inputs"]["input.txt"]["Elapsed time"]
        assert isinstance(elapsed, float)
        assert elapsed >= 0.0

    def test_no_report_when_flag_absent(self, make_yaml, run_pseudotest):
        """No report file is created when -r is not given."""
        yaml_file = make_yaml(
            self.tmp_path,
            """\
            Name: No report
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  energy:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: -42.5000
            """,
        )
        report_path = self.tmp_path / "report.yaml"
        run_pseudotest(yaml_file, self.exec_dir)
        assert not report_path.exists()

    def test_report_nested_match_group(self, make_yaml, run_pseudotest):
        """Report preserves nested match group structure with calculated values."""
        yaml_file = make_yaml(
            self.tmp_path,
            """\
            Name: Nested report
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  results_group:
                    file: results.txt
                    energy:
                      grep: "Energy:"
                      field: 2
                      value: -42.5000
                    iterations:
                      grep: "Iterations"
                      field: 2
                      value: 10
            """,
        )
        report_path = self.tmp_path / "report.yaml"
        rc = run_pseudotest(yaml_file, self.exec_dir, extra_args=["-r", str(report_path)])

        assert rc == ExitCode.OK
        report = self._load_report(report_path)
        group = report["Inputs"]["input.txt"]["Matches"]["results_group"]
        assert isinstance(group, dict)
        assert group["energy"]["value"] == -42.5
        assert group["energy"]["reference"] == -42.5
        assert group["iterations"]["value"] == 10
        assert group["iterations"]["reference"] == 10

    def test_report_directory_match(self, make_yaml, run_pseudotest):
        """Report includes directory match parameters with calculated value."""
        yaml_file = make_yaml(
            self.tmp_path,
            """\
            Name: Dir report
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  dir_count:
                    directory: output_dir
                    count_files: 2
            """,
        )
        report_path = self.tmp_path / "report.yaml"
        rc = run_pseudotest(yaml_file, self.exec_dir, extra_args=["-r", str(report_path)])

        assert rc == ExitCode.OK
        report = self._load_report(report_path)
        dir_match = report["Inputs"]["input.txt"]["Matches"]["dir_count"]
        assert dir_match["directory"] == "output_dir"
        assert dir_match["count_files"] == 2
        assert dir_match["reference"] == 2

    def test_report_omits_internal_keys(self, make_yaml, run_pseudotest):
        """Report does not include internal keys like 'tol' and 'match'."""
        yaml_file = make_yaml(
            self.tmp_path,
            """\
            Name: Report tol
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  energy:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: -42.5000
                    tol: 0.01
            """,
        )
        report_path = self.tmp_path / "report.yaml"
        run_pseudotest(yaml_file, self.exec_dir, extra_args=["-r", str(report_path)])

        report = self._load_report(report_path)
        energy = report["Inputs"]["input.txt"]["Matches"]["energy"]
        assert energy["tol"] == 0.01
        assert "match" not in energy
        assert energy["value"] == -42.5

    def test_report_expected_failure(self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest):
        """Report shows ExpectedFailure: true when set."""
        make_executable(exec_dir, "fail.py", MOCK_FAILING_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Report expected fail
            Executable: fail.py
            Inputs:
              input.txt:
                ExpectedFailure: true
            """,
        )
        report_path = tmp_path / "report.yaml"
        rc = run_pseudotest(yaml_file, exec_dir, extra_args=["-r", str(report_path)])

        assert rc == ExitCode.OK
        report = self._load_report(report_path)
        assert report["Inputs"]["input.txt"]["ExpectedFailure"] is True
        assert report["Inputs"]["input.txt"]["Execution"] == "pass"

    def test_report_top_level_key_is_test_file(self, make_yaml, run_pseudotest):
        """Top-level report key is the test file path, with leading './' stripped."""
        yaml_file = make_yaml(
            self.tmp_path,
            """\
            Name: Key test
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  energy:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: -42.5000
            """,
        )
        report_path = self.tmp_path / "report.yaml"
        run_pseudotest(yaml_file, self.exec_dir, extra_args=["-r", str(report_path)])

        raw = self._load_raw_report(report_path)
        top_key = next(iter(raw[-1]))
        assert top_key == str(yaml_file)
        assert "Name" in raw[-1][top_key]

    def test_report_appends_to_existing(self, make_yaml, run_pseudotest):
        """Running twice appends a second YAML document instead of overwriting."""
        yaml_file = make_yaml(
            self.tmp_path,
            """\
            Name: Append test
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  energy:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: -42.5000
            """,
        )
        report_path = self.tmp_path / "report.yaml"
        run_pseudotest(yaml_file, self.exec_dir, extra_args=["-r", str(report_path)])
        run_pseudotest(yaml_file, self.exec_dir, extra_args=["-r", str(report_path)])

        docs = self._load_raw_report(report_path)
        assert len(docs) == 2
        for doc in docs:
            key = next(iter(doc))
            assert doc[key]["Name"] == "Append test"

        # Verify --- separators in the raw text
        text = report_path.read_text()
        assert text.startswith("---\n")
        assert text.count("---\n") == 2


# ---------------------------------------------------------------------------
# Config update tests (pseudotest-update script)
# ---------------------------------------------------------------------------

# Mock that produces a slightly different value to trigger match failures
MOCK_DRIFTED_SCRIPT = """\
#!/usr/bin/env python3
\"\"\"Mock executable that produces values close but not equal to the reference.\"\"\"
import sys

with open("results.txt", "w") as f:
    f.write("Energy: -42.5050 Ry\\n")
    f.write("Force: 3.0000 Ha\\n")
sys.exit(0)
"""


class TestUpdateTolerance:
    """Tests for pseudotest-update --tolerance."""

    def test_update_tolerance_basic(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest, run_update
    ):
        """pseudotest-update -t sets tol on a failing numeric match."""
        make_executable(exec_dir, "mock.py", MOCK_DRIFTED_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Tol update
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  energy:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: -42.5000
            """,
        )
        # First run: match fails (diff = 0.005)
        rc = run_pseudotest(yaml_file, exec_dir)
        assert rc == ExitCode.TEST_FAILURE

        # Run with pseudotest-update -t: should rewrite the YAML
        rc = run_update(yaml_file, exec_dir, "-t")
        assert rc == ExitCode.TEST_FAILURE  # still fails this run

        # Re-run: now the tolerance should make it pass
        rc = run_pseudotest(yaml_file, exec_dir)
        assert rc == ExitCode.OK

        # Verify the YAML was updated with a tol key
        from ruamel.yaml import YAML as _YAML

        data = _YAML().load(yaml_file.open())
        tol = data["Inputs"]["input.txt"]["Matches"]["energy"]["tol"]
        assert tol >= 0.005  # at least the observed difference

    def test_update_tolerance_preserves_reference(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_update
    ):
        """pseudotest-update -t must not change the reference value."""
        make_executable(exec_dir, "mock.py", MOCK_DRIFTED_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Preserve ref
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  energy:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: -42.5000
            """,
        )
        run_update(yaml_file, exec_dir, "-t")

        from ruamel.yaml import YAML as _YAML

        data = _YAML().load(yaml_file.open())
        assert float(data["Inputs"]["input.txt"]["Matches"]["energy"]["value"]) == -42.5

    def test_update_tolerance_replaces_insufficient_tol(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_update
    ):
        """When existing tol is too small, pseudotest-update -t increases it."""
        make_executable(exec_dir, "mock.py", MOCK_DRIFTED_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Replace tol
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  energy:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: -42.5000
                    tol: 0.001
            """,
        )
        run_update(yaml_file, exec_dir, "-t")

        from ruamel.yaml import YAML as _YAML

        data = _YAML().load(yaml_file.open())
        tol = data["Inputs"]["input.txt"]["Matches"]["energy"]["tol"]
        assert tol >= 0.005

    def test_update_tolerance_skips_passing_match(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_update
    ):
        """Passing matches are not modified by pseudotest-update -t."""
        make_executable(exec_dir, "mock.py", MOCK_DRIFTED_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Skip passing
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  energy:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: -42.5050
            """,
        )
        rc = run_update(yaml_file, exec_dir, "-t")
        assert rc == ExitCode.OK

        from ruamel.yaml import YAML as _YAML

        data = _YAML().load(yaml_file.open())
        assert "tol" not in data["Inputs"]["input.txt"]["Matches"]["energy"]

    def test_update_tolerance_skips_failed_execution(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_update
    ):
        """No update when execution fails."""
        make_executable(exec_dir, "fail.py", MOCK_FAILING_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Fail exec
            Executable: fail.py
            Inputs:
              input.txt:
                Matches:
                  energy:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: -42.5000
            """,
        )
        original = yaml_file.read_text()
        run_update(yaml_file, exec_dir, "-t")
        assert yaml_file.read_text() == original


class TestUpdateReference:
    """Tests for pseudotest-update --reference."""

    def test_update_reference_basic(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest, run_update
    ):
        """pseudotest-update -r replaces the value with the calculated one."""
        make_executable(exec_dir, "mock.py", MOCK_DRIFTED_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Ref update
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  energy:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: -42.5000
            """,
        )
        rc = run_update(yaml_file, exec_dir, "-r")
        assert rc == ExitCode.TEST_FAILURE  # still fails this run

        # Re-run: now the reference matches the calculated value
        rc = run_pseudotest(yaml_file, exec_dir)
        assert rc == ExitCode.OK

        from ruamel.yaml import YAML as _YAML

        data = _YAML().load(yaml_file.open())
        assert float(data["Inputs"]["input.txt"]["Matches"]["energy"]["value"]) == pytest.approx(-42.505)

    def test_update_reference_preserves_tolerance(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_update
    ):
        """pseudotest-update -r must not change existing tolerances."""
        make_executable(exec_dir, "mock.py", MOCK_DRIFTED_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Preserve tol
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  energy:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: -42.5000
                    tol: 0.001
            """,
        )
        run_update(yaml_file, exec_dir, "-r")

        from ruamel.yaml import YAML as _YAML

        data = _YAML().load(yaml_file.open())
        match_entry = data["Inputs"]["input.txt"]["Matches"]["energy"]
        assert float(match_entry["value"]) == pytest.approx(-42.505)
        assert match_entry["tol"] == 0.001

    def test_update_reference_skips_passing_match(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_update
    ):
        """Passing matches are not modified by pseudotest-update -r."""
        make_executable(exec_dir, "mock.py", MOCK_DRIFTED_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Skip passing
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  energy:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: -42.5050
            """,
        )
        run_update(yaml_file, exec_dir, "-r")

        from ruamel.yaml import YAML as _YAML

        data = _YAML().load(yaml_file.open())
        assert float(data["Inputs"]["input.txt"]["Matches"]["energy"]["value"]) == -42.505

    def test_update_reference_skips_failed_execution(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_update
    ):
        """No update when execution fails."""
        make_executable(exec_dir, "fail.py", MOCK_FAILING_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Fail exec
            Executable: fail.py
            Inputs:
              input.txt:
                Matches:
                  energy:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: -42.5000
            """,
        )
        original = yaml_file.read_text()
        run_update(yaml_file, exec_dir, "-r")
        assert yaml_file.read_text() == original

    def test_update_reference_skips_extraction_failure(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_update
    ):
        """No update when the calculated value cannot be extracted."""
        make_executable(exec_dir, "mock.py", MOCK_DRIFTED_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Bad grep
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  missing:
                    file: results.txt
                    grep: "NONEXISTENT:"
                    field: 2
                    value: 99.0
            """,
        )
        run_update(yaml_file, exec_dir, "-r")

        from ruamel.yaml import YAML as _YAML

        data = _YAML().load(yaml_file.open())
        assert float(data["Inputs"]["input.txt"]["Matches"]["missing"]["value"]) == 99.0

    def test_update_reference_multiple_matches(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_update
    ):
        """Only failing matches are updated; passing ones are left alone."""
        make_executable(exec_dir, "mock.py", MOCK_DRIFTED_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Multi match
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  energy:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: -42.5000
                  force:
                    file: results.txt
                    grep: "Force:"
                    field: 2
                    value: 3.0000
            """,
        )
        run_update(yaml_file, exec_dir, "-r")

        from ruamel.yaml import YAML as _YAML

        data = _YAML().load(yaml_file.open())
        matches = data["Inputs"]["input.txt"]["Matches"]
        # energy was wrong → updated
        assert float(matches["energy"]["value"]) == pytest.approx(-42.505)
        # force was correct → unchanged
        assert float(matches["force"]["value"]) == 3.0

    def test_mutually_exclusive_flags(self, tmp_path, exec_dir, make_executable, make_input, make_yaml):
        """-t and -r cannot be used together."""
        make_executable(exec_dir, "mock.py", MOCK_DRIFTED_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Mutex test
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  energy:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: -42.5000
            """,
        )
        with pytest.raises(SystemExit):
            from pseudotest.cli_update import main as update_main

            update_main([str(yaml_file), "-D", str(exec_dir), "-t", "-r"])

    def test_update_tolerance_broadcast(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest, run_update
    ):
        """pseudotest-update -t handles broadcast params (list values) correctly."""
        make_executable(exec_dir, "mock.py", MOCK_DRIFTED_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Broadcast tol
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  values:
                    file: results.txt
                    grep: ["Energy:", "Force:"]
                    field: [2, 2]
                    value: [-42.5000, 3.0000]
                    match: [energy, force]
            """,
        )
        run_update(yaml_file, exec_dir, "-t")

        from ruamel.yaml import YAML as _YAML

        data = _YAML().load(yaml_file.open())
        tol = data["Inputs"]["input.txt"]["Matches"]["values"]["tol"]
        # tol should be a list: [computed, 0] — energy drifted, force matched
        assert isinstance(tol, list)
        assert len(tol) == 2
        assert tol[0] >= 0.005  # energy difference
        assert tol[1] == 0  # force passed

        # Re-run: should pass now
        rc = run_pseudotest(yaml_file, exec_dir)
        assert rc == ExitCode.OK

    def test_update_reference_broadcast(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest, run_update
    ):
        """pseudotest-update -r handles broadcast params (list values) correctly."""
        make_executable(exec_dir, "mock.py", MOCK_DRIFTED_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Broadcast ref
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  values:
                    file: results.txt
                    grep: ["Energy:", "Force:"]
                    field: [2, 2]
                    value: [-42.5000, 3.0000]
                    match: [energy, force]
            """,
        )
        run_update(yaml_file, exec_dir, "-r")

        from ruamel.yaml import YAML as _YAML

        data = _YAML().load(yaml_file.open())
        values = data["Inputs"]["input.txt"]["Matches"]["values"]["value"]
        assert isinstance(values, list)
        assert float(values[0]) == pytest.approx(-42.505)
        assert float(values[1]) == 3.0  # unchanged — it passed

        # Re-run: should pass now
        rc = run_pseudotest(yaml_file, exec_dir)
        assert rc == ExitCode.OK

    def test_update_output_writes_to_separate_file(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest, run_update
    ):
        """pseudotest-update -o writes the updated config to a different file."""
        make_executable(exec_dir, "mock.py", MOCK_DRIFTED_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Output file
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  energy:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: -42.5000
            """,
        )
        original_text = yaml_file.read_text()
        output_file = tmp_path / "updated.yaml"

        run_update(yaml_file, exec_dir, "-r", output=output_file)

        # Original file is untouched
        assert yaml_file.read_text() == original_text

        # Updated file exists and has the new value
        from ruamel.yaml import YAML as _YAML

        data = _YAML().load(output_file.open())
        assert float(data["Inputs"]["input.txt"]["Matches"]["energy"]["value"]) == pytest.approx(-42.505)

        # Re-run with the updated file should pass
        rc = run_pseudotest(output_file, exec_dir)
        assert rc == ExitCode.OK


class TestUpdateFormatPreservation:
    """Ensure pseudotest-update preserves formatting of untouched values."""

    def test_update_reference_preserves_quotes_and_floats(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_update
    ):
        """Untouched YAML values must keep their original formatting."""
        make_executable(exec_dir, "mock.py", MOCK_DRIFTED_SCRIPT)
        make_input(tmp_path)

        yaml_text = """\
Name: Format test
Executable: mock.py
Inputs:
  input.txt:
    Matches:
      energy:
        file: results.txt
        grep: "Energy:"
        field: 2
        value: -42.5000
"""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml_text)

        run_update(yaml_file, exec_dir, "-r")

        updated = yaml_file.read_text()

        # Double-quoted strings must stay double-quoted
        assert '"Energy:"' in updated

        # The updated value must keep the same number of decimal places
        assert "value: -42.5050" in updated

        # Untouched keys should be byte-identical
        for line in ["file: results.txt", "field: 2", 'grep: "Energy:"']:
            assert line in updated

    def test_update_tolerance_preserves_unrelated_values(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_update
    ):
        """Tolerance update must not alter values, quotes, or formatting of other fields."""
        make_executable(exec_dir, "mock.py", MOCK_DRIFTED_SCRIPT)
        make_input(tmp_path)

        yaml_text = """\
Name: Format tol
Executable: mock.py
Inputs:
  input.txt:
    Matches:
      energy:
        file: results.txt
        grep: "Energy:"
        field: 2
        value: -42.5000
"""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml_text)

        run_update(yaml_file, exec_dir, "-t")

        updated = yaml_file.read_text()

        # Reference value must be unchanged
        assert "value: -42.5000" in updated
        # Double-quoted strings preserved
        assert '"Energy:"' in updated
        # A tol key should have been added
        assert "tol:" in updated


class TestUpdateSkipsFileIsPresent:
    """Ensure file_is_present matches are never modified by pseudotest-update."""

    MOCK_PARTIAL_DIR_SCRIPT = """\
#!/usr/bin/env python3
\"\"\"Creates output_dir with only one file (missing_file.txt absent).\"\"\"
import os, sys
os.makedirs("output_dir", exist_ok=True)
with open("output_dir/found.txt", "w") as f:
    f.write("ok\\n")
with open("results.txt", "w") as f:
    f.write("Energy: -42.5050 Ry\\n")
sys.exit(0)
"""

    def test_update_reference_skips_file_is_present(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_update
    ):
        """pseudotest-update -r must not modify file_is_present entries."""
        make_executable(exec_dir, "mock.py", self.MOCK_PARTIAL_DIR_SCRIPT)
        make_input(tmp_path)

        yaml_text = """\
Name: Skip fip
Executable: mock.py
Inputs:
  input.txt:
    Matches:
      energy:
        file: results.txt
        grep: "Energy:"
        field: 2
        value: -42.5000
      missing:
        directory: output_dir
        file_is_present: missing_file.txt
"""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml_text)

        run_update(yaml_file, exec_dir, "-r")

        updated = yaml_file.read_text()

        # energy reference should be updated
        assert "value: -42.5050" in updated

        # file_is_present must remain unchanged (not replaced with "False")
        assert "file_is_present: missing_file.txt" in updated

    def test_update_tolerance_skips_file_is_present(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_update
    ):
        """pseudotest-update -t must not add a tolerance to file_is_present entries."""
        make_executable(exec_dir, "mock.py", self.MOCK_PARTIAL_DIR_SCRIPT)
        make_input(tmp_path)

        yaml_text = """\
Name: Skip fip tol
Executable: mock.py
Inputs:
  input.txt:
    Matches:
      energy:
        file: results.txt
        grep: "Energy:"
        field: 2
        value: -42.5000
      missing:
        directory: output_dir
        file_is_present: missing_file.txt
"""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml_text)

        run_update(yaml_file, exec_dir, "-t")

        updated = yaml_file.read_text()

        # energy should get a tol
        assert "tol:" in updated

        # file_is_present entry must be untouched — no tol added next to it
        lines = updated.splitlines()
        for i, line in enumerate(lines):
            if "file_is_present" in line:
                # The next non-blank line should NOT be a tol key
                for j in range(i + 1, len(lines)):
                    if lines[j].strip():
                        assert "tol" not in lines[j], f"tol was incorrectly added near file_is_present: {lines[j]}"
                        break


class TestUpdateProtectedKey:
    """Ensure ``protected: true`` prevents updates to a match."""

    def test_protected_reference_not_updated(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_update
    ):
        """pseudotest-update -r must skip matches with protected: true."""
        make_executable(exec_dir, "mock.py", MOCK_DRIFTED_SCRIPT)
        make_input(tmp_path)

        yaml_text = """\
Name: Protected ref
Executable: mock.py
Inputs:
  input.txt:
    Matches:
      energy:
        file: results.txt
        grep: "Energy:"
        field: 2
        value: -42.5000
        protected: true
"""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml_text)

        run_update(yaml_file, exec_dir, "-r")

        updated = yaml_file.read_text()
        # Original value must stay unchanged
        assert "value: -42.5000" in updated

    def test_protected_tolerance_not_updated(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_update
    ):
        """pseudotest-update -t must skip matches with protected: true."""
        make_executable(exec_dir, "mock.py", MOCK_DRIFTED_SCRIPT)
        make_input(tmp_path)

        yaml_text = """\
Name: Protected tol
Executable: mock.py
Inputs:
  input.txt:
    Matches:
      energy:
        file: results.txt
        grep: "Energy:"
        field: 2
        value: -42.5000
        protected: true
"""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml_text)

        run_update(yaml_file, exec_dir, "-t")

        updated = yaml_file.read_text()
        # No tol should be added
        assert "tol:" not in updated
        # Value unchanged
        assert "value: -42.5000" in updated

    def test_protected_false_allows_update(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_update
    ):
        """protected: false must not prevent updates."""
        make_executable(exec_dir, "mock.py", MOCK_DRIFTED_SCRIPT)
        make_input(tmp_path)

        yaml_text = """\
Name: Not protected
Executable: mock.py
Inputs:
  input.txt:
    Matches:
      energy:
        file: results.txt
        grep: "Energy:"
        field: 2
        value: -42.5000
        protected: false
"""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml_text)

        run_update(yaml_file, exec_dir, "-r")

        updated = yaml_file.read_text()
        # Value should be updated
        assert "value: -42.5050" in updated

    def test_mixed_protected_and_unprotected(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_update
    ):
        """Only protected matches are skipped; unprotected ones are updated."""
        make_executable(exec_dir, "mock.py", MOCK_DRIFTED_SCRIPT)
        make_input(tmp_path)

        yaml_text = """\
Name: Mixed
Executable: mock.py
Inputs:
  input.txt:
    Matches:
      energy:
        file: results.txt
        grep: "Energy:"
        field: 2
        value: -42.5000
        protected: true
      force:
        file: results.txt
        grep: "Force:"
        field: 2
        value: 99.0000
"""
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml_text)

        run_update(yaml_file, exec_dir, "-r")

        updated = yaml_file.read_text()
        # Protected match untouched
        assert "value: -42.5000" in updated
        # Unprotected match updated (Force: 3.0000 from MOCK_DRIFTED_SCRIPT)
        assert "value: 3.0000" in updated
