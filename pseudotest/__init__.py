"""
Pseudotest - YAML Regression Testing Framework

A Python package for running regression tests defined in YAML format.
Inspired by octopus/cephalopod naming for scientific software testing.
"""

from .runner import Colors, PseudoTestRunner

__version__ = "1.0.0"
__author__ = "Kraken MD Team"

__all__ = ["PseudoTestRunner", "Colors", "main"]


def main():
    """Main entry point for the pseudotest command"""
    runner = PseudoTestRunner()
    runner.run()


if __name__ == "__main__":
    main()
