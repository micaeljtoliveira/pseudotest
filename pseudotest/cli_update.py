"""Command-line interface for pseudotest-update.

A dedicated script for updating test configuration files after running
the tests.  Supports three mutually-exclusive update modes:

- **tolerance** (``-t``): widen tolerances to cover observed differences.
- **reference** (``-r``): replace reference values with calculated values
  for failing matches only.
- **reference-all** (``-R``): replace reference values with calculated
  values for all matches, including those that already pass.

The updated config is written back to the original file unless
``-o FILE`` is given.
"""

import argparse

from pseudotest.cli_run import add_common_arguments, run_tests
from pseudotest.config_updater import UpdateMode


def main(command_line_args: list[str] | None = None) -> int:
    """Entry point for the ``pseudotest-update`` command.

    Args:
        command_line_args: Command line arguments (defaults to sys.argv).

    Returns:
        Exit code for the process.
    """
    argument_parser = argparse.ArgumentParser(
        prog="pseudotest-update",
        description="Run regression tests and update the YAML config to fix match failures",
    )
    # -t and -r select the update mode, so the timeout and the report only have long options
    add_common_arguments(argument_parser, timeout_flags=("--timeout",), report_flags=("--report",))

    mode_group = argument_parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "-t",
        "--tolerance",
        action="store_const",
        const=UpdateMode.TOLERANCE,
        dest="update_mode",
        help="Update tolerances to cover observed differences",
    )
    mode_group.add_argument(
        "-r",
        "--reference",
        action="store_const",
        const=UpdateMode.REFERENCE,
        dest="update_mode",
        help="Update reference values for failing matches",
    )
    mode_group.add_argument(
        "-R",
        "--reference-all",
        action="store_const",
        const=UpdateMode.REFERENCE_ALL,
        dest="update_mode",
        help="Update reference values for all matches, including passing ones",
    )

    argument_parser.add_argument(
        "-o",
        "--output",
        default=None,
        metavar="FILE",
        help="Write updated config to FILE instead of overwriting the original",
    )
    parsed_args = argument_parser.parse_args(command_line_args)
    return run_tests(parsed_args, parsed_args.update_mode, parsed_args.output)
