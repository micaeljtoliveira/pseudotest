"""YAML report generation for pseudotest.

The :class:`ReportWriter` class is responsible for building structured
report entries from match results and writing the final YAML report to
disk.  Extracting this into its own module follows the Single
Responsibility Principle — the runner orchestrates tests while the
report writer owns serialisation.
"""

import logging
from collections import ChainMap
from pathlib import Path
from typing import Any

from pseudotest.matchers import INTERNAL_KEYS, REFERENCE_KEYS, RESERVED_KEYS
from pseudotest.test_config import yaml


def _cast_to_type(value: str | None, target_type: type) -> Any:
    """Cast a string value to *target_type*, falling back to the original string."""
    if value is None:
        return None
    # Map ruamel.yaml scalar types to Python builtins
    _builtin_map: dict[str, type] = {
        "ScalarFloat": float,
        "ScalarInt": int,
        "ScalarBoolean": bool,
    }
    cast_type = _builtin_map.get(target_type.__name__, target_type)
    try:
        return cast_type(value)
    except (ValueError, TypeError):
        return value


class ReportWriter:
    """Builds and writes YAML execution reports.

    Collects per-input results during a test run and serialises the
    complete report to a YAML file when :meth:`write` is called.
    """

    @staticmethod
    def build_match_entry(params: ChainMap[str, Any], calculated_value: str | None) -> dict[str, Any]:
        """Build a report entry for a single leaf match.

        Includes the original match parameters with the reference value
        replaced by the calculated value, cast to the same type as the
        reference.
        """
        entry: dict[str, Any] = {}
        for key in RESERVED_KEYS:
            if key in params and key not in INTERNAL_KEYS:
                if key in REFERENCE_KEYS:
                    entry[key] = _cast_to_type(calculated_value, type(params[key]))
                    entry["reference"] = params[key]
                else:
                    entry[key] = params[key]
        return entry

    @staticmethod
    def build_input_entry(
        input_scope: ChainMap[str, Any],
        expected_failure: bool,
        execution_success: bool,
        execution_time: float,
    ) -> dict[str, Any]:
        """Build the per-input report dict (before matches are appended)."""
        return {
            "InputMethod": input_scope.get("InputMethod", "argument"),
            "ExpectedFailure": expected_failure,
            "Execution": "pass" if execution_success else "fail",
            "Elapsed time": round(execution_time, 3),
        }

    @staticmethod
    def write(
        report_file: str,
        test_file_path: str,
        test_config_data: dict[str, Any],
        report_inputs: dict[str, Any],
    ) -> None:
        """Serialise the full report to *report_file*.

        Args:
            report_file: Destination path for the YAML report.
            test_file_path: Original test file path as passed on the CLI.
            test_config_data: Parsed top-level test configuration dict.
            report_inputs: Per-input result dicts keyed by input filename.
        """
        test_file_key = test_file_path.lstrip("./") if test_file_path.startswith("./") else test_file_path
        report = {
            test_file_key: {
                "Name": test_config_data["Name"],
                "Enabled": test_config_data.get("Enabled", True),
                "Executable": test_config_data.get("Executable", ""),
                "Inputs": report_inputs,
            }
        }
        with Path(report_file).open("w") as f:
            yaml.dump(report, f)
        logging.info(f"Report written to {report_file}")
