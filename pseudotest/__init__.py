"""
Pseudotest - YAML Regression Testing Framework

A Python package for running regression tests defined in YAML format.
Inspired by octopus/cephalopod naming for scientific software testing.
"""

from importlib.metadata import PackageNotFoundError, version

from .cli_run import main
from .cli_update import main as update_main
from .formatting import Colors
from .report import ReportWriter
from .runner import PseudoTestRunner

# The version is set by setuptools_scm from the git tags
try:
    __version__ = version("pseudotest")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "unknown"
__author__ = "Micael Oliveira"

__all__ = ["PseudoTestRunner", "ReportWriter", "Colors", "main", "update_main"]
