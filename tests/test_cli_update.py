"""Unit tests for pseudotest.cli_update."""

from unittest.mock import patch

import pytest

import pseudotest
import pseudotest.cli_update
from pseudotest.exceptions import ExitCode


@pytest.mark.parametrize(
    ("flag", "mode"),
    [
        ("-t", "tolerance"),
        ("--tolerance", "tolerance"),
        ("-r", "reference"),
        ("--reference", "reference"),
        ("-R", "reference_all"),
        ("--reference-all", "reference_all"),
    ],
)
def test_update_mode(flag, mode):
    """pseudotest.update_main() is the pseudotest-update command."""
    with patch.object(pseudotest.cli_update, "PseudoTestRunner") as runner_class:
        runner_class.return_value.run.return_value = ExitCode.OK
        assert pseudotest.update_main(["test.yaml", flag]) == ExitCode.OK
    runner_class.return_value.run.assert_called_once_with(
        "test.yaml", ".", preserve_workdir=False, timeout=600, update_mode=mode, update_output=None
    )


def test_options_passed_to_runner():
    with patch.object(pseudotest.cli_update, "PseudoTestRunner") as runner_class:
        runner_class.return_value.run.return_value = ExitCode.TEST_FAILURE
        args = ["test.yaml", "-r", "-D", "bin", "--timeout", "5", "--output", "updated.yaml"]
        assert pseudotest.update_main(args) == ExitCode.TEST_FAILURE
    runner_class.return_value.run.assert_called_once_with(
        "test.yaml", "bin", preserve_workdir=False, timeout=5, update_mode="reference", update_output="updated.yaml"
    )
