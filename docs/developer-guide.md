# Developer Guide

This guide is for contributors extending or maintaining `pseudotest`. The [Reference](reference.md) describes the
test file format, the command-line options and the exit codes, which are not repeated here.

## Project layout

```
pseudotest/
  cli_run.py            # Entry point: pseudotest, logging set-up and error handling
  cli_update.py         # Entry point: pseudotest-update
  __main__.py           # python -m pseudotest
  runner.py             # Top-level orchestration (PseudoTestRunner)
  executor.py           # Subprocess execution and workdir/file preparation
  matchers.py           # Match dispatch and built-in match handlers
  value_extractors.py   # Pure text extraction helpers
  comparator.py         # Number parsing, numeric/string comparison and tolerance behavior
  results.py            # MatchResult and RunSummary, the outcomes of a match and of a run
  config_updater.py     # In-place YAML updates for tolerance/reference modes
  report.py             # Report entries and YAML serialization
  config.py             # YAML loading, validation, scope helpers, and broadcast expansion
  formatting.py         # Terminal output (match results, failed executions), colors, and indentation
  exceptions.py         # Exception classes (including ExtractionError) and exit codes
tests/
  conftest.py              # Shared fixtures, including the `ws` workspace of the end-to-end tests
  test_e2e_run.py          # End-to-end tests: matches, input methods, execution
  test_e2e_report.py       # End-to-end tests: YAML report
  test_e2e_update.py       # End-to-end tests: pseudotest-update
  test_e2e_errors.py       # End-to-end tests: test-file errors, exit codes, installed scripts
  test_docs.py             # Checks of the YAML examples of the documentation
  test_runner.py           # Unit tests for the walk of the match tree
  test_matchers.py         # Unit tests for match handlers
  test_executor.py         # Unit tests for execution engine
  test_comparator.py       # Unit tests for comparison logic
  test_config_updater.py   # Unit tests for match updates
  test_value_extractors.py # Unit tests for value extractors
  test_config.py           # Unit tests for configuration loading and parameter broadcasting
  test_results.py          # Unit tests for match results and run summaries
  test_cli_run.py          # Unit tests for the pseudotest entry point, logging and error handling
  test_cli_update.py       # Unit tests for the pseudotest-update entry point
  test_formatting.py       # Unit tests for output and display formatting
  test_report.py           # Unit tests for execution report
```

## Architecture overview

`PseudoTestRunner.run()` coordinates the full workflow:

1. Load the test file (`TestConfig.load`) and, unless the test is disabled, validate its inputs
   (`TestConfig.validate`).
2. Create a temporary working directory, shared by all the inputs.
3. For each input listed under `Inputs`, in `_run_input`:
   - Run the executable with `TestExecutor` (copies files, builds the command, runs the subprocess).
   - Walk the match tree with `run_matches`, which evaluates each leaf match through `matchers.match()` (extract the
     value, compare, display) and applies the updates requested by `pseudotest-update`.
   - Collect the report entries.
4. Remove the working directory (in a `finally` block, so also on errors), unless `--preserve` is given.
5. Print the summary statistics, optionally write the YAML report and the updated test file, and return the
   `RunSummary` of the run, which counts the failed executions and holds the `MatchResult` of every match. The
   entry points exit with its `exit_code`.

Key design choices:

- **Separation of concerns**: execution, matching, comparison, reporting, and updating are in distinct modules. Some
  dependencies remain: the comparator displays its results, and the report and the updater use the key sets of the
  matchers.
- **Predicate-based handler dispatch**: match handlers are registered with a predicate; the first one whose predicate
  returns `True` handles the match. This makes it possible to add match types without modifying existing code.
- **YAML round-trip via ruamel.yaml**: comments and formatting are preserved when `pseudotest-update` writes back to
  the test file.
- **ChainMap scoping**: an input inherits the top-level keys, and a match inherits the parameters of its groups.

## Development setup

```bash
pip install -e .[devel,test]
```

Recommended checks before committing:

```bash
pytest
ruff check .
ruff format .
mypy
```

A pre-commit hook for the ruff checks is available and it is strongly recommended to activate it.

`pytest` also runs the examples of the docstrings as doctests and reports the coverage, which is 100%, as
configured in `pyproject.toml`. Warnings are errors. Add `--cov-report=html` for a browsable coverage report in
`htmlcov/`.

## Errors and exit codes

User errors raise `UsageError` (a `CliError` with exit code 2):

- `TestConfig.load`: missing or invalid test file, no `Name`.
- `TestConfig.validate`: missing `Inputs`, or an input that is not a mapping.
- `TestExecutor`: no `Executable`, executable missing or not executable, missing input or extra file, unknown
  `InputMethod`, `rename` without `RenameTo`. The input method is validated before any file is copied.
- `PseudoTestRunner.run_matches`: a match that is not a mapping, an unknown match parameter, or a match named after a
  parameter.
- `matchers.match()` and its handlers: no `file` or `directory`, `line: 0`, missing extraction parameters.

Both entry points add their shared arguments with `cli_run.add_common_arguments`, and run the test with
`cli_run.run_tests`, which passes the run to `cli_run.handle_errors`. It turns a `CliError` into its exit code with a
one-line `ERROR:` message, and any other exception into `ExitCode.INTERNAL` (99). With `-vv`, the traceback is printed
too. `ExitCode.RUNTIME` (3) is reserved: nothing raises a plain `CliError` yet.

## Configuration scoping

`TestConfig.input_scope(input_name)` returns a `ChainMap` with two layers:

1. The parameters of the input (the mapping under `Inputs.<name>`, empty when the input has none).
2. The top-level keys of the test file.

Any key of the input shadows the same top-level key, and missing keys fall through to the top level.

### Match tree

`PseudoTestRunner.run_matches(scope, work_dir, indent_level, scope_path)` walks a `Matches` mapping:

- Keys in `RESERVED_KEYS` are parameters of the current scope, inherited by its matches. A reserved key holding a
  mapping is an error: a match cannot be named after a parameter.
- A match is a **group** if it contains a mapping under a key that is not a parameter. Its parameters are chained in
  front of the inherited ones and `run_matches` recurses into it.
- Otherwise it is a **leaf**: all its keys must be in `RESERVED_KEYS`, and `_run_leaf_match` evaluates it.

`scope_path` (e.g. `Inputs > input.txt > Matches > energy`) locates the match in the error messages.

### Broadcast parameter expansion

`broadcast_params(params)` detects list-valued keys and expands the `ChainMap` into one `ChainMap` per list index:

- All list-valued keys must have the same length; a `UsageError` is raised otherwise.
- Scalar keys are copied unchanged into every expanded `ChainMap`.

`_run_leaf_match` names each element after its `match` value, or `name[i]` when there is no `match` list.

```python
params = ChainMap({"file": ["a.txt", "b.txt"], "field": 2, "value": [1.0, 2.0]})
result = broadcast_params(params)
# result[0] = {"file": "a.txt", "field": 2, "value": 1.0}
# result[1] = {"file": "b.txt", "field": 2, "value": 2.0}
```

## Match system internals

`pseudotest.matchers` maintains a registry of `(predicate, handler)` pairs: `_MATCH_HANDLERS` for the handlers
registered with `register_match_handler()`, and `_BUILTIN_MATCH_HANDLERS` for the built-in ones. `match(name, params,
work_dir)` calls the first handler whose predicate returns `True` for the parameters, trying the registered handlers
before the built-in ones. The handler extracts the calculated value, which `match()` compares with the reference
value using `comparator.compare`. `match()` returns a `MatchResult` (see [Match results](#match-results)), and does
not display anything.

### Key sets

Four sets are accumulated by `register_match_handler()`:

| Set | Purpose |
|---|---|
| `RESERVED_KEYS` | All match parameters; tells parameters from match names, and rejects unknown parameters |
| `REFERENCE_KEYS` | Keys that hold a reference value (`value`, `count`, `size`, `count_files`, `file_is_present`) |
| `INTERNAL_KEYS` | Keys excluded from reports (`match`) |
| `NON_UPDATABLE_KEYS` | Reference keys that `pseudotest-update` must never modify (`file_is_present`) |

### Adding a new match type

Implement a handler with the signature:

```python
def my_handler(work_dir: Path, params: ChainMap[str, Any]) -> tuple[str, str]:
    """Return (calculated_value, reference_key).

    The calculated value is extracted from the files of the working directory, and the reference key is the parameter
    holding the reference value. Raise ExtractionError(reason, reference_key) when no value can be extracted, e.g.
    because a file or a pattern is missing: the match then fails with that reason.
    """
    ...
```

The handler finds its files from its parameters, relative to the working directory. Register it:

```python
from pseudotest.matchers import register_match_handler

register_match_handler(
    predicate=lambda params: "my_key" in params,
    handler=my_handler,
    keys={"my_key", "my_ref"},  # all recognised keys for this handler
    reference_keys={"my_ref"},  # key(s) holding the expected value
    internal_keys=set(),  # keys excluded from reports
    non_updatable_keys=set(),  # reference keys that must not be auto-updated
)
```

Every key of the new match type must be registered: a key that is not in `RESERVED_KEYS` is rejected as an unknown
match parameter.

Complete example — a handler that checks a file's line count:

```python
from collections import ChainMap
from pathlib import Path
from typing import Any

from pseudotest.exceptions import ExtractionError
from pseudotest.matchers import register_match_handler


def handle_line_count(work_dir: Path, params: ChainMap[str, Any]) -> tuple[str, str]:
    try:
        lines = (work_dir / params["file"]).read_text().splitlines()
    except OSError as e:
        raise ExtractionError(f"'{params['file']}' cannot be read: {e.strerror}", "line_count") from e
    return str(len(lines)), "line_count"


register_match_handler(
    predicate=lambda params: "file" in params and "line_count" in params,
    handler=handle_line_count,
    keys={"file", "line_count"},
    reference_keys={"line_count"},
)
```

Registered handlers are tried before the built-in ones, so this handler takes the matches with `line_count` before
the built-in content handler, which takes any other match with `file`. It can then be used in YAML:

```yaml
Matches:
  output_lines:
    file: results.txt
    line_count: 42
```

After registering, add unit tests in `tests/test_matchers.py` and an end-to-end test in `tests/test_e2e_run.py`.

In version 0.3 and earlier, handlers had the signature `(target_path, params) -> (calculated_value, reference_value)`, with
the target path taken from `file` or `directory`, and returned `(None, None)` when no value could be extracted.

### Match results

A `results.MatchResult` holds everything known about an evaluated match: its name and parameters, whether it passed,
the calculated and reference values, the reference key, the tolerance, the difference of a numeric comparison, the
precision of the calculated value when the tolerance is smaller than it, and the reason of a failure. The runner
passes each result to:

- `formatting.display_match_result`, which prints the status of the match and, when it failed, the details;
- `ReportWriter.build_match_entry`, which builds its report entry;
- `config_updater.apply_match_updates`, which updates the test file, using the reference key of the result.

## Value extractors

`pseudotest.value_extractors` contains four pure functions with no I/O or side effects. Their docstrings have
examples, which are run as doctests.

- `get_target_line(lines, line_num)`: returns `lines[line_num]`, with Python indexing (0-based, negative from the
  end), or `None` when out of range. `matchers` converts the 1-based `line` parameter to this index.
- `find_pattern_line(lines, pattern, offset=0)`: returns the line at `offset` from the first line containing
  `pattern` as a substring (case-sensitive), or `None` if the pattern is not found or the offset is out of range.
- `extract_field_from_line(line, field_num)`: splits `line` on whitespace sequences or commas (with optional
  surrounding whitespace) and returns the 1-based field, like `awk '{print $N}'`. Two consecutive commas give an
  empty string. Returns `None` for `None` input or an out-of-range field.
- `extract_column_from_line(line, column_pos)`: like `cut -c<column_pos>- | awk '{print $1}'`, with tokens delimited by
  whitespace or commas. Returns `None` if `column_pos` exceeds the line length, and `""` if there is no token after
  that position.

## Execution internals

`TestExecutor.execute()` performs four steps:

1. **Resolve executable**: verifies the file exists at `exec_path/Executable` and has the execute bit.
2. **Prepare files**: validates the input method, then copies the input file and each `ExtraFiles` entry from the test
   directory into `temp_dir`, flat. The input keeps its file name, or is copied as `RenameTo` in `rename` mode.
3. **Build command**: assembles the subprocess argument list. When `MPIEXEC` is set, splits it like a shell command
   (so that it can include options of the launcher) and prepends `[*launcher, <flag>, <Processors>]`, using the flag
   from `_MPI_NP_FLAG` (keyed by the basename of the launcher).
4. **Run subprocess**: runs inside `temp_dir`, capturing stdout and stderr to files named `stdout` and `stderr` in the
   working directory. A non-zero exit code is a failure. Timeouts and launch failures are reported through
   `OutputFormatter.print_execution_error`.

For `stdin` mode, the input file is opened and passed as `stdin`; the file handle is closed in a `finally` block. In
every mode, the copied input file is then deleted from the working directory, so that it is not mistaken for an output
by the matches and the next inputs.

## Comparison and tolerance behavior

`comparator.parse_number` parses numbers, accepting Fortran `D` exponents; `is_number` is built on it.
`compare(calculated, reference, tolerance)` returns a `Comparison` (passed, difference, precision, reason), and
dispatches on whether both values are numbers:

- **Numeric**: `abs(calculated - reference) <= tol`, or `== 0.0` without `tol`. Equal infinities, and two nans, have a
  difference of `0.0`.
- **String**: `str(calculated) == str(reference)`.

When `tol` is set and the precision implied by the string format of the calculated value
(`get_precision_from_string_format`) is coarser than `tol`, the match is **unconditionally failed**. For example, a
value printed as `1.234` has precision `0.001`; setting `tol: 1e-6` fails because the output cannot distinguish
differences smaller than `0.001`. The failure details show the tolerance and the effective precision instead of the
usual calculated/reference/difference lines, and suggest a minimum tolerance. Failure details are printed by
`formatting.display_match_result`.

A zero written in scientific notation (e.g. `0.00000000E+000`) has precision `0.0`: every non-zero value is written
with its own exponent, so the zero is exact and any tolerance is accepted for it. Without this, a match that is
exactly zero with one compiler and a rounding residue such as `4.2E-22` with another could not pass on both, and the
tolerance update jobs would undo each other. `inf` and `nan` are exact too.

## Config updater internals

`apply_match_updates(match_def, results, mode)`, where `mode` is an `UpdateMode` (`TOLERANCE`, `REFERENCE` or
`REFERENCE_ALL`) or its value, iterates over the `MatchResult` of each broadcast element and patches
the raw ruamel.yaml dict in-place. Protected matches, non-updatable reference keys and extraction failures are
skipped.

**Tolerance mode** (`_update_tolerance`):

1. Computes `compute_tolerance(|calculated - reference|)`, and takes the precision of the calculated value if it is
   larger, so that the match passes on the next run. Infinite or nan differences are skipped with a warning.
2. If `total > 1` (broadcast), ensures `tol` in `match_def` is a list of length `total`, then sets the element at the
   failing index.
3. If `total == 1`, sets `tol` directly.

**Reference mode** (`_update_reference`):

1. Takes the reference key of the result, and skips the update if the reference is inherited from a group.
2. Skips, with a warning, a numeric reference that the calculated value would replace with text.
3. Calls `cast_like(calculated_value, reference)` to match the original Python/YAML type.

`cast_like` is also used by the report. Type mapping:

| Reference type | Result |
|---|---|
| `bool` (including ruamel's `ScalarBoolean`) | `True`/`False` from `true`/`yes`/`on` or `false`/`no`/`off`, any case |
| `ScalarFloat` | `ScalarFloat` with the notation and precision of the reference (`_make_scalar_float`); a plain float for `inf`/`nan` |
| `int` | `int` when the value is integral, `float` otherwise |
| `float` | `float` |
| anything else | the calculated string |

A value that cannot be parsed as the reference type is returned as a string.

## Report format internals

`ReportWriter.write(report_file, test_file_path, test_config_data, report_inputs)` serialises the report of one run to
YAML, keyed by `test_file_path` without a leading `./`, and appends it to `report_file` after a `---` separator
(standard YAML multi-document format). A disabled test is written with an empty `Inputs` mapping.

`build_input_entry` constructs:

```python
{
    "InputMethod": ...,
    "Processors": ...,
    "ExpectedFailure": ...,
    "Execution": "pass" | "fail",
    "Elapsed time": float,
    "Matches": { ... }
}
```

`build_match_entry(result)` constructs one entry per match with:

- all non-internal parameters of the match, in their order, with the inherited ones first;
- the calculated value, cast with `cast_like`, under the reference key of the result, and the reference value under
  the `reference` key;
- `status`, `pass` or `fail`, and, for a failed match, the `reason`.

Keys in `INTERNAL_KEYS` (currently just `match`) are excluded.

## Testing strategy

- **Unit tests** target isolated modules: extractors, matchers, comparator, executor, updater, formatting, report,
  runner and the entry points.
- **End-to-end tests** (`test_e2e_*.py`) run the `main()` functions of the entry points on self-contained workspaces,
  and check the exit code, the output, and the test files and reports written. `test_e2e_errors.py` also runs the
  installed scripts in subprocesses.
- **Documentation tests** (`test_docs.py`) check that every `yaml` code block of the README and of the user
  documentation parses and uses only known keys.

The end-to-end tests use the `ws` fixture of `conftest.py`, a `Workspace` with a `bin/` directory for the
executables, an `input.txt` input file, and a `work/` directory for the working directories of the runs:

```python
def test_energy(ws):
    ws.mock({"results.txt": "Energy: -42.5000\n"})  # mock executable writing results.txt
    ws.matches("energy: {file: results.txt, grep: 'Energy:', field: 2, value: -42.5}")
    result = ws.run()  # or ws.update("-r"), with extra command-line arguments
    assert result.rc == ExitCode.OK
    assert "energy" in result.out  # standard output; result.log holds the log messages
```

`ws.mock()` writes a Python mock executable (so the tests run on any platform) with the files to write, its exit
code, outputs, and the files it requires. `ws.executable()` writes any other script, `ws.input()` and `ws.config()`
write input and test files, and `ws.load_matches()` and `ws.load_report()` read back the results. Check the output
of the runs, not only their exit codes.

Prefer adding tests close to the changed behavior. For a new match handler, add:

1. Unit test in `test_matchers.py` covering successful extraction, extraction failure (`None`), and any `UsageError`
   paths.
2. End-to-end test in `test_e2e_run.py` using a mock executable that writes the expected output format.

## Contribution checklist

1. Keep API and YAML behavior backward-compatible unless intentionally versioned.
2. Add or update tests for new logic and edge cases.
3. Run `pytest`, `ruff check .` and `mypy`.
4. Update the user guide, the reference, and the changelog for any user-facing behavior change.
5. Keep match, update, and report semantics consistent. A new reference key must be added to `REFERENCE_KEYS` for
   update and report to handle it correctly.

## Documentation

The documentation is built with [Zensical](https://zensical.org/), from the sources in `docs/`:

```bash
pip install -e .[docs]
zensical serve      # live-reload preview at http://127.0.0.1:8000
zensical build      # build static site to _site/
```

Navigation is defined in `mkdocs.yml`.
