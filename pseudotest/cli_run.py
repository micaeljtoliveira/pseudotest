"""Command-line interface for pseudotest.

CLI argument parsing, logging configuration, and the ``main()`` entry point live here.  The actual test execution logic
is delegated to the runner module, and error handling is centralized around custom exceptions defined in the exceptions
module. This separation of concerns keeps the CLI code focused on user interaction and orchestration, while the core
logic remains testable and maintainable. The CLI supports extensibility through custom match handlers that can be
registered in the matchers module.
"""

import argparse
import logging
import sys
import traceback
from collections.abc import Callable

from pseudotest.exceptions import CliError, ExitCode
from pseudotest.runner import PseudoTestRunner


def setup_logging(verbosity_level: int) -> None:
    """Configure logging based on verbosity level.

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


def _report_error(message: str, verbosity_level: int) -> None:
    """Log *message* and, at the highest verbosity level, the traceback of the exception being handled."""
    logging.error(message)
    if verbosity_level >= 2:
        traceback.print_exc()


def handle_errors(run: Callable[[], int], verbosity_level: int) -> int:
    """Call *run* and turn the exceptions it raises into exit codes.

    User errors (:class:`CliError`) are reported in one line with their own exit code; any other exception is an
    internal error. The traceback is shown with ``-vv``.

    Args:
        run: Callable running the tests and returning the exit code
        verbosity_level: 0=WARNING, 1=INFO, 2+=DEBUG

    Returns:
        Exit code for the process
    """
    try:
        return run()
    except CliError as e:
        _report_error(str(e), verbosity_level)
        return e.exit_code
    except Exception as e:
        hint = "" if verbosity_level >= 2 else " (use -vv for the traceback)"
        _report_error(f"internal error: {e}{hint}", verbosity_level)
        return ExitCode.INTERNAL


def main(command_line_args: list[str] | None = None) -> int:
    """Main entry point for command line execution.

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
    argument_parser.add_argument(
        "-r",
        "--report",
        default=None,
        metavar="FILE",
        help="Write a YAML execution report to FILE",
    )
    parsed_args = argument_parser.parse_args(command_line_args)

    setup_logging(parsed_args.verbose)
    test_runner = PseudoTestRunner()
    return handle_errors(
        lambda: test_runner.run(
            parsed_args.test_file,
            parsed_args.directory,
            parsed_args.preserve,
            parsed_args.timeout,
            report_file=parsed_args.report,
        ),
        parsed_args.verbose,
    )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
