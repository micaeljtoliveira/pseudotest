"""Exception classes and exit codes for pseudotest."""


class ExitCode:
    """Standard exit codes for the pseudotest application."""

    OK = 0  # Success
    TEST_FAILURE = 1  # One or more tests failed
    USAGE = 2  # Command line usage error
    CONFIG = 3  # Configuration file error
    RUNTIME = 4  # Runtime error during execution
    TIMEOUT = 5  # Execution timeout
    INTERNAL = 99  # Internal/unexpected error


class CliError(Exception):
    """Base class for command line interface errors."""

    exit_code = ExitCode.RUNTIME


class UsageError(CliError):
    """Error in command line usage or invalid parameters."""

    exit_code = ExitCode.USAGE


class ConfigError(CliError):
    """Error in configuration file format or content."""

    exit_code = ExitCode.CONFIG


class RuntimeError(CliError):
    """Runtime error during test execution."""

    exit_code = ExitCode.RUNTIME


class TimeoutError(CliError):
    """Timeout during test execution."""

    exit_code = ExitCode.TIMEOUT
