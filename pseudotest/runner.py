"""Test orchestration for pseudotest.

The ``PseudoTestRunner`` class coordinates the overall test workflow: loading configuration, iterating over inputs,
delegating execution to :class:`~pseudotest.executor.TestExecutor`, and delegating match evaluation to
:mod:`pseudotest.matchers`.
"""

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, ChainMap

from pseudotest.exceptions import ExitCode
from pseudotest.executor import TestExecutor
from pseudotest.formatting import Colors, OutputFormatter, display_match_status
from pseudotest.matchers import match
from pseudotest.test_config import RESERVED_KEYS, TestConfig, broadcast_params


class PseudoTestRunner:
    """Thin orchestrator for running YAML-based regression tests.

    Args:
        colors: Terminal colour helper (default: auto-detect TTY).
        executor: Test execution engine (default: subprocess-based).
    """

    def __init__(
        self,
        colors: Colors | None = None,
        executor: TestExecutor | None = None,
    ):
        self.colors = colors or Colors()
        self.executor = executor or TestExecutor(OutputFormatter(self.colors))
        self.failed_executions = 0
        self.failed_matches = 0
        self.total_matches = 0

    def run_matches(self, current_match_scope: ChainMap[str, Any], work_dir: Path, extra_indent: int = 2):
        """Recursively walk the match tree and evaluate every leaf match.

        Updates internal counters for total and failed matches.

        Args:
            current_match_scope: Match configuration scope containing
                parameters and nested matches
            work_dir: Working directory where output files are located
            extra_indent: Additional indentation level for nested output
        """
        local_match_params = {key: current_match_scope[key] for key in RESERVED_KEYS if key in current_match_scope}

        for match_name, match_definition in current_match_scope.items():
            if match_name in RESERVED_KEYS:
                continue

            combined_match_def = ChainMap(current_match_scope[match_name], local_match_params)

            if all(key in RESERVED_KEYS for key in match_definition):
                # Leaf match — evaluate it
                param_sets = broadcast_params(combined_match_def)

                if len(param_sets) > 1:
                    print(f"{' ' * (2 + extra_indent)}  {match_name:<{50 - extra_indent}}")
                    nested_indent = 2
                else:
                    nested_indent = 0

                for param_set in param_sets:
                    self.total_matches += 1
                    display_name = param_set.get("match", match_name) if len(param_sets) > 1 else match_name
                    match_success = match(display_name, param_set, work_dir, extra_indent=extra_indent + nested_indent)
                    if not match_success:
                        self.failed_matches += 1
            else:
                # Nested match group — recurse
                print(f"{' ' * (2 + extra_indent)}  {match_name:<{50 - extra_indent}}")
                self.run_matches(combined_match_def, work_dir, extra_indent + 2)

    def run(self, test_file_path: str, executable_directory: str, preserve_workdir: bool, timeout: int) -> int:
        """Main entry point for running tests.

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

        if not test_config.data.get("Enabled", True):
            print("Test disabled: skipping test")
            return ExitCode.OK

        test_directory = test_config_file.resolve().parent
        temp_work_dir = Path(tempfile.mkdtemp(prefix="pseudotest_"))
        print(f"Using workdir: {temp_work_dir}")

        # Process each test input
        print("Inputs:")
        for input_filename in test_config.data["Inputs"]:
            print(f"  {input_filename}:")

            input_scope = test_config.input_scope(input_filename)
            expected_failure = input_scope.get("ExpectedFailure", False)

            # Delegate execution to the executor (DIP)
            execution_success, execution_time = self.executor.execute(
                input_scope,
                Path(input_filename),
                test_directory,
                Path(executable_directory),
                temp_work_dir,
                expected_failure,
                timeout,
            )

            print(f"    Elapsed time: {execution_time:.3f}s")

            if expected_failure:
                execution_success = not execution_success
                display_match_status("Failed execution", execution_success)
            else:
                display_match_status("Execution", execution_success)

            self.failed_executions += 0 if execution_success else 1

            if execution_success:
                print("    Matches:")
                match_definitions = input_scope.get("Matches", [])
                self.run_matches(match_definitions, temp_work_dir)

        # Display test summary
        print("Test Summary:")
        print(f"  Failed executions : {self.failed_executions:-5}")
        print(f"  Total matches     : {self.total_matches:-5}")
        print(f"  Failed matches    : {self.failed_matches:-5}")

        if preserve_workdir:
            logging.debug(f"Preserved working directory: {temp_work_dir}")
        else:
            shutil.rmtree(temp_work_dir, ignore_errors=True)
            logging.debug(f"Removed working directory: {temp_work_dir}")

        return ExitCode.OK if (self.failed_executions == 0 and self.failed_matches == 0) else ExitCode.TEST_FAILURE
