#!/usr/bin/env python3
"""
YAML-based regression test runner for kraken-md

This script reads YAML test files and executes regression tests with match validation.
"""

import argparse
import logging
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any, ChainMap, Optional

from pseudotest.matches import match
from pseudotest.test_config import RESERVED_KEYS, TestConfig, broadcast_params
from pseudotest.utils import CliError, Colors, ExitCode, UsageError, display_match_status


class PseudoTestRunner:
    """Main class for running YAML-based regression tests"""

    def __init__(self):
        self.colors = Colors()
        self.failed_executions = 0
        self.failed_matches = 0
        self.total_matches = 0

    def _print_execution_output(self, temp_dir: Path, input_file: str) -> None:
        """Print stdout and stderr output from failed execution

        Args:
            temp_dir: Directory containing stdout and stderr files
            input_file: Name of the input file for context
        """
        stdout_file = temp_dir / "stdout"
        stderr_file = temp_dir / "stderr"

        # Check current logging level to determine how much to show
        show_full_output = logging.getLogger().isEnabledFor(logging.DEBUG)

        for output_file, output_name in [(stdout_file, "STDOUT"), (stderr_file, "STDERR")]:
            if output_file.exists():
                try:
                    content = output_file.read_text(errors="replace")
                    if content.strip():  # Show content if there's actual content
                        lines = content.splitlines()

                        print(f"\n{self.colors.RED}=== {output_name} from {input_file} ==={self.colors.RESET}")

                        if show_full_output or len(lines) <= 10:
                            # Show full content in debug mode or if <= 10 lines
                            print(content)
                        else:
                            # Show last 10 lines in normal mode
                            print("... (showing last 10 lines, use -vv to see full output)")
                            print("\n".join(lines[-10:]))

                        print(f"{self.colors.RED}=== End {output_name} ==={self.colors.RESET}")
                    else:
                        # Inform user when file is empty
                        print(f"\n{self.colors.RED}=== {output_name} from {input_file} is empty ==={self.colors.RESET}")
                except Exception as e:
                    logging.debug(f"Failed to read {output_name} file: {e}")
            else:
                # Inform user when file doesn't exist
                print(f"\n{self.colors.RED}=== {output_name} from {input_file} does not exist ==={self.colors.RESET}")

    def run_matches(self, current_match_scope: ChainMap[str, Any], work_dir: Path, extra_indent: int = 2):
        """Run all matches and return overall success

        Updates internal counters for total and failed matches.

        Args:
            current_match_scope: Match configuration scope containing parameters and nested matches
            work_dir: Working directory where output files are located
            extra_indent: Additional indentation level for nested output
        """
        # Extract match parameters that apply to all matches in this scope
        local_match_params = {key: current_match_scope[key] for key in RESERVED_KEYS if key in current_match_scope}

        for match_name, match_definition in current_match_scope.items():
            if match_name in RESERVED_KEYS:
                continue  # Skip reserved keys at this level

            # Combine local match definition with inherited parameters
            combined_match_def = ChainMap(current_match_scope[match_name], local_match_params)

            if all(key in RESERVED_KEYS for key in match_definition):
                # This is a leaf match definition, run the match
                param_sets = broadcast_params(combined_match_def)

                # Handle display formatting for multiple parameter sets
                if len(param_sets) > 1:
                    print(f"{' ' * (2 + extra_indent)}  {match_name:<{50 - extra_indent}}")
                    nested_indent = 2
                else:
                    nested_indent = 0

                for param_set in param_sets:
                    self.total_matches += 1
                    # Use custom match name if provided for multi-parameter sets
                    display_name = param_set.get("match", match_name) if len(param_sets) > 1 else match_name
                    match_success = match(display_name, param_set, work_dir, extra_indent=extra_indent + nested_indent)
                    if not match_success:
                        self.failed_matches += 1
            else:
                # This is a nested match group, recursively run matches
                print(f"{' ' * (2 + extra_indent)}  {match_name:<{50 - extra_indent}}")
                self.run_matches(combined_match_def, work_dir, extra_indent + 2)

    def run_input(  # noqa: C901
        self,
        input_config: ChainMap[str, Any],
        input_file: Path,
        test_dir: Path,
        exec_path: Path,
        temp_dir: Path,
        expected_failure: bool,
        timeout: int,
    ) -> tuple[bool, float]:
        """Run a single test input and return success status and execution time

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
        # Get executable configuration
        executable_name = input_config["Executable"]
        executable_path = Path(exec_path) / executable_name

        if not executable_path.is_file():
            raise FileNotFoundError(f"Executable '{executable_name}' not available at {executable_path}")
        if not (executable_path.stat().st_mode & 0o111):
            raise PermissionError(f"Executable '{executable_name}' is not executable")

        # Process test input configuration
        extra_files = input_config.get("ExtraFiles", [])
        input_method = input_config.get("InputMethod", "argument")  # Default to argument method
        rename_target = input_config.get("RenameTo")  # For rename method

        # Copy input file to temporary directory
        source_input_path = test_dir / input_file
        if not source_input_path.exists():
            raise FileNotFoundError(f"Input file not found: {source_input_path}")

        # Handle different input methods for file placement
        if input_method == "rename" and rename_target:
            # Rename the input file to the specified name
            shutil.copy2(source_input_path, temp_dir / rename_target)
            logging.debug(f"Copied input file: {input_file} -> {rename_target}")
            working_input_name = rename_target
        else:
            # Standard copy for argument and stdin methods
            shutil.copy2(source_input_path, temp_dir)
            logging.debug(f"Copied input file: {input_file}")
            working_input_name = input_file

        # Copy additional required files
        for extra_file in extra_files:
            source_extra_path = test_dir / extra_file
            if source_extra_path.exists():
                shutil.copy2(source_extra_path, temp_dir)
                logging.debug(f"Copied extra file: {extra_file}")
            else:
                raise FileNotFoundError(f"Extra file not found: {source_extra_path}")

        # Resolve absolute executable path for subprocess
        resolved_executable = executable_path if executable_path.is_absolute() else Path.cwd() / executable_path

        # Prepare command arguments and stdin based on input method
        if input_method == "argument":
            # Pass input file as first argument (default behavior)
            command_args = [resolved_executable, working_input_name]
            stdin_file = None
            logging.info(f"Executing: {resolved_executable} {working_input_name}")
        elif input_method == "stdin":
            # Redirect input file to stdin
            command_args = [resolved_executable]
            stdin_file = (temp_dir / working_input_name).open("r")
            logging.info(f"Executing: {resolved_executable} < {working_input_name}")
        elif input_method == "rename":
            # Input file was renamed, just run executable without arguments
            command_args = [resolved_executable]
            stdin_file = None
            logging.info(f"Executing: {resolved_executable} (with {working_input_name} in working directory)")
        else:
            raise UsageError(f"Unknown input method: {input_method}")

        # Execute the command and capture output
        execution_success = False
        start_time = time.time()
        try:
            with (temp_dir / "stdout").open("w") as stdout_file, (temp_dir / "stderr").open("w") as stderr_file:
                process_result = subprocess.run(
                    command_args,
                    cwd=temp_dir,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    stdin=stdin_file,
                    text=True,
                    timeout=timeout,
                )
            execution_success = process_result.returncode == 0

            if not execution_success:
                logging.debug(f"Executable failed with exit code {process_result.returncode}")
                # Print stdout and stderr output for failed executions (only if not expected to fail)
                if not expected_failure:
                    self._print_execution_output(temp_dir, str(input_file))

            # Log any error output for debugging
            stderr_content = (temp_dir / "stderr").read_text(errors="replace")
            if stderr_content and execution_success:  # Only log in debug for successful runs
                logging.debug(f"STDERR: {stderr_content}")

        except subprocess.TimeoutExpired:
            logging.debug(f"Test execution timed out after {timeout} seconds")
            execution_success = False
            if not expected_failure:
                self._print_execution_output(temp_dir, str(input_file))
        except Exception as e:
            logging.debug(f"Test execution failed: {e}")
            execution_success = False
            if not expected_failure:
                self._print_execution_output(temp_dir, str(input_file))
        finally:
            # Clean up resources
            if stdin_file:
                stdin_file.close()
            else:
                # Remove input file if not using stdin
                (temp_dir / working_input_name).unlink(missing_ok=True)

        execution_time = time.time() - start_time
        return execution_success, execution_time

    def run(self, test_file_path: str, executable_directory: str, preserve_workdir: bool, timeout: int) -> int:
        """Main entry point for running tests

        Args:
            test_file_path: Path to YAML test configuration file
            executable_directory: Directory containing executable binaries
            preserve_workdir: Whether to preserve temporary working directory
            timeout: Execution timeout in seconds

        Returns:
            Exit code (0 for success, non-zero for failure)
        """
        # Load and validate test configuration
        test_config_file = Path(test_file_path)
        test_config = TestConfig()
        test_config.load(test_config_file)

        print(f"{self.colors.BLUE}***** {test_config.data['Name']} *****{self.colors.RESET}")

        # Check if test is enabled
        if not test_config.data.get("Enabled", True):
            print("Test disabled: skipping test")
            return ExitCode.OK  # Skip is considered success

        # Get test directory (same as test file location)
        test_directory = test_config_file.resolve().parent

        # Create temporary working directory
        temp_work_dir = Path(tempfile.mkdtemp(prefix="pseudotest_"))
        print(f"Using workdir: {temp_work_dir}")

        # Process each test input
        print("Inputs:")
        for input_filename in test_config.data["Inputs"]:
            print(f"  {input_filename}:")

            # Get configuration scope for this specific input
            input_scope = test_config.input_scope(input_filename)
            expected_failure = input_scope.get("ExpectedFailure", False)

            # Execute the test input
            execution_success, execution_time = self.run_input(
                input_scope,
                Path(input_filename),
                test_directory,
                Path(executable_directory),
                temp_work_dir,
                expected_failure,
                timeout,
            )

            # Display execution time
            print(f"    Elapsed time: {execution_time:.3f}s")

            # Handle expected failure cases
            if expected_failure:
                execution_success = not execution_success
                display_match_status("Failed execution", execution_success)
            else:
                display_match_status("Execution", execution_success)

            self.failed_executions += 0 if execution_success else 1

            # Run matches only if execution was successful (or expected to fail and did)
            if execution_success:
                print("    Matches:")
                match_definitions = input_scope.get("Matches", [])
                self.run_matches(match_definitions, temp_work_dir)

        # Display test summary
        print("Test Summary:")
        print(f"  Failed executions : {self.failed_executions:-5}")
        print(f"  Total matches     : {self.total_matches:-5}")
        print(f"  Failed matches    : {self.failed_matches:-5}")

        # Clean up temporary working directory
        if preserve_workdir:
            logging.debug(f"Preserved working directory: {temp_work_dir}")
        else:
            shutil.rmtree(temp_work_dir, ignore_errors=True)
            logging.debug(f"Removed working directory: {temp_work_dir}")

        # Return appropriate exit code
        return ExitCode.OK if (self.failed_executions == 0 and self.failed_matches == 0) else ExitCode.TEST_FAILURE


def setup_logging(verbosity_level: int) -> None:
    """Configure logging based on verbosity level

    Args:
        verbosity_level: 0=WARNING, 1=INFO, 2+=DEBUG
    """
    if verbosity_level == 0:
        level = logging.WARNING
    elif verbosity_level == 1:
        level = logging.INFO
    else:
        level = logging.DEBUG

    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )


def main(command_line_args: Optional[list[str]] = None) -> int:
    """Main entry point for command line execution

    Args:
        command_line_args: Command line arguments (defaults to sys.argv)

    Returns:
        Exit code for the process
    """
    argument_parser = argparse.ArgumentParser(
        prog="pseudotest",
        description="Regression testing utility for scientific software",
        exit_on_error=True,
    )
    argument_parser.add_argument("test_file", help="YAML file describing the test to run")
    argument_parser.add_argument("-D", "--directory", default=".", help="Directory containing the executables")
    argument_parser.add_argument("-p", "--preserve", action="store_true", help="Preserve working directory after test")
    argument_parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v for INFO, -vv for DEBUG)",
    )
    argument_parser.add_argument(
        "-t",
        "--timeout",
        type=int,
        default=600,
        help="Execution timeout in seconds (default: 600, i.e., 10 minutes)",
    )
    parsed_args = argument_parser.parse_args(command_line_args)

    setup_logging(parsed_args.verbose)
    test_runner = PseudoTestRunner()
    return test_runner.run(parsed_args.test_file, parsed_args.directory, parsed_args.preserve, parsed_args.timeout)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CliError as e:
        logging.error(e)
        sys.exit(e.exit_code)
    except Exception:
        logging.error("internal error (use --vv for traceback)")
        # We do not have config here, so inspect argv instead
        if "--vv" in sys.argv:
            traceback.print_exc()
        sys.exit(ExitCode.INTERNAL)
