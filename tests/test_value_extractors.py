"""Unit tests for pseudotest.value_extractors."""

from pseudotest.value_extractors import (
    extract_column_from_line,
    extract_field_from_line,
    find_pattern_line,
    get_target_line,
)


class TestGetTargetLine:
    def test_positive_out_of_bounds(self):
        assert get_target_line(["a", "b"], 5) is None

    def test_negative_index(self):
        assert get_target_line(["a", "b", "c"], -1) == "c"
        assert get_target_line(["a", "b", "c"], -3) == "a"

    def test_negative_out_of_bounds(self):
        assert get_target_line(["a", "b"], -5) is None


class TestFindPatternLine:
    def test_offset_out_of_bounds(self):
        lines = ["first", "second", "third"]
        assert find_pattern_line(lines, "third", 1) is None

    def test_not_found(self):
        assert find_pattern_line(["a", "b"], "z") is None


class TestExtractFieldFromLine:
    def test_none_line(self):
        assert extract_field_from_line(None, 1) is None

    def test_out_of_bounds(self):
        assert extract_field_from_line("one two", 5) is None


class TestExtractColumnFromLine:
    def test_none_line(self):
        assert extract_column_from_line(None, 1) is None

    def test_out_of_bounds(self):
        assert extract_column_from_line("short", 100) is None
