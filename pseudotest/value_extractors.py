"""Value extraction helpers for line, field, and column parsing.

Contains pure functions that extract text fragments from file content. No I/O, no display, and no comparison logic
should be included here.
"""

from typing import List, Optional


def get_target_line(lines: List[str], line_num: int) -> Optional[str]:
    """Extract target line handling positive and negative indexing.

    Supports both positive line numbers (0-indexed from start) and negative
    line numbers (counted from end).  This provides flexible line access
    similar to standard Python list indexing.

    Args:
        lines: File content as list of lines
        line_num: Line number where positive values are 0-indexed from start,
                 negative values count from end (-1 = last line)

    Returns:
        Target line content or None if line number is out of bounds

    Examples:
        >>> lines = ["first", "second", "third"]
        >>> get_target_line(lines, 0)   # "first"
        >>> get_target_line(lines, -1)  # "third"
    """
    if line_num >= 0:
        if line_num >= len(lines):
            return None
        return lines[line_num]
    else:
        if abs(line_num) > len(lines):
            return None
        return lines[line_num]


def find_pattern_line(lines: List[str], pattern: str, offset: int = 0) -> Optional[str]:
    """Find the line content at specified offset from first line containing *pattern*.

    Performs simple substring matching to locate the first occurrence
    of the pattern within any line of the input text, then returns the
    content of the line at the specified offset from that match.

    Args:
        lines: File content as list of lines
        pattern: Text pattern to search for (case-sensitive substring match)
        offset: Line offset from the pattern match (0=same line, 1=next line, etc.)

    Returns:
        Content of the target line (pattern line + offset),
        or None if pattern not found or offset line doesn't exist

    Examples:
        >>> lines = ["hello world", "test pattern", "final line"]
        >>> find_pattern_line(lines, "pattern", 0)  # "test pattern"
        >>> find_pattern_line(lines, "pattern", 1)  # "final line"
        >>> find_pattern_line(lines, "missing", 0)  # None
    """
    for i, line in enumerate(lines):
        if pattern in line:
            target_index = i + offset
            if 0 <= target_index < len(lines):
                return lines[target_index]
            else:
                return None
    return None


def extract_field_from_line(line: Optional[str], field_num: int) -> Optional[str]:
    """Extract a specific whitespace-separated field from a line.

    Splits the line on whitespace and returns the field at the specified
    position.  Similar to: ``awk '{print $N}'`` where *N* is the field number.

    Args:
        line: Line content to extract field from, or None if line doesn't exist
        field_num: 1-indexed field position after whitespace splitting

    Returns:
        Content of the specified field as string, or None if line is None
        or field number is out of bounds

    Examples:
        >>> extract_field_from_line("first second third", 2)  # "second"
        >>> extract_field_from_line("first second third", 5)  # None
        >>> extract_field_from_line(None, 2)                  # None
    """
    if line is None:
        return None

    fields = line.split()
    if field_num < 1 or field_num > len(fields):
        return None
    return fields[field_num - 1]


def extract_column_from_line(line: Optional[str], column_pos: int) -> Optional[str]:
    """Extract first token starting from a specific column position in a line.

    Similar to the shell command: ``cut -c<column>- | awk '{print $1}'``
    Extracts a substring from the specified column position to the end of the
    line, then returns the first whitespace-separated token from that substring.

    Args:
        line: Line content to extract token from, or None if line doesn't exist
        column_pos: 1-indexed character position to start extraction

    Returns:
        First whitespace-separated token from the specified position,
        empty string if no tokens found after column position,
        or None if line is None or column position is out of bounds

    Examples:
        >>> extract_column_from_line("  hello world test", 3)   # "hello"
        >>> extract_column_from_line("  hello world test", 9)   # "world"
        >>> extract_column_from_line("short", 10)               # None
        >>> extract_column_from_line("   ", 1)                  # ""
        >>> extract_column_from_line(None, 3)                   # None
    """
    if line is None:
        return None

    if column_pos > len(line):
        return None

    # Extract substring from column position onwards
    substring = line[column_pos - 1 :].lstrip()

    # Get first whitespace-separated token
    tokens = substring.split()
    return tokens[0] if tokens else ""
