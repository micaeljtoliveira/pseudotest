"""Unit tests for pseudotest.report."""

from pseudotest.config_updater import cast_like
from pseudotest.report import ReportWriter
from pseudotest.test_config import yaml


class TestCastLike:
    def test_value_error_fallback(self):
        """Unparseable string for given type → returns original value."""
        result = cast_like("not_an_int", 1)
        assert result == "not_an_int"

    def test_none_returns_none(self):
        result = cast_like(None, 1)
        assert result is None

    def test_successful_cast(self):
        result = cast_like("42", 1)
        assert result == 42

    def test_bool_cast(self):
        assert cast_like("false", True) is False


class TestWrite:
    def test_only_leading_dot_slash_removed_from_test_key(self, tmp_path):
        report_path = tmp_path / "report.yaml"
        ReportWriter.write(str(report_path), "./.hidden/test.yaml", {"Name": "Hidden"}, {})
        report = yaml.load(report_path)
        assert list(report) == [".hidden/test.yaml"]

    def test_each_write_appends_a_document(self, tmp_path):
        report_path = tmp_path / "report.yaml"
        ReportWriter.write(str(report_path), "a.yaml", {"Name": "A"}, {})
        ReportWriter.write(str(report_path), "b.yaml", {"Name": "B"}, {})
        assert [list(doc) for doc in yaml.load_all(report_path)] == [["a.yaml"], ["b.yaml"]]
