"""Terminal formatting, color output, and display helpers for pseudotest."""

import logging
import sys
from pathlib import Path

from pseudotest.comparator import parse_number
from pseudotest.results import MatchResult

INDENT_STEP = 2
STATUS_COLUMN = 58


def indent(level: int) -> str:
    """Return an indentation string for the given nesting *level*.

    Level 0 produces no indentation; each subsequent level adds
    :data:`INDENT_STEP` spaces.
    """
    return " " * (INDENT_STEP * level)


class Colors:
    """ANSI color codes for terminal output.

    Automatically detects if stdout is a TTY and disables colors if not.
    This ensures clean output when redirecting to files or pipes.
    """

    def __init__(self):
        """Initialize color codes based on TTY detection."""
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


def display_match_status(match_name: str, success: bool, indent_level: int = 2) -> None:
    """Display the status of a match with appropriate formatting.

    Args:
        match_name: Name of the match to display
        success: Whether the match succeeded
        indent_level: Nesting level (each level = :data:`INDENT_STEP` spaces)
    """
    colors = Colors()
    prefix = indent(indent_level)
    name_width = STATUS_COLUMN - len(prefix)

    status_text = f"[{colors.GREEN} OK {colors.RESET}]" if success else f"[{colors.RED}FAIL{colors.RESET}]"

    print(f"{prefix}{match_name:<{name_width}} {status_text}")


def display_failure_details(lines: list[str], indent_level: int = 2) -> None:
    """Display the details of a failed match between two separators.

    Args:
        lines: Detail lines to display
        indent_level: Nesting level of the match whose details are displayed
    """
    prefix = indent(indent_level + 1)
    separator = f"{prefix}" + "-" * 45
    print(separator)
    for line in lines:
        print(f"{prefix}{line}")
    print(separator)


def _failure_details(result: MatchResult) -> list[str]:
    """Return the detail lines explaining why *result* failed."""
    if result.calculated is None:
        # No value could be extracted
        return [result.reason or "No value extracted"]

    if result.precision is not None:
        return [
            "Unreliable comparison: the tolerance is smaller than the precision of the calculated value",
            f"Calculated value    : {result.calculated}",
            f"Effective precision : {result.precision:g}",
            f"Tolerance           : {result.tolerance}",
            f"Use a tolerance of at least {result.precision:g}, or print the value with more digits",
        ]

    if result.difference is None:
        return [f"Calculated value : '{result.calculated}'", f"Expected value   : '{result.reference}'"]

    details = [
        f"Calculated value : {result.calculated}",
        f"Reference value  : {result.reference}",
        f"Difference       : {result.difference}",
    ]
    reference = abs(parse_number(result.reference) or 0.0)
    if reference > 1e-10:
        details.append(f"Deviation [%]    : {result.difference / reference * 100.0:.6f}")
    if result.tolerance:
        details.append(f"Tolerance        : {result.tolerance}")
        if reference > 1e-10:
            details.append(f"Tolerance [%]    : {result.tolerance / reference * 100.0:.6f}")
    return details


def display_match_result(result: MatchResult, indent_level: int = 2) -> None:
    """Display the status of a match and, when it failed, why.

    Args:
        result: Result of the match
        indent_level: Nesting level of the match
    """
    display_match_status(result.name, result.passed, indent_level)
    if not result.passed:
        display_failure_details(_failure_details(result), indent_level)


class OutputFormatter:
    """Formats and prints execution output (stdout/stderr) from test runs.

    Encapsulates all logic for displaying subprocess output after a failed test execution.

    Accepts a Colors instance via constructor rather than creating its own.
    """

    def __init__(self, colors: Colors | None = None):
        self.colors = colors or Colors()

    def print_execution_error(self, input_file: str, message: str) -> None:
        """Print why the execution of *input_file* did not complete.

        Args:
            input_file: Name of the input file for context
            message: Reason of the failure, e.g. a timeout
        """
        print(f"\n{self.colors.RED}=== {input_file}: {message} ==={self.colors.RESET}")

    def print_execution_output(self, temp_dir: Path, input_file: str) -> None:
        """Print stdout and stderr output from a failed execution.

        Args:
            temp_dir: Directory containing stdout and stderr files
            input_file: Name of the input file for context
        """
        stdout_file = temp_dir / "stdout"
        stderr_file = temp_dir / "stderr"

        # Check current logging level to determine how much to show
        show_full_output = logging.getLogger().isEnabledFor(logging.DEBUG)

        for output_file, output_name in [(stdout_file, "STDOUT"), (stderr_file, "STDERR")]:
            if output_file.exists():
                try:
                    content = output_file.read_text(errors="replace")
                    if content.strip():  # Show content if there's actual content
                        lines = content.splitlines()

                        print(f"\n{self.colors.RED}=== {output_name} from {input_file} ==={self.colors.RESET}")

                        if show_full_output or len(lines) <= 10:
                            # Show full content in debug mode or if <= 10 lines
                            print(content)
                        else:
                            # Show last 10 lines in normal mode
                            print("... (showing last 10 lines, use -vv to see full output)")
                            print("\n".join(lines[-10:]))

                        print(f"{self.colors.RED}=== End {output_name} ==={self.colors.RESET}")
                    else:
                        # Inform user when file is empty
                        print(f"\n{self.colors.RED}=== {output_name} from {input_file} is empty ==={self.colors.RESET}")
                except Exception as e:
                    logging.debug(f"Failed to read {output_name} file: {e}")
            else:
                # Inform user when file doesn't exist
                print(f"\n{self.colors.RED}=== {output_name} from {input_file} does not exist ==={self.colors.RESET}")
