"""Results of the evaluation of matches.

A :class:`MatchResult` holds everything known about one evaluated match. It is displayed by
:func:`pseudotest.formatting.display_match_result`, written to the report by :class:`pseudotest.report.ReportWriter`,
and used by :mod:`pseudotest.config_updater` to update the test file.
"""

from collections import ChainMap
from dataclasses import dataclass
from typing import Any


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
