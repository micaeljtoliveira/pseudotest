"""
Pseudotest - YAML Regression Testing Framework

A Python package for running regression tests defined in YAML format.
Inspired by octopus/cephalopod naming for scientific software testing.

The names exported here, with the command-line tools and the formats of the test files and reports, are the public
API, which follows semantic versioning; everything else is internal.
"""

from ._version import __version__ as __version__
from .cli_run import main
from .cli_update import main as update_main
from .config_updater import UpdateMode
from .exceptions import ExtractionError
from .formatting import Colors
from .matchers import register_match_handler
from .report import ReportWriter
from .results import MatchResult, RunSummary
from .runner import PseudoTestRunner

__author__ = "Micael Oliveira"

__all__ = [
    "PseudoTestRunner",
    "RunSummary",
    "MatchResult",
    "UpdateMode",
    "register_match_handler",
    "ExtractionError",
    "ReportWriter",
    "Colors",
    "main",
    "update_main",
]
