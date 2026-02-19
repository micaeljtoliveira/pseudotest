"""Unit tests for pseudotest.cli_run and pseudotest.__init__."""

from unittest.mock import MagicMock, patch

import pseudotest
import pseudotest.cli_run


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
