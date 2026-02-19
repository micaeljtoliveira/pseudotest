"""Shared fixtures for pseudotest tests.

Provides factory fixtures for building self-contained test workspaces
(executables, input files, YAML configs) and for invoking the CLI
entry points programmatically.
"""

from __future__ import annotations

import stat
import textwrap
from pathlib import Path

import pytest

from pseudotest.cli_run import main
from pseudotest.cli_update import main as update_main

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def exec_dir(tmp_path: Path) -> Path:
    """Create and return a ``bin/`` directory inside the test's tmp_path."""
    d = tmp_path / "bin"
    d.mkdir()
    return d


@pytest.fixture
def make_executable():
    """Factory fixture: write a Python script into a directory and make it executable."""

    def _factory(directory: Path, name: str, script: str) -> Path:
        path = directory / name
        path.write_text(textwrap.dedent(script))
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return path

    return _factory


@pytest.fixture
def make_input():
    """Factory fixture: write an input file into a directory."""

    def _factory(directory: Path, name: str = "input.txt", content: str = "placeholder\n") -> Path:
        path = directory / name
        path.write_text(content)
        return path

    return _factory


@pytest.fixture
def make_yaml():
    """Factory fixture: write a YAML test-config file into a directory."""

    def _factory(directory: Path, yaml_text: str, name: str = "test.yaml") -> Path:
        path = directory / name
        path.write_text(textwrap.dedent(yaml_text))
        return path

    return _factory


@pytest.fixture
def run_pseudotest():
    """Factory fixture: invoke ``pseudotest.runner.main()`` and return its exit code."""

    def _factory(test_yaml: Path, exec_dir: Path, extra_args: list[str] | None = None) -> int:
        args = [str(test_yaml), "-D", str(exec_dir)]
        if extra_args:
            args.extend(extra_args)
        return main(args)

    return _factory


@pytest.fixture
def run_update():
    """Factory fixture: invoke ``pseudotest-update`` and return its exit code."""

    def _factory(test_yaml: Path, exec_dir: Path, mode: str, output: Path | None = None) -> int:
        args = [str(test_yaml), "-D", str(exec_dir), mode]
        if output:
            args.extend(["-o", str(output)])
        return update_main(args)

    return _factory
