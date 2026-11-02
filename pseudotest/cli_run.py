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

from pseudotest.config_updater import UpdateMode
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


def add_common_arguments(
    parser: argparse.ArgumentParser, *, timeout_flags: tuple[str, ...], report_flags: tuple[str, ...]
) -> None:
    """Add the arguments shared by ``pseudotest`` and ``pseudotest-update`` to *parser*.

    The flags of the timeout and of the report differ between the commands, as ``-t`` and ``-r`` select the update mode
    of ``pseudotest-update``.

    Args:
        parser: Parser of the command
        timeout_flags: Flags of the timeout option
        report_flags: Flags of the report option
    """
    parser.add_argument("test_file", help="YAML file describing the test to run")
    parser.add_argument("-D", "--directory", default=".", help="Directory containing the executables")
    parser.add_argument("-p", "--preserve", action="store_true", help="Preserve working directory after test")
    parser.add_argument(
        *timeout_flags,
        dest="timeout",
        type=int,
        default=600,
        help="Execution timeout of each input in seconds (default: 600, i.e., 10 minutes)",
    )
    parser.add_argument(
        *report_flags, dest="report", default=None, metavar="FILE", help="Append a YAML execution report to FILE"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v for INFO, -vv for DEBUG)",
    )


def run_tests(args: argparse.Namespace, update_mode: UpdateMode | None = None, update_output: str | None = None) -> int:
    """Run the test of the parsed command-line *args*, and return the exit code.

    Args:
        args: Command-line arguments, as added by :func:`add_common_arguments`
        update_mode: Update mode of ``pseudotest-update``
        update_output: Path where ``pseudotest-update`` writes the updated test file

    Returns:
        Exit code for the process
    """
    setup_logging(args.verbose)
    test_runner = PseudoTestRunner()
    return handle_errors(
        lambda: test_runner.run(
            args.test_file,
            args.directory,
            preserve_workdir=args.preserve,
            timeout=args.timeout,
            report_file=args.report,
            update_mode=update_mode,
            update_output=update_output,
        ).exit_code,
        args.verbose,
    )


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
    )
    add_common_arguments(argument_parser, timeout_flags=("-t", "--timeout"), report_flags=("-r", "--report"))
    return run_tests(argument_parser.parse_args(command_line_args))
