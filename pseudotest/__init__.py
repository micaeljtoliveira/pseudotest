"""
Pseudotest - YAML Regression Testing Framework

A Python package for running regression tests defined in YAML format.
Inspired by octopus/cephalopod naming for scientific software testing.
"""

from .cli import main
from .formatting import Colors
from .report import ReportWriter
from .runner import PseudoTestRunner

__version__ = "1.0.0"
__author__ = "Kraken MD Team"

__all__ = ["PseudoTestRunner", "ReportWriter", "Colors", "main"]
