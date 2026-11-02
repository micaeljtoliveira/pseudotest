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


class ExtractionError(Exception):
    """Raised by a match handler when no value can be extracted, e.g. because a file or a pattern is missing.

    The match then fails, with the message of the exception as reason. This is not a usage error: the run goes on.

    Args:
        reason: Why no value could be extracted
        reference_key: Match parameter holding the reference value, when known
    """

    def __init__(self, reason: str, reference_key: str | None = None):
        super().__init__(reason)
        self.reference_key = reference_key
