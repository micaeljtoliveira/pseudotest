"""Exception classes and exit codes for pseudotest."""


class ExitCode:
    """Standard exit codes for the pseudotest application."""

    OK = 0  # Success
    TEST_FAILURE = 1  # One or more tests failed
    USAGE = 2  # Command line usage error
    RUNTIME = 3  # Runtime error during execution
    INTERNAL = 99  # Internal/unexpected error


class CliError(Exception):
    """Base class for command line interface errors."""

    exit_code = ExitCode.RUNTIME


class UsageError(CliError):
    """Error in command line usage or invalid parameters."""

    exit_code = ExitCode.USAGE
