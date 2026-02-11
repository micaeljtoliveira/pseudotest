"""Utility classes and functions for pseudotest

This module contains common utilities including exit codes, custom exception classes,
color formatting for terminal output, and display functions.
"""

import re
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


def get_precision_from_string_format(value_str: str) -> float:
    """Get the precision/resolution from a numeric string representation.

    This function analyzes the string format of a number to determine the smallest representable number
    using that format."""

    try:
        float(value_str)
    except (ValueError, TypeError):
        return 0.0

    clean_str = value_str.strip()

    # Handle scientific notation, including Fortran-style 'D' exponent
    clean_str = re.sub(r"[dD]", "e", clean_str)  # Replace 'D' with 'e' for scientific notation
    sci_match = re.match(r"^[+-]?(\d*\.?\d*)[eE]([+-]?\d+)$", clean_str)
    if sci_match:
        mantissa, exp_str = sci_match.groups()
        exponent = int(exp_str)

        if "." in mantissa:
            # Count digits after decimal in mantissa
            decimal_digits = len(mantissa.split(".")[1])
            mantissa_precision = 10 ** (-decimal_digits)
        else:
            # Integer mantissa
            mantissa_precision = 1.0

        return mantissa_precision * (10**exponent)

    # Handle regular numbers
    if "." in clean_str:
        # Count decimal places
        integer_part, decimal_part = clean_str.split(".", 1)
        return 10 ** (-len(decimal_part))
    else:
        # Integer value, precision is 1
        return 1.0
