"""Unit tests for pseudotest.cli_run and pseudotest.__init__."""

from unittest.mock import MagicMock, patch

import pseudotest
import pseudotest.cli_run
from pseudotest.cli_run import handle_errors
from pseudotest.exceptions import ExitCode, UsageError


class TestPackageMain:
    """Cover pseudotest.main() which delegates to cli_run.main()."""

    def test_package_main_with_mock_runner(self):
        """Calling pseudotest.main() delegates to cli_run.main() and creates a PseudoTestRunner."""
        mock_run = MagicMock(return_value=0)
        with patch.object(
            pseudotest.cli_run,
            "PseudoTestRunner",
            lambda: type("R", (), {"run": mock_run})(),
        ):
            result = pseudotest.main(["test.yaml", "-D", "."])
        mock_run.assert_called_once()
        assert result == 0


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
