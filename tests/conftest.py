"""Shared fixtures for pseudotest tests.

The ``ws`` fixture builds a self-contained workspace for end-to-end tests: mock executables, input files and a YAML
test file, and runs the ``pseudotest`` and ``pseudotest-update`` entry points on them.
"""

from __future__ import annotations

import stat
import tempfile
import textwrap
from pathlib import Path
from typing import Any, NamedTuple

import pytest

from pseudotest import matchers
from pseudotest.cli_run import main
from pseudotest.cli_update import main as update_main
from pseudotest.test_config import yaml

# Files written by the default mock executable
RESULTS = """\
Energy: -42.5000 Ry  0.3  0.4
Total force: 1.2345e-03 Ha
Status converged OK
Iterations 10
WARNING: step skipped
WARNING: step skipped
"""
DEFAULT_FILES = {
    "results.txt": RESULTS,
    "output_dir/data_a.txt": "file_a\n",
    "output_dir/data_b.txt": "file_b\n",
}


class RunResult(NamedTuple):
    """Exit code, standard output and log messages of one run of an entry point."""

    rc: int
    out: str
    log: str


class Workspace:
    """A test directory with a ``bin/`` directory for the executables.

    The test file is ``test.yaml`` and an input file ``input.txt`` is created, so that most tests only have to write
    the mock executable and the matches. The working directories of the runs are created in ``work/``.
    """

    def __init__(self, root: Path, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture):
        self.root = root
        self.bin = root / "bin"
        self.bin.mkdir()
        self.work_root = root / "work"
        self.work_root.mkdir()
        self.test_file = root / "test.yaml"
        self.report = root / "report.yaml"
        self._capsys = capsys
        self._caplog = caplog
        self.input()

    def executable(self, script: str, name: str = "mock.py") -> Path:
        """Write the Python *script* as an executable of ``bin/``."""
        path = self.bin / name
        path.write_text(textwrap.dedent(script))
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return path

    def mock(
        self,
        files: dict[str, str] | None = None,
        *,
        name: str = "mock.py",
        exit_code: int = 0,
        stdout: str = "",
        stderr: str = "",
        sleep: float = 0,
        requires: tuple[str, ...] = (),
    ) -> Path:
        """Write a mock executable that writes *files* in its working directory.

        Args:
            files: Files to write, by path relative to the working directory (default: :data:`DEFAULT_FILES`)
            name: Name of the executable
            exit_code: Exit code of the executable
            stdout: Text written to the standard output
            stderr: Text written to the standard error
            sleep: Time to sleep before doing anything, in seconds
            requires: Files that must be in the working directory, otherwise the executable fails
        """
        files = DEFAULT_FILES if files is None else files
        return self.executable(
            f"""\
            #!/usr/bin/env python3
            import os, sys, time

            time.sleep({sleep})
            if not all(os.path.exists(name) for name in {list(requires)!r}):
                sys.exit(1)
            for name, content in {files!r}.items():
                os.makedirs(os.path.dirname(name) or ".", exist_ok=True)
                with open(name, "w") as f:
                    f.write(content)
            sys.stdout.write({stdout!r})
            sys.stderr.write({stderr!r})
            sys.exit({exit_code})
            """,
            name,
        )

    def input(self, name: str = "input.txt", content: str = "placeholder\n") -> Path:
        """Write an input file, relative to the test directory."""
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def config(self, text: str, name: str = "test.yaml") -> Path:
        """Write a YAML test file."""
        path = self.root / name
        path.write_text(textwrap.dedent(text))
        return path

    def matches(self, text: str, *, name: str = "Test", executable: str = "mock.py") -> Path:
        """Write a test file running *executable* on ``input.txt`` with the given matches."""
        matches = textwrap.indent(textwrap.dedent(text), " " * 6)
        return self.config(f"Name: {name}\nExecutable: {executable}\nInputs:\n  input.txt:\n    Matches:\n{matches}")

    def _call(self, entry_point: Any, args: list[str]) -> RunResult:
        self._capsys.readouterr()
        self._caplog.clear()
        rc = entry_point(args)
        return RunResult(rc, self._capsys.readouterr().out, self._caplog.text)

    def run(self, *args: str, test_file: Path | None = None) -> RunResult:
        """Run ``pseudotest`` on the test file with the executables of ``bin/``."""
        return self._call(main, [str(test_file or self.test_file), "-D", str(self.bin), *args])

    def update(self, mode: str, *args: str, test_file: Path | None = None) -> RunResult:
        """Run ``pseudotest-update`` in *mode* (``-t``, ``-r`` or ``-R``) on the test file."""
        return self._call(update_main, [str(test_file or self.test_file), "-D", str(self.bin), mode, *args])

    def load_config(self, path: Path | None = None) -> Any:
        """Load a YAML test file, by default the test file."""
        return yaml.load(path or self.test_file)

    def load_matches(self, path: Path | None = None) -> Any:
        """Load the matches of ``input.txt`` from a test file."""
        return self.load_config(path)["Inputs"]["input.txt"]["Matches"]

    def load_report_documents(self) -> list[Any]:
        """Load all the documents of the report."""
        return list(yaml.load_all(self.report))

    def load_report(self) -> Any:
        """Load the last document of the report, without its test-file key."""
        document = self.load_report_documents()[-1]
        return document[next(iter(document))]


@pytest.fixture
def ws(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> Workspace:
    """A workspace for end-to-end tests, see :class:`Workspace`."""
    workspace = Workspace(tmp_path, capsys, caplog)
    monkeypatch.setattr(tempfile, "tempdir", str(workspace.work_root))
    return workspace


@pytest.fixture
def restore_match_registry():
    """Restore the match handlers and key sets changed by a test that registers a match handler.

    The key sets are restored in place, as other modules hold references to them.
    """
    handlers = list(matchers._MATCH_HANDLERS)
    key_sets = [matchers.RESERVED_KEYS, matchers.REFERENCE_KEYS, matchers.INTERNAL_KEYS, matchers.NON_UPDATABLE_KEYS]
    saved_key_sets = [set(key_set) for key_set in key_sets]
    yield
    matchers._MATCH_HANDLERS[:] = handlers
    for key_set, saved in zip(key_sets, saved_key_sets, strict=True):
        key_set.clear()
        key_set.update(saved)
