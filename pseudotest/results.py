"""Results of the evaluation of matches, and of the run of a test file.

A :class:`MatchResult` holds everything known about one evaluated match. It is displayed by
:func:`pseudotest.formatting.display_match_result`, written to the report by :class:`pseudotest.report.ReportWriter`,
and used by :mod:`pseudotest.config_updater` to update the test file.

A :class:`RunSummary` is returned by :meth:`pseudotest.runner.PseudoTestRunner.run` for a whole test file.
"""

from collections import ChainMap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pseudotest.exceptions import ExitCode


@dataclass
class MatchResult:
    """Outcome of the evaluation of one match.

    Attributes:
        name: Name of the match, as displayed
        params: Parameters of the match, including the inherited ones
        passed: Whether the match passed
        calculated: Value extracted from the outputs, or None when none could be extracted
        reference: Reference value the calculated value is compared to
        reference_key: Parameter holding the reference value, when known
        tolerance: Tolerance of the comparison, if any
        difference: Absolute difference of a numeric comparison
        precision: Precision of the calculated value, set when the tolerance is smaller than it
        reason: Why the match failed
    """

    name: str
    params: ChainMap[str, Any]
    passed: bool
    calculated: str | None = None
    reference: Any = None
    reference_key: str | None = None
    tolerance: float | None = None
    difference: float | None = None
    precision: float | None = None
    reason: str | None = None

    @property
    def status(self) -> str:
        """``"pass"`` or ``"fail"``."""
        return "pass" if self.passed else "fail"


@dataclass
class RunSummary:
    """Outcome of the run of a test file.

    Attributes:
        name: Name of the test
        enabled: Whether the test is enabled; a disabled test is not run
        failed_executions: Number of inputs whose execution failed
        match_results: Results of the evaluated matches, in the order of their evaluation
        updated_file: Test file written by ``pseudotest-update``, if any
    """

    name: str
    enabled: bool = True
    failed_executions: int = 0
    match_results: list[MatchResult] = field(default_factory=list)
    updated_file: Path | None = None

    @property
    def total_matches(self) -> int:
        """Number of evaluated matches."""
        return len(self.match_results)

    @property
    def failed_matches(self) -> int:
        """Number of failed matches."""
        return sum(not result.passed for result in self.match_results)

    @property
    def passed(self) -> bool:
        """Whether all the executions and matches passed."""
        return self.failed_executions == 0 and self.failed_matches == 0

    @property
    def exit_code(self) -> int:
        """Exit code of the command running the test: ``OK`` or ``TEST_FAILURE``."""
        return ExitCode.OK if self.passed else ExitCode.TEST_FAILURE
