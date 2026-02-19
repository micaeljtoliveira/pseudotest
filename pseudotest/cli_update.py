"""Command-line interface for pseudotest-update.

A dedicated script for updating test configuration files after running
the tests.  Supports two mutually-exclusive update modes:

- **tolerance** (``-t``): widen tolerances to cover observed differences.
- **reference** (``-r``): replace reference values with calculated values.

The updated config is written back to the original file unless
``-o FILE`` is given.
"""

import argparse
import logging
import sys
import traceback

from pseudotest.cli_run import setup_logging
from pseudotest.exceptions import CliError, ExitCode
from pseudotest.runner import PseudoTestRunner


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
        exit_on_error=True,
    )
    argument_parser.add_argument("test_file", help="YAML file describing the test to run")
    argument_parser.add_argument("-D", "--directory", default=".", help="Directory containing the executables")
    argument_parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v for INFO, -vv for DEBUG)",
    )
    argument_parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Execution timeout in seconds (default: 600)",
    )

    mode_group = argument_parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "-t",
        "--tolerance",
        action="store_const",
        const="tolerance",
        dest="update_mode",
        help="Update tolerances to cover observed differences",
    )
    mode_group.add_argument(
        "-r",
        "--reference",
        action="store_const",
        const="reference",
        dest="update_mode",
        help="Update reference values to match calculated values",
    )

    argument_parser.add_argument(
        "-o",
        "--output",
        default=None,
        metavar="FILE",
        help="Write updated config to FILE instead of overwriting the original",
    )
    parsed_args = argument_parser.parse_args(command_line_args)

    setup_logging(parsed_args.verbose)
    test_runner = PseudoTestRunner()
    return test_runner.run(
        parsed_args.test_file,
        parsed_args.directory,
        preserve_workdir=False,
        timeout=parsed_args.timeout,
        update_mode=parsed_args.update_mode,
        update_output=parsed_args.output,
    )


if __name__ == "__main__":  # pragma: no cover
    try:
        sys.exit(main())
    except CliError as e:
        logging.error(e)
        sys.exit(e.exit_code)
    except Exception:
        logging.error("internal error (use --vv for traceback)")
        if "--vv" in sys.argv:
            traceback.print_exc()
        sys.exit(ExitCode.INTERNAL)
