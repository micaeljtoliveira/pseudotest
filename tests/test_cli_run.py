"""Unit tests for pseudotest.cli_run and pseudotest.__init__."""

import logging
import runpy
import sys
from unittest.mock import patch

import pytest

import pseudotest
import pseudotest.cli_run
from pseudotest.cli_run import handle_errors, setup_logging
from pseudotest.exceptions import ExitCode, UsageError


class TestMain:
    def test_arguments_passed_to_runner(self):
        """pseudotest.main() is the pseudotest command."""
        with patch.object(pseudotest.cli_run, "PseudoTestRunner") as runner_class:
            runner_class.return_value.run.return_value = ExitCode.OK
            args = ["test.yaml", "-D", "bin", "--preserve", "--timeout", "5", "--report", "report.yaml"]
            assert pseudotest.main(args) == ExitCode.OK
        runner_class.return_value.run.assert_called_once_with("test.yaml", "bin", True, 5, report_file="report.yaml")

    def test_defaults(self):
        with patch.object(pseudotest.cli_run, "PseudoTestRunner") as runner_class:
            runner_class.return_value.run.return_value = ExitCode.TEST_FAILURE
            assert pseudotest.main(["test.yaml"]) == ExitCode.TEST_FAILURE
        runner_class.return_value.run.assert_called_once_with("test.yaml", ".", False, 600, report_file=None)


class TestSetupLogging:
    @pytest.mark.parametrize(
        ("verbosity", "level"), [(0, logging.WARNING), (1, logging.INFO), (2, logging.DEBUG), (3, logging.DEBUG)]
    )
    def test_level(self, verbosity, level):
        with patch.object(logging, "basicConfig") as basic_config:
            setup_logging(verbosity)
        assert basic_config.call_args.kwargs["level"] == level


class TestHandleErrors:
    """Exceptions raised while running the tests are turned into exit codes."""

    def test_usage_error_returns_its_exit_code(self, caplog):
        def run():
            raise UsageError("Test file not found: missing.yaml")

        assert handle_errors(run, verbosity_level=0) == ExitCode.USAGE
        assert "Test file not found: missing.yaml" in caplog.text

    def test_unexpected_error_is_internal(self, caplog, capsys):
        def run():
            raise KeyError("boom")

        assert handle_errors(run, verbosity_level=0) == ExitCode.INTERNAL
        assert "internal error" in caplog.text
        assert "use -vv" in caplog.text
        assert "Traceback" not in capsys.readouterr().err

    def test_traceback_shown_with_vv(self, capsys):
        def run():
            raise KeyError("boom")

        assert handle_errors(run, verbosity_level=2) == ExitCode.INTERNAL
        assert "Traceback" in capsys.readouterr().err

    def test_main_reports_missing_test_file(self, tmp_path, caplog):
        assert pseudotest.main([str(tmp_path / "missing.yaml")]) == ExitCode.USAGE
        assert "Test file not found" in caplog.text


def test_python_m_pseudotest(tmp_path, monkeypatch):
    """python -m pseudotest runs the pseudotest command."""
    monkeypatch.setattr(sys, "argv", ["pseudotest", str(tmp_path / "missing.yaml")])
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("pseudotest", run_name="__main__")
    assert exit_info.value.code == ExitCode.USAGE
