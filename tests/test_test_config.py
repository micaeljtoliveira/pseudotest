"""Unit tests for pseudotest.test_config."""

from pathlib import Path

import pytest

from pseudotest.test_config import TestConfig, broadcast_params


class TestConfigErrors:
    def test_missing_test_file(self):
        tc = TestConfig()
        with pytest.raises(FileNotFoundError, match="Test file not found"):
            tc.load(Path("/tmp/surely_does_not_exist_12345.yaml"))

    def test_invalid_yaml(self, tmp_path):
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text(":\n  - :\n    :\n  bad: [unbalanced")
        tc = TestConfig()
        with pytest.raises(ValueError, match="Failed to load test file"):
            tc.load(bad_yaml)

    def test_broadcast_mismatched_lengths(self):
        from collections import ChainMap

        from pseudotest.exceptions import UsageError

        params = ChainMap({"a": [1, 2, 3], "b": [4, 5]})
        with pytest.raises(UsageError, match="same length"):
            broadcast_params(params)
