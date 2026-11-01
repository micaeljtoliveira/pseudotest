"""Unit tests for pseudotest.executor."""

import os
import stat
import subprocess
from collections import ChainMap
from pathlib import Path
from unittest.mock import patch

import pytest

from pseudotest.exceptions import UsageError
from pseudotest.executor import TestExecutor

# ---------------------------------------------------------------------------
# _resolve_executable
# ---------------------------------------------------------------------------


class TestResolveExecutable:
    def test_missing_executable(self, tmp_path):
        config = ChainMap({"Executable": "does_not_exist.py"})
        with pytest.raises(UsageError, match="not available"):
            TestExecutor._resolve_executable(config, tmp_path)

    def test_non_executable_file(self, tmp_path):
        script = tmp_path / "no_exec.py"
        script.write_text("#!/usr/bin/env python3\n")
        script.chmod(0o644)

        config = ChainMap({"Executable": "no_exec.py"})
        with pytest.raises(UsageError, match="not executable"):
            TestExecutor._resolve_executable(config, tmp_path)

    def test_valid_executable(self, tmp_path):
        script = tmp_path / "good.py"
        script.write_text("#!/usr/bin/env python3\n")
        script.chmod(script.stat().st_mode | stat.S_IXUSR)

        config = ChainMap({"Executable": "good.py"})
        result = TestExecutor._resolve_executable(config, tmp_path)
        assert result.name == "good.py"


# ---------------------------------------------------------------------------
# _prepare_files
# ---------------------------------------------------------------------------


class TestPrepareFiles:
    def test_missing_input_file(self, tmp_path):
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        with pytest.raises(UsageError, match="Input file not found"):
            TestExecutor._prepare_files(Path("nonexistent.txt"), tmp_path, work_dir, [], "argument", None)

    def test_missing_extra_file(self, tmp_path):
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        (tmp_path / "input.txt").write_text("data\n")

        with pytest.raises(UsageError, match="Extra file not found"):
            TestExecutor._prepare_files(Path("input.txt"), tmp_path, work_dir, ["does_not_exist.dat"], "argument", None)

    def test_rename_method(self, tmp_path):
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        (tmp_path / "input.txt").write_text("data\n")

        name = TestExecutor._prepare_files(Path("input.txt"), tmp_path, work_dir, [], "rename", "inp.dat")
        assert name == "inp.dat"
        assert (work_dir / "inp.dat").exists()

    def test_argument_method_copies_input(self, tmp_path):
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        (tmp_path / "input.txt").write_text("data\n")

        name = TestExecutor._prepare_files(Path("input.txt"), tmp_path, work_dir, [], "argument", None)
        assert name == "input.txt"
        assert (work_dir / "input.txt").exists()

    def test_extra_files_copied(self, tmp_path):
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        (tmp_path / "input.txt").write_text("data\n")
        (tmp_path / "extra.dat").write_text("extra\n")

        TestExecutor._prepare_files(Path("input.txt"), tmp_path, work_dir, ["extra.dat"], "argument", None)
        assert (work_dir / "extra.dat").exists()


# ---------------------------------------------------------------------------
# _build_command
# ---------------------------------------------------------------------------


class TestBuildCommand:
    def test_argument_method(self, tmp_path):
        exe = tmp_path / "prog"
        args, stdin = TestExecutor._build_command(exe, "input.txt", "argument", tmp_path)
        assert args == [exe, "input.txt"]
        assert stdin is None

    def test_stdin_method(self, tmp_path):
        exe = tmp_path / "prog"
        (tmp_path / "input.txt").write_text("data\n")
        args, stdin = TestExecutor._build_command(exe, "input.txt", "stdin", tmp_path)
        assert args == [exe]
        assert stdin is not None
        stdin.close()

    def test_rename_method(self, tmp_path):
        exe = tmp_path / "prog"
        args, stdin = TestExecutor._build_command(exe, "inp.dat", "rename", tmp_path)
        assert args == [exe]
        assert stdin is None

    def test_unknown_method_raises(self, tmp_path):
        exe = tmp_path / "prog"
        with pytest.raises(UsageError, match="Unknown input method"):
            TestExecutor._build_command(exe, "input.txt", "foobar", tmp_path)

    def test_mpi_np_flag_mpiexec(self, tmp_path):
        """mpiexec uses -np."""
        exe = tmp_path / "prog"
        config = ChainMap({"Processors": 4})
        with patch.dict(os.environ, {"MPIEXEC": "/usr/bin/mpiexec"}):
            args, _ = TestExecutor._build_command(exe, "input.txt", "argument", tmp_path, config)
        assert args[:3] == ["/usr/bin/mpiexec", "-np", "4"]

    def test_mpi_np_flag_srun(self, tmp_path):
        """srun uses -n."""
        exe = tmp_path / "prog"
        config = ChainMap({"Processors": 2})
        with patch.dict(os.environ, {"MPIEXEC": "/usr/bin/srun"}):
            args, _ = TestExecutor._build_command(exe, "input.txt", "argument", tmp_path, config)
        assert args[:3] == ["/usr/bin/srun", "-n", "2"]

    def test_mpi_np_flag_aprun(self, tmp_path):
        """aprun uses -n."""
        exe = tmp_path / "prog"
        config = ChainMap({"Processors": 6})
        with patch.dict(os.environ, {"MPIEXEC": "/usr/bin/aprun"}):
            args, _ = TestExecutor._build_command(exe, "input.txt", "argument", tmp_path, config)
        assert args[:3] == ["/usr/bin/aprun", "-n", "6"]

    def test_mpi_unknown_launcher_defaults_np(self, tmp_path):
        """Unknown launcher falls back to -np."""
        exe = tmp_path / "prog"
        config = ChainMap({"Processors": 3})
        with patch.dict(os.environ, {"MPIEXEC": "/opt/custom_mpi"}):
            args, _ = TestExecutor._build_command(exe, "input.txt", "argument", tmp_path, config)
        assert args[:3] == ["/opt/custom_mpi", "-np", "3"]

    def test_mpi_default_processors(self, tmp_path):
        """When Processors is not set, defaults to 1."""
        exe = tmp_path / "prog"
        config = ChainMap({})
        with patch.dict(os.environ, {"MPIEXEC": "/usr/bin/mpiexec"}):
            args, _ = TestExecutor._build_command(exe, "input.txt", "argument", tmp_path, config)
        assert args[:3] == ["/usr/bin/mpiexec", "-np", "1"]


# ---------------------------------------------------------------------------
# _run_subprocess — generic exception handling
# ---------------------------------------------------------------------------


class TestRunSubprocess:
    def test_generic_exception_returns_failure(self, tmp_path):
        """Patch subprocess.run to raise OSError → should return (False, elapsed)."""
        import subprocess as _subprocess

        executor = TestExecutor()
        exe = tmp_path / "prog"

        def exploding_run(*args, **kwargs):
            raise OSError("Simulated I/O error")

        (tmp_path / "stdout").write_text("")
        (tmp_path / "stderr").write_text("")

        with patch.object(_subprocess, "run", exploding_run):
            success, elapsed = executor._run_subprocess(
                [str(exe), "input.txt"],
                None,
                tmp_path,
                "input.txt",
                Path("input.txt"),
                False,
                30,
            )
        assert success is False
        assert elapsed >= 0.0


# ---------------------------------------------------------------------------
# Validation and file preparation
# ---------------------------------------------------------------------------


class TestExecuteValidation:
    @pytest.fixture
    def setup(self, tmp_path):
        exe = tmp_path / "prog"
        exe.write_text("#!/bin/sh\n")
        exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
        (tmp_path / "input.txt").write_text("data\n")
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        return tmp_path, work_dir

    def test_missing_executable_key(self, tmp_path):
        with pytest.raises(UsageError, match="No 'Executable'"):
            TestExecutor._resolve_executable(ChainMap({}), tmp_path)

    @pytest.mark.parametrize(
        ("config", "message"),
        [
            ({"InputMethod": "rename"}, "has no 'RenameTo'"),
            ({"InputMethod": "foobar"}, "Unknown input method"),
        ],
    )
    def test_invalid_input_method_raises_before_copying(self, setup, config, message):
        test_dir, work_dir = setup
        input_config = ChainMap(config, {"Executable": "prog"})
        with pytest.raises(UsageError, match=message):
            TestExecutor().execute(input_config, Path("input.txt"), test_dir, test_dir, work_dir, False, 30)
        assert list(work_dir.iterdir()) == []

    def test_input_in_subdirectory_used_by_name(self, tmp_path):
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        (tmp_path / "inputs").mkdir()
        (tmp_path / "inputs" / "case.in").write_text("data\n")

        name = TestExecutor._prepare_files(Path("inputs/case.in"), tmp_path, work_dir, [], "argument", None)
        assert name == "case.in"
        assert (work_dir / "case.in").exists()


class TestExecutionErrors:
    @pytest.mark.parametrize(
        ("error", "message"),
        [
            (subprocess.TimeoutExpired("prog", 30), "input.txt: timed out after 30 s"),
            (OSError("Simulated launch error"), "input.txt: failed to run: Simulated launch error"),
        ],
    )
    def test_reason_is_shown(self, tmp_path, capsys, error, message):
        def failing_run(*args, **kwargs):
            raise error

        with patch.object(subprocess, "run", failing_run):
            success, _ = TestExecutor()._run_subprocess(
                ["prog", "input.txt"], None, tmp_path, "input.txt", Path("input.txt"), False, 30
            )
        assert success is False
        assert message in capsys.readouterr().out
