"""Test orchestration for pseudotest.

The ``PseudoTestRunner`` class coordinates the overall test workflow: loading configuration, iterating over inputs,
delegating execution to :class:`~pseudotest.executor.TestExecutor`, and delegating match evaluation to
:mod:`pseudotest.matchers`.
"""

import logging
import shutil
import tempfile
from collections import ChainMap
from pathlib import Path
from typing import Any

from pseudotest.exceptions import ExitCode
from pseudotest.executor import TestExecutor
from pseudotest.formatting import Colors, OutputFormatter, display_match_status, indent
from pseudotest.matchers import match
from pseudotest.report import ReportWriter
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

    def run_matches(
        self,
        current_match_scope: ChainMap[str, Any],
        work_dir: Path,
        indent_level: int = 3,
    ) -> dict[str, Any]:
        """Recursively walk the match tree and evaluate every leaf match.

        Updates internal counters for total and failed matches.

        Args:
            current_match_scope: Match configuration scope containing
                parameters and nested matches
            work_dir: Working directory where output files are located
            indent_level: Nesting level for output display

        Returns:
            Nested dict of match results suitable for YAML serialisation.
        """
        local_match_params = {key: current_match_scope[key] for key in RESERVED_KEYS if key in current_match_scope}
        results: dict[str, Any] = {}

        for match_name, match_definition in current_match_scope.items():
            if match_name in RESERVED_KEYS:
                continue

            combined_match_def = ChainMap(current_match_scope[match_name], local_match_params)

            if all(key in RESERVED_KEYS for key in match_definition):
                # Leaf match, so evaluate it
                param_sets = broadcast_params(combined_match_def)

                if len(param_sets) > 1:
                    print(f"{indent(indent_level)}{match_name}")
                    nested_level = indent_level + 1
                else:
                    nested_level = indent_level

                for param_set in param_sets:
                    self.total_matches += 1
                    display_name = param_set.get("match", match_name) if len(param_sets) > 1 else match_name
                    match_success, calculated_value = match(
                        display_name, param_set, work_dir, indent_level=nested_level
                    )
                    if not match_success:
                        self.failed_matches += 1
                    results[display_name] = ReportWriter.build_match_entry(param_set, calculated_value)
            else:
                # Nested match group, need to recursively evaluate children
                print(f"{indent(indent_level)}{match_name}")
                results[match_name] = self.run_matches(combined_match_def, work_dir, indent_level + 1)

        return results

    def run(
        self,
        test_file_path: str,
        executable_directory: str,
        preserve_workdir: bool,
        timeout: int,
        report_file: str | None = None,
    ) -> int:
        """Main entry point for running tests.

        Args:
            test_file_path: Path to YAML test configuration file
            executable_directory: Directory containing executable binaries
            preserve_workdir: Whether to preserve temporary working directory
            timeout: Execution timeout in seconds
            report_file: Optional path to write a YAML execution report

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
        report_inputs: dict[str, Any] = {}

        print("Inputs:")
        for input_filename in test_config.data["Inputs"]:
            print(f"{indent(1)}{input_filename}:")

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

            print(f"{indent(2)}Elapsed time: {execution_time:.3f}s")

            if expected_failure:
                execution_success = not execution_success
                display_match_status("Failed execution", execution_success, indent_level=2)
            else:
                display_match_status("Execution", execution_success, indent_level=2)

            self.failed_executions += 0 if execution_success else 1

            input_report = ReportWriter.build_input_entry(
                input_scope, expected_failure, execution_success, execution_time
            )

            if execution_success:
                print(f"{indent(2)}Matches:")
                match_definitions = input_scope.get("Matches", {})
                match_results = self.run_matches(match_definitions, temp_work_dir)
                input_report["Matches"] = match_results

            report_inputs[input_filename] = input_report

        # Display test summary
        print("Test Summary:")
        print(f"{indent(1)}Failed executions : {self.failed_executions:-5}")
        print(f"{indent(1)}Total matches     : {self.total_matches:-5}")
        print(f"{indent(1)}Failed matches    : {self.failed_matches:-5}")

        if preserve_workdir:
            logging.debug(f"Preserved working directory: {temp_work_dir}")
        else:
            shutil.rmtree(temp_work_dir, ignore_errors=True)
            logging.debug(f"Removed working directory: {temp_work_dir}")

        exit_code = ExitCode.OK if (self.failed_executions == 0 and self.failed_matches == 0) else ExitCode.TEST_FAILURE

        # Write YAML report if requested
        if report_file:
            ReportWriter.write(report_file, test_file_path, test_config.data, report_inputs)

        return exit_code
