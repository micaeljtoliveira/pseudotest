"""Test execution via subprocess for pseudotest.

Manages the process of running a single test input: resolving the executable, preparing files, launching the subprocess,
and capturing output.

Accepts an ``OutputFormatter`` via constructor so that presentation can be swapped or mocked independently.
"""

import logging
import shutil
import subprocess
import time
from collections import ChainMap
from pathlib import Path
from typing import Any, TextIO

from pseudotest.exceptions import UsageError
from pseudotest.formatting import OutputFormatter


class TestExecutor:
    """Execute a single test input in a temporary directory.

    Args:
        output_formatter: Formatter used to display stdout/stderr on failure.
    """

    def __init__(self, output_formatter: OutputFormatter | None = None):
        self.output_formatter = output_formatter or OutputFormatter()

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #

    def execute(
        self,
        input_config: ChainMap[str, Any],
        input_file: Path,
        test_dir: Path,
        exec_path: Path,
        temp_dir: Path,
        expected_failure: bool,
        timeout: int,
    ) -> tuple[bool, float]:
        """Run a single test input and return ``(success, elapsed_seconds)``.

        Args:
            input_config: Configuration scope for this specific input
            input_file: Input file to process
            test_dir: Directory containing test files
            exec_path: Directory containing executables
            temp_dir: Temporary working directory for execution
            expected_failure: Whether this test is expected to fail
            timeout: Execution timeout in seconds

        Returns:
            Tuple of (success_status, execution_time_seconds)
        """

        resolved_executable = self._resolve_executable(input_config, exec_path)

        extra_files = input_config.get("ExtraFiles", [])
        input_method = input_config.get("InputMethod", "argument")
        rename_target = input_config.get("RenameTo")

        working_input_name = self._prepare_files(
            input_file,
            test_dir,
            temp_dir,
            extra_files,
            input_method,
            rename_target,
        )

        command_args, stdin_file = self._build_command(
            resolved_executable,
            working_input_name,
            input_method,
            temp_dir,
        )

        return self._run_subprocess(
            command_args,
            stdin_file,
            temp_dir,
            working_input_name,
            input_file,
            expected_failure,
            timeout,
        )

    # --------------------------------------------------------------------- #
    # Private helpers
    # --------------------------------------------------------------------- #

    @staticmethod
    def _resolve_executable(
        input_config: ChainMap[str, Any],
        exec_path: Path,
    ) -> Path:
        """Validate and resolve the executable path."""

        executable_name = input_config["Executable"]
        executable_path = Path(exec_path) / executable_name

        if not executable_path.is_file():
            raise FileNotFoundError(f"Executable '{executable_name}' not available at {executable_path}")
        if not (executable_path.stat().st_mode & 0o111):
            raise PermissionError(f"Executable '{executable_name}' is not executable")

        resolved = executable_path if executable_path.is_absolute() else Path.cwd() / executable_path
        return resolved

    @staticmethod
    def _prepare_files(
        input_file: Path,
        test_dir: Path,
        temp_dir: Path,
        extra_files: list[str],
        input_method: str,
        rename_target: str | None,
    ) -> str:
        """Copy input and extra files into the temporary directory.

        Returns the working name of the input file inside *temp_dir*.
        """

        source_input_path = test_dir / input_file
        if not source_input_path.exists():
            raise FileNotFoundError(f"Input file not found: {source_input_path}")

        if input_method == "rename" and rename_target:
            shutil.copy2(source_input_path, temp_dir / rename_target)
            logging.debug(f"Copied input file: {input_file} -> {rename_target}")
            working_input_name = rename_target
        else:
            shutil.copy2(source_input_path, temp_dir)
            logging.debug(f"Copied input file: {input_file}")
            working_input_name = str(input_file)

        for extra_file in extra_files:
            source_extra_path = test_dir / extra_file
            if source_extra_path.exists():
                shutil.copy2(source_extra_path, temp_dir)
                logging.debug(f"Copied extra file: {extra_file}")
            else:
                raise FileNotFoundError(f"Extra file not found: {source_extra_path}")

        return working_input_name

    @staticmethod
    def _build_command(
        resolved_executable: Path,
        working_input_name: str,
        input_method: str,
        temp_dir: Path,
    ) -> tuple[list[str | Path], TextIO | None]:
        """Build the subprocess command and optional stdin file handle."""

        if input_method == "argument":
            command_args = [resolved_executable, working_input_name]
            stdin_file = None
            logging.info(f"Executing: {resolved_executable} {working_input_name}")
        elif input_method == "stdin":
            command_args = [resolved_executable]
            stdin_file = (temp_dir / working_input_name).open("r")
            logging.info(f"Executing: {resolved_executable} < {working_input_name}")
        elif input_method == "rename":
            command_args = [resolved_executable]
            stdin_file = None
            logging.info(f"Executing: {resolved_executable} (with {working_input_name} in working directory)")
        else:
            raise UsageError(f"Unknown input method: {input_method}")

        return command_args, stdin_file

    def _run_subprocess(
        self,
        command_args: list[str | Path],
        stdin_file: TextIO | None,
        temp_dir: Path,
        working_input_name: str,
        input_file: Path,
        expected_failure: bool,
        timeout: int,
    ) -> tuple[bool, float]:
        """Launch the subprocess and return ``(success, elapsed)``."""

        execution_success = False
        start_time = time.time()

        try:
            with (temp_dir / "stdout").open("w") as stdout_fh, (temp_dir / "stderr").open("w") as stderr_fh:
                process_result = subprocess.run(
                    command_args,
                    cwd=temp_dir,
                    stdout=stdout_fh,
                    stderr=stderr_fh,
                    stdin=stdin_file,
                    text=True,
                    timeout=timeout,
                )
            execution_success = process_result.returncode == 0

            if not execution_success:
                logging.debug(f"Executable failed with exit code {process_result.returncode}")
                if not expected_failure:
                    self.output_formatter.print_execution_output(temp_dir, str(input_file))

            stderr_content = (temp_dir / "stderr").read_text(errors="replace")
            if stderr_content and execution_success:
                logging.debug(f"STDERR: {stderr_content}")

        except subprocess.TimeoutExpired:
            logging.debug(f"Test execution timed out after {timeout} seconds")
            execution_success = False
            if not expected_failure:
                self.output_formatter.print_execution_output(temp_dir, str(input_file))
        except Exception as e:
            logging.debug(f"Test execution failed: {e}")
            execution_success = False
            if not expected_failure:
                self.output_formatter.print_execution_output(temp_dir, str(input_file))
        finally:
            if stdin_file:
                stdin_file.close()
            else:
                (temp_dir / working_input_name).unlink(missing_ok=True)

        execution_time = time.time() - start_time
        return execution_success, execution_time
