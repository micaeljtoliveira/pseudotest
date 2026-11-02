"""Unit tests for pseudotest.results."""

from collections import ChainMap

import pytest

from pseudotest.exceptions import ExitCode
from pseudotest.results import MatchResult, RunSummary


def _result(passed: bool) -> MatchResult:
    return MatchResult("match", ChainMap(), passed)


class TestMatchResult:
    @pytest.mark.parametrize(("passed", "status"), [(True, "pass"), (False, "fail")])
    def test_status(self, passed, status):
        assert _result(passed).status == status


class TestRunSummary:
    def test_empty(self):
        summary = RunSummary("Test")
        assert (summary.total_matches, summary.failed_matches, summary.passed) == (0, 0, True)
        assert summary.exit_code == ExitCode.OK

    def test_counts(self):
        summary = RunSummary("Test", match_results=[_result(True), _result(False), _result(False)])
        assert (summary.total_matches, summary.failed_matches, summary.passed) == (3, 2, False)
        assert summary.exit_code == ExitCode.TEST_FAILURE

    def test_failed_execution(self):
        summary = RunSummary("Test", failed_executions=1, match_results=[_result(True)])
        assert not summary.passed
        assert summary.exit_code == ExitCode.TEST_FAILURE
