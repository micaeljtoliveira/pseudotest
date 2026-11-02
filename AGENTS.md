# AGENTS.md

Instructions for coding agents working on this repository. They complement the
[Developer Guide](docs/developer-guide.md), which describes the architecture in more detail.

## Project

`pseudotest` is a YAML-driven regression testing framework for scientific software. It runs an executable on input
files in a temporary working directory, and checks the files it writes against reference values, with tolerances for
numbers. Two commands are installed:

- `pseudotest`: run the test of a YAML test file;
- `pseudotest-update`: run it and update the tolerances (`-t`) or the reference values (`-r`, `-R`) of the test file.

## Setup and commands

```bash
pip install -e .[devel,test]    # [docs] for the documentation
pytest                          # tests, doctests and coverage, configured in pyproject.toml
ruff check .                    # lint; `ruff check . --fix` fixes what it can
ruff format .                   # format
mypy                            # type check, configured in pyproject.toml
pre-commit install              # run the ruff hooks on every commit
zensical build --strict         # documentation, built into the ignored _site/
```

Before proposing a change, run `pytest`, `ruff check .`, `ruff format --check .` and `mypy`. They must all pass, with
coverage at 100%.

## Code

```
CLI (cli_run.py / cli_update.py)        argument parsing, logging, error handling (handle_errors)
  └─> PseudoTestRunner.run()            runner.py: one working directory shared by the inputs, run in order
        ├─> TestConfig                  config.py: YAML loading and validation, scopes, broadcast
        ├─> TestExecutor.execute()      executor.py: file staging, subprocess, MPI launcher, timeout
        └─> run_matches()               walk of the match tree: groups and leaf matches
              ├─> matchers.match()      handlers (work_dir, params) -> (calculated, reference_key)
              ├─> comparator.compare()  pure numeric/string comparison, tolerance vs printed precision
              ├─> formatting            display of the results
              ├─> report.py             YAML report entries
              └─> config_updater.py     round-trip YAML updates (pseudotest-update)
```

- `run()` returns a `RunSummary` (`results.py`), holding the `MatchResult` of every match; the entry points exit with
  its `exit_code`.
- Errors in a test file or in the files it refers to raise `UsageError` (exit code 2), reported in one line. A value
  that cannot be extracted is not an error: handlers raise `ExtractionError`, and the match fails with the reason.
- `ruamel.yaml` round-trips the test files, so that `pseudotest-update` keeps their comments and formatting.

## Public API

From 1.0.0, the project follows semantic versioning. Its [public API](docs/reference.md#public-api) is the command-line
tools and their options, the exit codes, the formats of the test files and reports, and the names exported by
`pseudotest/__init__.py`. Everything else is internal.

- Do not break the public API without being asked to: an incompatible change needs a new major version.
- A new public name is exported by `pseudotest/__init__.py` and documented in the reference.
- The oldest supported versions, Python 3.11 and `ruamel.yaml` 0.17.21, are tested by the `minimum-versions` CI job:
  update it with `pyproject.toml`.

## Conventions

- Python 3.11+, line length 120, ruff rules `E F B C4 SIM PTH UP I N C901` (complexity at most 10: extract helpers
  instead of silencing it), fully annotated code checked by mypy.
- Docstrings in Google style (`Args:`, `Returns:`, `Raises:`). Comments explain why, not what, and are sparse.
- Write code that reads like the surrounding code: reuse the existing helpers, e.g. `parse_number`, `cast_like`,
  `display_failure_details`.

### Tests

- Every bug fix comes with a regression test that fails without the fix.
- End-to-end tests (`tests/test_e2e_*.py`) use the `ws` fixture of `tests/conftest.py`: `ws.mock(files=...)` writes a
  mock executable, `ws.matches(...)` a test file, and `ws.run()` / `ws.update(mode)` return `rc`, `out` and `log`.
  Check the output and the files written, not only the exit code.
- Coverage stays at 100%, and warnings are errors.

### Documentation

- `docs/user-guide.md`: how-to with examples; `docs/reference.md`: the single place listing every key, option, exit
  code and the report format; `docs/developer-guide.md`: internals. The README is a short introduction, also the
  PyPI page.
- Update the user guide, the reference and `CHANGELOG.md` (under `[Unreleased]`, in the Keep a Changelog format) for
  every user-facing change. `tests/test_docs.py` checks the YAML examples of the documentation.

## Git workflow: OneFlow

`main` is the only long-lived branch; all other branches are short-lived and merged back into it. The procedures, for
features, releases and hotfixes, are in the [Git workflow](docs/developer-guide.md#git-workflow) section of the
developer guide.

- Work on a branch named `feature/<short-description>`, started from `main`; never commit to `main` directly.
- Open a pull request to `main`. Pull requests are merged with a merge commit.
- Releases and hotfixes are made on `release/X.Y.Z` and `hotfix/X.Y.Z` branches, whose tips are tagged `vX.Y.Z`.
  Pushing a `v*` tag publishes the package to PyPI: never create or push tags, or release and hotfix branches, unless
  asked to.
- Do not rewrite the history of a pushed branch (rebase, force push) unless asked to.

### Commit messages

- An imperative sentence, capitalised, ending with a period: `Fix the order of the keys of a match in the report.`
- When a short reason helps, add it as a second sentence of the title. For several changes, end the title with a
  colon and list them as `-` bullets on the following lines, optionally followed by a paragraph giving the context.
- No prefixes such as `feat:` or `fix:`.

### Pull requests

- The title follows the commit style. The description states what changes and why, with breaking changes first, and
  how it was tested.
