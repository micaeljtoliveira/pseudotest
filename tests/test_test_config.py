"""Unit tests for pseudotest.test_config."""

from collections import ChainMap
from pathlib import Path

import pytest

from pseudotest.exceptions import UsageError
from pseudotest.test_config import TestConfig, broadcast_params


class TestConfigErrors:
    def test_missing_test_file(self):
        tc = TestConfig()
        with pytest.raises(UsageError, match="Test file not found"):
            tc.load(Path("/tmp/surely_does_not_exist_12345.yaml"))

    def test_invalid_yaml(self, tmp_path):
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text(":\n  - :\n    :\n  bad: [unbalanced")
        tc = TestConfig()
        with pytest.raises(UsageError, match="Failed to load test file"):
            tc.load(bad_yaml)

    def test_broadcast_mismatched_lengths(self):
        params = ChainMap({"a": [1, 2, 3], "b": [4, 5]})
        with pytest.raises(UsageError, match="same length"):
            broadcast_params(params)


class TestLoadValidation:
    @pytest.mark.parametrize(
        ("content", "message"),
        [
            ("", "must contain a mapping"),
            ("- a\n- b\n", "must contain a mapping"),
            ("Executable: a.x\nInputs: {}\n", "has no 'Name'"),
        ],
    )
    def test_invalid_test_file(self, tmp_path, content, message):
        test_file = tmp_path / "test.yaml"
        test_file.write_text(content)
        with pytest.raises(UsageError, match=message):
            TestConfig().load(test_file)

    @pytest.mark.parametrize(
        ("content", "message"),
        [
            ("Name: t\n", "'Inputs' must be a mapping"),
            ("Name: t\nInputs: [a.inp]\n", "'Inputs' must be a mapping"),
            # A default placed under Inputs would be run as an input
            ("Name: t\nInputs:\n  ExpectedFailure: true\n  a.inp: {}\n", "input 'ExpectedFailure' must be a mapping"),
        ],
    )
    def test_invalid_inputs(self, tmp_path, content, message):
        test_file = tmp_path / "test.yaml"
        test_file.write_text(content)
        tc = TestConfig()
        tc.load(test_file)
        with pytest.raises(UsageError, match=message):
            tc.validate()

    def test_input_without_parameters_uses_top_level_scope(self, tmp_path):
        test_file = tmp_path / "test.yaml"
        test_file.write_text("Name: t\nExecutable: a.x\nInputs:\n  a.inp:\n")
        tc = TestConfig()
        tc.load(test_file)
        tc.validate()
        assert tc.input_scope("a.inp")["Executable"] == "a.x"


class TestBroadcast:
    def test_lists_broadcast_and_scalars_repeat(self):
        params = ChainMap({"value": [1, 2]}, {"file": "out.txt"})
        assert [dict(p) for p in broadcast_params(params)] == [
            {"value": 1, "file": "out.txt"},
            {"value": 2, "file": "out.txt"},
        ]
