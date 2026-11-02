"""Unit tests for pseudotest.runner: the walk of the match tree."""

from collections import ChainMap

import pytest

from pseudotest.exceptions import UsageError
from pseudotest.runner import PseudoTestRunner


@pytest.fixture
def work_dir(tmp_path):
    (tmp_path / "a.txt").write_text("Energy: 1.0\n")
    (tmp_path / "b.txt").write_text("Energy: 2.0\n")
    return tmp_path


class TestRunMatches:
    def test_group_parameters_inherited_and_overridden(self, work_dir):
        matches = {
            "group": {
                "file": "a.txt",
                "grep": "Energy:",
                "field": 2,
                "inherited": {"value": 1.0},
                "overridden": {"file": "b.txt", "value": 2.0},
                "subgroup": {"file": "b.txt", "nested": {"value": 2.0}},
            }
        }
        runner = PseudoTestRunner()
        results = runner.run_matches(matches, work_dir)

        assert (runner.summary.total_matches, runner.summary.failed_matches) == (3, 0)
        assert results["group"]["inherited"]["file"] == "a.txt"
        assert results["group"]["overridden"]["file"] == "b.txt"
        assert results["group"]["subgroup"]["nested"]["value"] == 2.0

    def test_failed_matches_counted(self, work_dir):
        runner = PseudoTestRunner()
        runner.run_matches(
            ChainMap({"energy": {"file": "a.txt", "grep": "Energy:", "field": 2, "value": 3.0}}), work_dir
        )
        assert (runner.summary.total_matches, runner.summary.failed_matches) == (1, 1)

    def test_reserved_key_with_scalar_is_inherited_parameter(self, work_dir):
        """A parameter next to the matches is inherited, not evaluated as a match."""
        runner = PseudoTestRunner()
        results = runner.run_matches(
            {"file": "a.txt", "energy": {"grep": "Energy:", "field": 2, "value": 1.0}}, work_dir
        )
        assert list(results) == ["energy"]
        assert runner.summary.total_matches == 1

    def test_error_locates_the_match(self, work_dir):
        with pytest.raises(UsageError, match="'Inputs > a.inp > Matches > group > energy'"):
            PseudoTestRunner().run_matches(
                {"group": {"energy": {"fiel": "a.txt"}}}, work_dir, scope_path="Inputs > a.inp > Matches"
            )
