"""Unit tests for pseudotest.cli_update."""

from unittest.mock import patch

import pytest

import pseudotest
import pseudotest.cli_run
from pseudotest.config_updater import UpdateMode
from pseudotest.exceptions import ExitCode


@pytest.mark.parametrize(
    ("flag", "mode"),
    [
        ("-t", UpdateMode.TOLERANCE),
        ("--tolerance", UpdateMode.TOLERANCE),
        ("-r", UpdateMode.REFERENCE),
        ("--reference", UpdateMode.REFERENCE),
        ("-R", UpdateMode.REFERENCE_ALL),
        ("--reference-all", UpdateMode.REFERENCE_ALL),
    ],
)
def test_update_mode(flag, mode):
    """pseudotest.update_main() is the pseudotest-update command."""
    with patch.object(pseudotest.cli_run, "PseudoTestRunner") as runner_class:
        runner_class.return_value.run.return_value = ExitCode.OK
        assert pseudotest.update_main(["test.yaml", flag]) == ExitCode.OK
    runner_class.return_value.run.assert_called_once_with(
        "test.yaml",
        ".",
        preserve_workdir=False,
        timeout=600,
        report_file=None,
        update_mode=mode,
        update_output=None,
    )


def test_options_passed_to_runner():
    """The options of pseudotest are available, with long names only for the timeout and the report."""
    with patch.object(pseudotest.cli_run, "PseudoTestRunner") as runner_class:
        runner_class.return_value.run.return_value = ExitCode.TEST_FAILURE
        args = [
            "test.yaml",
            "-r",
            "-D",
            "bin",
            "--timeout",
            "5",
            "--output",
            "updated.yaml",
            "-p",
            "--report",
            "r.yaml",
        ]
        assert pseudotest.update_main(args) == ExitCode.TEST_FAILURE
    runner_class.return_value.run.assert_called_once_with(
        "test.yaml",
        "bin",
        preserve_workdir=True,
        timeout=5,
        report_file="r.yaml",
        update_mode=UpdateMode.REFERENCE,
        update_output="updated.yaml",
    )


def test_update_mode_values():
    """The Python API accepts the values of the update modes."""
    assert UpdateMode("reference_all") is UpdateMode.REFERENCE_ALL
    assert UpdateMode.TOLERANCE.description == "tolerances"
