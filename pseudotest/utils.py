"""Utility classes and functions for pseudotest

This module contains common utilities including exit codes, custom exception classes,
color formatting for terminal output, and display functions.
"""

import sys


class ExitCode:
    """Standard exit codes for the pseudotest application"""

    OK = 0  # Success
    TEST_FAILURE = 1  # One or more tests failed
    USAGE = 2  # Command line usage error
    CONFIG = 3  # Configuration file error
    RUNTIME = 4  # Runtime error during execution
    TIMEOUT = 5  # Execution timeout
    INTERNAL = 99  # Internal/unexpected error


class CliError(Exception):
    """Base class for command line interface errors"""

    exit_code = ExitCode.RUNTIME


class UsageError(CliError):
    """Error in command line usage or invalid parameters"""

    exit_code = ExitCode.USAGE


class ConfigError(CliError):
    """Error in configuration file format or content"""

    exit_code = ExitCode.CONFIG


class RuntimeError(CliError):
    """Runtime error during test execution"""

    exit_code = ExitCode.RUNTIME


class TimeoutError(CliError):
    """Timeout during test execution"""

    exit_code = ExitCode.TIMEOUT


class Colors:
    """ANSI color codes for terminal output

    Automatically detects if stdout is a TTY and disables colors if not.
    This ensures clean output when redirecting to files or pipes.
    """

    def __init__(self):
        """Initialize color codes based on TTY detection"""
        if sys.stdout.isatty():
            self.BLUE = "\033[34m"
            self.RED = "\033[31m"
            self.GREEN = "\033[32m"
            self.RESET = "\033[0m"
        else:
            # No colors for non-TTY output (files, pipes, etc.)
            self.BLUE = ""
            self.RED = ""
            self.GREEN = ""
            self.RESET = ""


def display_match_status(match_name: str, success: bool, extra_indent: int = 0) -> None:
    """Display the status of a match with appropriate formatting

    Args:
        match_name: Name of the match to display
        success: Whether the match succeeded
        extra_indent: Additional indentation for nested output
    """
    colors = Colors()
    base_indent = " " * (2 + extra_indent)

    # Calculate available width for match name, accounting for status indicator
    available_width = 50 - extra_indent

    status_text = f"[{colors.GREEN} OK {colors.RESET}]" if success else f"[{colors.RED}FAIL{colors.RESET}]"

    print(f"{base_indent}  {match_name:<{available_width}} {status_text}")
