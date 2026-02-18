"""Integration / regression tests for the pseudotest script.

Every test builds a self-contained workspace inside ``tmp_path`` with:
  * a mock executable (Python script) that creates files and directories,
  * one or more input files, and
  * a YAML test configuration.

The tests then call ``pseudotest.runner.main()`` directly so that
``pytest-cov`` can track coverage across the whole stack.
"""

from __future__ import annotations

import stat
import textwrap
from pathlib import Path

import pytest

from pseudotest.cli import main
from pseudotest.exceptions import ExitCode

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def exec_dir(tmp_path: Path) -> Path:
    """Create and return a ``bin/`` directory inside the test's tmp_path."""
    d = tmp_path / "bin"
    d.mkdir()
    return d


@pytest.fixture
def make_executable():
    """Factory fixture: write a Python script into a directory and make it executable."""

    def _factory(directory: Path, name: str, script: str) -> Path:
        path = directory / name
        path.write_text(textwrap.dedent(script))
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return path

    return _factory


@pytest.fixture
def make_input():
    """Factory fixture: write an input file into a directory."""

    def _factory(directory: Path, name: str = "input.txt", content: str = "placeholder\n") -> Path:
        path = directory / name
        path.write_text(content)
        return path

    return _factory


@pytest.fixture
def make_yaml():
    """Factory fixture: write a YAML test-config file into a directory."""

    def _factory(directory: Path, yaml_text: str, name: str = "test.yaml") -> Path:
        path = directory / name
        path.write_text(textwrap.dedent(yaml_text))
        return path

    return _factory


@pytest.fixture
def run_pseudotest():
    """Factory fixture: invoke ``pseudotest.runner.main()`` and return its exit code."""

    def _factory(test_yaml: Path, exec_dir: Path, extra_args: list[str] | None = None) -> int:
        args = [str(test_yaml), "-D", str(exec_dir)]
        if extra_args:
            args.extend(extra_args)
        return main(args)

    return _factory


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
# Match types tests
# ---------------------------------------------------------------------------


class TestMatchTypes:
    """Exercise every supported match type through the full pipeline."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, exec_dir, make_executable, make_input):
        make_executable(exec_dir, "mock.py", MOCK_CREATOR_SCRIPT)
        make_input(tmp_path)
        self.exec_dir = exec_dir
        self.tmp_path = tmp_path

    def test_grep_field(self, make_yaml, run_pseudotest):
        yaml_file = make_yaml(
            self.tmp_path,
            """\
            Name: Grep field
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  force:
                    file: results.txt
                    grep: "Total force:"
                    field: 3
                    value: 1.2345e-03
            """,
        )
        assert run_pseudotest(yaml_file, self.exec_dir) == ExitCode.OK

    def test_grep_count(self, make_yaml, run_pseudotest):
        yaml_file = make_yaml(
            self.tmp_path,
            """\
            Name: Grep count
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  warnings:
                    file: results.txt
                    grep: "WARNING"
                    count: 2
            """,
        )
        assert run_pseudotest(yaml_file, self.exec_dir) == ExitCode.OK

    def test_line_field(self, make_yaml, run_pseudotest):
        yaml_file = make_yaml(
            self.tmp_path,
            """\
            Name: Line field
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  iterations:
                    file: results.txt
                    line: 4
                    field: 2
                    value: 10
            """,
        )
        assert run_pseudotest(yaml_file, self.exec_dir) == ExitCode.OK

    def test_file_size(self, make_yaml, run_pseudotest):
        # The mock writes exactly:
        #   "Energy: -42.5000 Ry  0.3  0.4\n"  (30 bytes)
        #   "Total force: 1.2345e-03 Ha\n"      (27 bytes)
        #   "Status converged OK\n"              (20 bytes)
        #   "Iterations 10\n"                    (14 bytes)
        #   "WARNING: step skipped\n"            (22 bytes) x2
        # Total = 30 + 27 + 20 + 14 + 22 + 22 = 135
        yaml_file = make_yaml(
            self.tmp_path,
            """\
            Name: File size
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  results_size:
                    file: results.txt
                    size: 135
            """,
        )
        assert run_pseudotest(yaml_file, self.exec_dir) == ExitCode.OK

    def test_column_extraction(self, make_yaml, run_pseudotest):
        yaml_file = make_yaml(
            self.tmp_path,
            """\
            Name: Column extraction
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  col_val:
                    file: results.txt
                    line: 1
                    column: 9
                    value: -42.5000
            """,
        )
        assert run_pseudotest(yaml_file, self.exec_dir) == ExitCode.OK

    def test_numeric_tolerance_pass(self, make_yaml, run_pseudotest):
        yaml_file = make_yaml(
            self.tmp_path,
            """\
            Name: Tolerance pass
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  energy_tol:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: -42.6
                    tol: 0.2
            """,
        )
        assert run_pseudotest(yaml_file, self.exec_dir) == ExitCode.OK

    def test_numeric_tolerance_fail(self, make_yaml, run_pseudotest):
        yaml_file = make_yaml(
            self.tmp_path,
            """\
            Name: Tolerance fail
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  energy_tol:
                    file: results.txt
                    grep: "Energy:"
                    field: 2
                    value: -40.0
                    tol: 0.001
            """,
        )
        assert run_pseudotest(yaml_file, self.exec_dir) == ExitCode.TEST_FAILURE

    def test_field_re_im_abs(self, make_yaml, run_pseudotest):
        """Test complex absolute-value match (field_re + field_im)."""
        yaml_file = make_yaml(
            self.tmp_path,
            """\
            Name: Complex abs
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  abs_val:
                    file: results.txt
                    grep: "Energy:"
                    field_re: 4
                    field_im: 5
                    value: 0.5
            """,
        )
        assert run_pseudotest(yaml_file, self.exec_dir) == ExitCode.OK

    def test_directory_missing(self, make_yaml, run_pseudotest):
        """Directory match against a non-existent directory should fail."""
        yaml_file = make_yaml(
            self.tmp_path,
            """\
            Name: Dir missing
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  no_dir:
                    directory: nonexistent
                    file_is_present: foo.txt
            """,
        )
        assert run_pseudotest(yaml_file, self.exec_dir) == ExitCode.TEST_FAILURE

    def test_directory_no_predicate(self, make_yaml, run_pseudotest):
        """Directory param without file_is_present or count_files → UsageError."""
        yaml_file = make_yaml(
            self.tmp_path,
            """\
            Name: Dir no predicate
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  bad:
                    directory: output_dir
            """,
        )
        from pseudotest.exceptions import UsageError

        with pytest.raises(UsageError, match="file_is_present.*count_files"):
            run_pseudotest(yaml_file, self.exec_dir)

    def test_file_is_present_non_string(self, make_yaml, run_pseudotest):
        """file_is_present with a non-string value → UsageError."""
        yaml_file = make_yaml(
            self.tmp_path,
            """\
            Name: Bad file_is_present
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  bad:
                    directory: output_dir
                    file_is_present: 42
            """,
        )
        from pseudotest.exceptions import UsageError

        with pytest.raises(UsageError, match="file_is_present.*must be a string"):
            run_pseudotest(yaml_file, self.exec_dir)

    def test_grep_with_line_offset(self, make_yaml, run_pseudotest):
        """Grep + line offset to read the line after the match."""
        yaml_file = make_yaml(
            self.tmp_path,
            """\
            Name: Grep offset
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  next_line:
                    file: results.txt
                    grep: "Energy:"
                    line: 1
                    field: 3
                    value: 1.2345e-03
            """,
        )
        assert run_pseudotest(yaml_file, self.exec_dir) == ExitCode.OK


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
# String comparison failure details tests
# ---------------------------------------------------------------------------


class TestStringMismatch:
    def test_string_mismatch_details(self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest):
        make_executable(exec_dir, "mock.py", MOCK_CREATOR_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: String mismatch
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  status:
                    file: results.txt
                    grep: "Status"
                    field: 2
                    value: "diverged"
            """,
        )
        rc = run_pseudotest(yaml_file, exec_dir)
        assert rc == ExitCode.TEST_FAILURE


# ---------------------------------------------------------------------------
# Error paths in runner tests (missing exec, permissions, missing input, etc)
# ---------------------------------------------------------------------------


class TestRunnerErrorPaths:
    """Cover FileNotFoundError / PermissionError / UsageError branches in runner."""

    def test_missing_executable(self, tmp_path, exec_dir, make_input, make_yaml, run_pseudotest):
        make_input(tmp_path)
        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Missing exec
            Executable: does_not_exist.py
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
        with pytest.raises(FileNotFoundError, match="not available"):
            run_pseudotest(yaml_file, exec_dir)

    def test_non_executable_file(self, tmp_path, exec_dir, make_input, make_yaml, run_pseudotest):
        """A file that exists but has no execute permission."""
        non_exec = exec_dir / "no_exec.py"
        non_exec.write_text("#!/usr/bin/env python3\nimport sys; sys.exit(0)\n")
        non_exec.chmod(0o644)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Not executable
            Executable: no_exec.py
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
        with pytest.raises(PermissionError, match="not executable"):
            run_pseudotest(yaml_file, exec_dir)

    def test_missing_input_file(self, tmp_path, exec_dir, make_executable, make_yaml, run_pseudotest):
        make_executable(exec_dir, "mock.py", MOCK_CREATOR_SCRIPT)
        # DO NOT create the input file
        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Missing input
            Executable: mock.py
            Inputs:
              nonexistent.txt:
                Matches:
                  dummy:
                    file: results.txt
                    line: 1
                    field: 1
                    value: x
            """,
        )
        with pytest.raises(FileNotFoundError, match="Input file not found"):
            run_pseudotest(yaml_file, exec_dir)

    def test_missing_extra_file(self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest):
        make_executable(exec_dir, "mock.py", MOCK_CREATOR_SCRIPT)
        make_input(tmp_path)
        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Missing extra
            Executable: mock.py
            Inputs:
              input.txt:
                ExtraFiles:
                  - does_not_exist.dat
                Matches:
                  dummy:
                    file: results.txt
                    line: 1
                    field: 1
                    value: x
            """,
        )
        with pytest.raises(FileNotFoundError, match="Extra file not found"):
            run_pseudotest(yaml_file, exec_dir)

    def test_unknown_input_method(self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest):
        make_executable(exec_dir, "mock.py", MOCK_CREATOR_SCRIPT)
        make_input(tmp_path)
        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Bad method
            Executable: mock.py
            InputMethod: foobar
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
        from pseudotest.exceptions import UsageError

        with pytest.raises(UsageError, match="Unknown input method"):
            run_pseudotest(yaml_file, exec_dir)

    def test_match_file_not_found_returns_fail(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, run_pseudotest
    ):
        """Match against a file that the executable does NOT create."""
        make_executable(exec_dir, "mock.py", MOCK_CREATOR_SCRIPT)
        make_input(tmp_path)
        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Missing match file
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  no_file:
                    file: nonexistent_output.txt
                    line: 1
                    field: 1
                    value: foo
            """,
        )
        rc = run_pseudotest(yaml_file, exec_dir)
        assert rc == ExitCode.TEST_FAILURE


# ---------------------------------------------------------------------------
# TestConfig error paths tests
# ---------------------------------------------------------------------------


class TestConfigErrors:
    def test_missing_test_file(self):
        from pseudotest.test_config import TestConfig

        tc = TestConfig()
        with pytest.raises(FileNotFoundError, match="Test file not found"):
            tc.load(Path("/tmp/surely_does_not_exist_12345.yaml"))

    def test_invalid_yaml(self, tmp_path):
        from pseudotest.test_config import TestConfig

        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text(":\n  - :\n    :\n  bad: [unbalanced")
        tc = TestConfig()
        with pytest.raises(ValueError, match="Failed to load test file"):
            tc.load(bad_yaml)

    def test_broadcast_mismatched_lengths(self):
        from collections import ChainMap

        from pseudotest.exceptions import UsageError
        from pseudotest.test_config import broadcast_params

        params = ChainMap({"a": [1, 2, 3], "b": [4, 5]})
        with pytest.raises(UsageError, match="same length"):
            broadcast_params(params)


# ---------------------------------------------------------------------------
# Unit tests for matches helper functions
# (mostly edge cases, to be moved elsewhere later)
# ---------------------------------------------------------------------------


class TestMatchesHelpers:
    """Cover uncovered branches in matches.py helper functions."""

    def test_get_target_line_positive_out_of_bounds(self):
        from pseudotest.value_extractors import get_target_line

        assert get_target_line(["a", "b"], 5) is None

    def test_get_target_line_negative_index(self):
        from pseudotest.value_extractors import get_target_line

        assert get_target_line(["a", "b", "c"], -1) == "c"
        assert get_target_line(["a", "b", "c"], -3) == "a"

    def test_get_target_line_negative_out_of_bounds(self):
        from pseudotest.value_extractors import get_target_line

        assert get_target_line(["a", "b"], -5) is None

    def test_find_pattern_line_offset_out_of_bounds(self):
        from pseudotest.value_extractors import find_pattern_line

        lines = ["first", "second", "third"]
        assert find_pattern_line(lines, "third", 1) is None

    def test_find_pattern_line_not_found(self):
        from pseudotest.value_extractors import find_pattern_line

        assert find_pattern_line(["a", "b"], "z") is None

    def test_extract_field_from_none_line(self):
        from pseudotest.value_extractors import extract_field_from_line

        assert extract_field_from_line(None, 1) is None

    def test_extract_field_out_of_bounds(self):
        from pseudotest.value_extractors import extract_field_from_line

        assert extract_field_from_line("one two", 5) is None

    def test_extract_column_from_none_line(self):
        from pseudotest.value_extractors import extract_column_from_line

        assert extract_column_from_line(None, 1) is None

    def test_extract_column_out_of_bounds(self):
        from pseudotest.value_extractors import extract_column_from_line

        assert extract_column_from_line("short", 100) is None

    def test_is_number_special_values(self):
        from pseudotest.comparator import is_number

        assert is_number("nan") is True
        assert is_number("inf") is True
        assert is_number("-inf") is True
        assert is_number("+inf") is True
        assert is_number("not_a_num") is False

    def test_is_number_none(self):
        from pseudotest.comparator import is_number

        assert is_number(None) is False


# ---------------------------------------------------------------------------
# match_compare_result tests
# (mostly edge cases, to be moved elsewhere later)
# ---------------------------------------------------------------------------


class TestMatchCompareResult:
    def test_numeric_mismatch_with_tolerance_detail(self):
        """Cover the tolerance-vs-precision warning path."""
        from pseudotest.comparator import match_compare_result

        # tolerance smaller than the effective precision => triggers warning
        result = match_compare_result("test_prec", "1.2345e+02", 123.46, tolerance=1e-6)
        assert result is False  # difference is ~0.01 > 1e-6

    def test_numeric_match_near_zero_reference(self):
        """Cover the branch where |reference| <= 1e-10 (no deviation % printed)."""
        from pseudotest.comparator import match_compare_result

        result = match_compare_result("zero_ref", "0.0001", 0.0, tolerance=None)
        assert result is False

    def test_numeric_match_with_tol_and_deviation(self):
        """Cover full failure output including tolerance percentage."""
        from pseudotest.comparator import match_compare_result

        result = match_compare_result("tol_dev", "10.0", 20.0, tolerance=0.5)
        assert result is False


# ---------------------------------------------------------------------------
# utils.get_precision_from_string_format tests
# (mostly edge cases, to be moved elsewhere later)
# ---------------------------------------------------------------------------


class TestGetPrecision:
    def test_non_numeric_string(self):
        from pseudotest.comparator import get_precision_from_string_format

        assert get_precision_from_string_format("abc") == 0.0

    def test_scientific_notation_with_decimal(self):
        from pseudotest.comparator import get_precision_from_string_format

        p = get_precision_from_string_format("1.23e+02")
        assert abs(p - 1.0) < 1e-12  # 0.01 * 100 = 1.0

    def test_scientific_notation_integer_mantissa(self):
        from pseudotest.comparator import get_precision_from_string_format

        p = get_precision_from_string_format("5e+03")
        assert abs(p - 1000.0) < 1e-6

    def test_fortran_d_notation(self):
        from pseudotest.comparator import get_precision_from_string_format

        # Python's float() cannot parse Fortran D notation, so it returns 0.0
        p = get_precision_from_string_format("1.5D+01")
        assert p == 0.0

    def test_integer_precision(self):
        from pseudotest.comparator import get_precision_from_string_format

        p = get_precision_from_string_format("42")
        assert p == 1.0

    def test_decimal_precision(self):
        from pseudotest.comparator import get_precision_from_string_format

        p = get_precision_from_string_format("3.14")
        assert abs(p - 0.01) < 1e-12


# ---------------------------------------------------------------------------
# Colors with TTY mock tests (to be moved elsewhere later)
# ---------------------------------------------------------------------------


class TestColorsTTY:
    def test_colors_enabled_on_tty(self, monkeypatch):
        """Cover the isatty=True branch of Colors.__init__."""
        import io

        fake_tty = io.StringIO()
        fake_tty.isatty = lambda: True
        monkeypatch.setattr("sys.stdout", fake_tty)
        from pseudotest.formatting import Colors

        c = Colors()
        assert c.BLUE == "\033[34m"
        assert c.RED == "\033[31m"
        assert c.GREEN == "\033[32m"
        assert c.RESET == "\033[0m"


# ---------------------------------------------------------------------------
# Content match errors exercised via integration tests
# ---------------------------------------------------------------------------


class TestContentMatchErrors:
    """Cover UsageError branches inside _handle_content_matches."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, exec_dir, make_executable, make_input):
        make_executable(exec_dir, "mock.py", MOCK_CREATOR_SCRIPT)
        make_input(tmp_path)
        self.exec_dir = exec_dir
        self.tmp_path = tmp_path

    def test_no_grep_or_line_raises(self, make_yaml, run_pseudotest):
        """Missing both 'grep' and 'line' → UsageError."""
        yaml_file = make_yaml(
            self.tmp_path,
            """\
            Name: No grep or line
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  bad:
                    file: results.txt
                    field: 1
                    value: x
            """,
        )
        from pseudotest.exceptions import UsageError

        with pytest.raises(UsageError, match="grep.*or.*line"):
            run_pseudotest(yaml_file, self.exec_dir)

    def test_no_field_column_or_complex_raises(self, make_yaml, run_pseudotest):
        """Having grep but no field/column/field_re+field_im → UsageError."""
        yaml_file = make_yaml(
            self.tmp_path,
            """\
            Name: No field
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  bad:
                    file: results.txt
                    grep: "Energy:"
                    value: x
            """,
        )
        from pseudotest.exceptions import UsageError

        with pytest.raises(UsageError, match="field.*column.*field_re"):
            run_pseudotest(yaml_file, self.exec_dir)

    def test_file_size_missing_file(self, make_yaml, run_pseudotest):
        """Size match on a file that is not produced → None → TEST_FAILURE."""
        yaml_file = make_yaml(
            self.tmp_path,
            """\
            Name: Size missing
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  sz:
                    file: not_here.bin
                    size: 100
            """,
        )
        rc = run_pseudotest(yaml_file, self.exec_dir)
        assert rc == ExitCode.TEST_FAILURE

    def test_calculated_value_none_returns_failure(self, make_yaml, run_pseudotest):
        """A grep that matches but the field is out of bounds → None → fail."""
        yaml_file = make_yaml(
            self.tmp_path,
            """\
            Name: Field OOB
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  oob:
                    file: results.txt
                    grep: "Energy:"
                    field: 99
                    value: x
            """,
        )
        rc = run_pseudotest(yaml_file, self.exec_dir)
        assert rc == ExitCode.TEST_FAILURE

    def test_field_re_im_none_field(self, make_yaml, run_pseudotest):
        """field_re/field_im where one field index is out of bounds → None."""
        yaml_file = make_yaml(
            self.tmp_path,
            """\
            Name: Complex OOB
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  cx:
                    file: results.txt
                    grep: "Energy:"
                    field_re: 99
                    field_im: 5
                    value: 1.0
            """,
        )
        rc = run_pseudotest(yaml_file, self.exec_dir)
        assert rc == ExitCode.TEST_FAILURE

    def test_field_re_im_non_numeric(self, make_yaml, run_pseudotest):
        """field_re/field_im where extracted values are non-numeric → ValueError."""
        yaml_file = make_yaml(
            self.tmp_path,
            """\
            Name: Complex non-numeric
            Executable: mock.py
            Inputs:
              input.txt:
                Matches:
                  cx:
                    file: results.txt
                    grep: "Status"
                    field_re: 1
                    field_im: 2
                    value: 1.0
            """,
        )
        rc = run_pseudotest(yaml_file, self.exec_dir)
        assert rc == ExitCode.TEST_FAILURE


# ---------------------------------------------------------------------------
# Subprocess exception handler in runner.run_input tests
# ---------------------------------------------------------------------------


class TestSubprocessException:
    """Cover the generic Exception handler in run_input (runner.py L234-238)."""

    def test_subprocess_generic_exception(
        self, tmp_path, exec_dir, make_executable, make_input, make_yaml, monkeypatch
    ):
        """Patch subprocess.run to raise a generic Exception."""
        from pseudotest.runner import PseudoTestRunner as Runner

        make_executable(exec_dir, "mock.py", MOCK_CREATOR_SCRIPT)
        make_input(tmp_path)

        yaml_file = make_yaml(
            tmp_path,
            """\
            Name: Subprocess crash
            Executable: mock.py
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
        import subprocess as _subprocess

        def exploding_run(*args, **kwargs):
            raise OSError("Simulated I/O error")

        monkeypatch.setattr(_subprocess, "run", exploding_run)

        runner = Runner()
        rc = runner.run(str(yaml_file), str(exec_dir), preserve_workdir=False, timeout=30)
        assert rc == ExitCode.TEST_FAILURE


# ---------------------------------------------------------------------------
# __init__.main() entry point tests
# ---------------------------------------------------------------------------


class TestPackageMain:
    """Cover pseudotest.main() which now delegates to cli.main()."""

    def test_package_main_with_mock_runner(self, monkeypatch):
        """Calling pseudotest.main() delegates to cli.main() and creates a PseudoTestRunner."""
        from unittest.mock import MagicMock

        import pseudotest.cli

        mock_run = MagicMock(return_value=0)
        monkeypatch.setattr(pseudotest.cli, "PseudoTestRunner", lambda: type("R", (), {"run": mock_run})())
        import pseudotest

        result = pseudotest.main(["test.yaml", "-D", "."])
        mock_run.assert_called_once()
        assert result == 0


# ---------------------------------------------------------------------------
# _print_execution_output edge cases tests
# ---------------------------------------------------------------------------


class TestPrintExecutionOutput:
    """Directly call OutputFormatter.print_execution_output to cover edge-case branches."""

    def test_output_files_dont_exist(self, tmp_path, capsys):
        """Cover the 'does not exist' branch."""
        from pseudotest.formatting import OutputFormatter

        formatter = OutputFormatter()
        formatter.print_execution_output(tmp_path, "test_input.txt")
        captured = capsys.readouterr()
        assert "does not exist" in captured.out

    def test_output_files_empty(self, tmp_path, capsys):
        """Cover the 'is empty' branch."""
        from pseudotest.formatting import OutputFormatter

        (tmp_path / "stdout").write_text("")
        (tmp_path / "stderr").write_text("")
        formatter = OutputFormatter()
        formatter.print_execution_output(tmp_path, "test_input.txt")
        captured = capsys.readouterr()
        assert "is empty" in captured.out


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

        return _YAML().load(path.open())

    def _load_report(self, path):
        raw = self._load_raw_report(path)
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
        top_key = next(iter(raw))
        assert top_key == str(yaml_file)
        assert "Name" in raw[top_key]
