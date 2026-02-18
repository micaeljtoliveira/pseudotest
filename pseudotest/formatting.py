"""Terminal formatting, color output, and display helpers for pseudotest."""

import logging
import sys
from pathlib import Path


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


def display_match_status(match_name: str, success: bool, extra_indent: int = 0) -> None:
    """Display the status of a match with appropriate formatting.

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


class OutputFormatter:
    """Formats and prints execution output (stdout/stderr) from test runs.

    Encapsulates all logic for displaying subprocess output after a failed test execution.

    Accepts a Colors instance via constructor rather than creating its own.
    """

    def __init__(self, colors: Colors | None = None):
        self.colors = colors or Colors()

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
