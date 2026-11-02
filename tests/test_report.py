"""Unit tests for pseudotest.report."""

from collections import ChainMap

from pseudotest.config import yaml
from pseudotest.config_updater import cast_like
from pseudotest.report import ReportWriter
from pseudotest.results import MatchResult


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


class TestBuildEntries:
    def test_match_entry(self):
        """The calculated value replaces the reference, which moves to 'reference'; internal keys are left out."""
        params = ChainMap({"value": -42.5, "match": "energy", "grep": "Energy:"}, {"file": "results.txt", "tol": 0.1})
        result = MatchResult("energy", params, True, "-42.6", -42.5, "value", 0.1, difference=0.1)
        entry = ReportWriter.build_match_entry(result)
        assert entry == {
            "file": "results.txt",
            "tol": 0.1,
            "value": -42.6,
            "reference": -42.5,
            "grep": "Energy:",
            "status": "pass",
        }
        # The order of the parameters is kept, with the inherited ones first
        assert list(entry) == ["file", "tol", "value", "reference", "grep", "status"]

    def test_match_entry_of_failed_extraction(self):
        params = ChainMap({"file": "out.txt", "size": 10})
        result = MatchResult("size", params, False, None, 10, "size", reason="'out.txt' not found")
        assert ReportWriter.build_match_entry(result) == {
            "file": "out.txt",
            "size": None,
            "reference": 10,
            "status": "fail",
            "reason": "'out.txt' not found",
        }

    def test_input_entry(self):
        scope = ChainMap({"Processors": 4}, {"InputMethod": "stdin"})
        assert ReportWriter.build_input_entry(scope, False, True, 1.23456) == {
            "InputMethod": "stdin",
            "Processors": 4,
            "ExpectedFailure": False,
            "Execution": "pass",
            "Elapsed time": 1.235,
        }
