# Developer Guide

This guide is for contributors extending or maintaining `pseudotest`.

## Project layout

```
pseudotest/
  cli_run.py            # Entry point: pseudotest
  cli_update.py         # Entry point: pseudotest-update
  runner.py             # Top-level orchestration (PseudoTestRunner)
  executor.py           # Subprocess execution and workdir/file preparation
  matchers.py           # Match dispatch and built-in match handlers
  value_extractors.py   # Pure text extraction helpers
  comparator.py         # Numeric/string comparison logic and tolerance behavior
  config_updater.py     # In-place YAML updates for tolerance/reference modes
  report.py             # Report model and YAML serialization
  test_config.py        # YAML loading, scope helpers, and broadcast expansion
  formatting.py         # Terminal output, colors, and indentation
  exceptions.py         # Exception classes and exit codes
tests/
  conftest.py              # Shared pytest fixtures
  test_integration.py      # End-to-end tests with mock executables
  test_matchers.py         # Unit tests for match handlers
  test_executor.py         # Unit tests for execution engine
  test_comparator.py       # Unit tests for comparison logic
  test_config_updater.py   # Unit tests for match updates
  test_value_extractors.py # Unit tests for value extractors
  test_test_config.py      # Unit tests for configuration loading and parameter broadcasting
  test_cli_run.py          # Unit tests for top-level entry point
  test_formatting.py       # Unit tests for output and display formatting
  test_report.py           # Unit tests for execution report
```

## Architecture overview

`PseudoTestRunner` coordinates the full workflow:

1. Load YAML test config (`TestConfig`).
2. Create a temporary work directory.
3. For each input listed under `Inputs`:
   - Run executable with `TestExecutor` (copies files, builds command, runs subprocess).
   - Evaluate matches through `matchers.match()` (extract value, compare, optionally update config).
   - Collect report entries.
4. Emit summary statistics and return an exit code.
5. Optionally write a YAML report and/or the updated config.

Key design choices:

- **Separation of concerns**: execution, matching, comparison, reporting, and updating are in distinct modules with no cross-cutting dependencies.
- **Predicate-based handler dispatch**: match handlers are registered with a predicate; the first one whose predicate returns `True` handles the match. This makes it easy to add new match types without modifying existing code.
- **YAML round-trip via ruamel.yaml**: comments and formatting are preserved when `pseudotest-update` writes back to the config file.
- **ChainMap scoping**: per-input configuration inherits from top-level defaults, enabling DRY configs with per-input overrides.

## Development setup

```bash
pip install -e .[devel,test]
```

Recommended checks before committing:

```bash
pytest
ruff check .
ruff format .
```

A pre-commit hook for the ruff checks is available and it is strongly recommended to activate it.

Coverage report (`htmlcov/`) is generated automatically by `pytest` as configured in `pyproject.toml`.

## CLI contracts

### `pseudotest`

From `cli_run.py`:

| Argument | Type | Default | Description |
|---|---|---|---|
| `test_file` | positional | — | YAML test config path |
| `-D, --directory` | option | `.` | Directory containing executables |
| `-p, --preserve` | flag | `False` | Keep temp workdir after run |
| `-v, --verbose` | count | `0` (WARNING) | `-v` = INFO, `-vv` = DEBUG |
| `-t, --timeout` | int | `600` | Per-input timeout in seconds |
| `-r, --report FILE` | option | `None` | Append YAML report to FILE |

### `pseudotest-update`

From `cli_update.py`:

| Argument | Type | Default | Description |
|---|---|---|---|
| `test_file` | positional | — | YAML test config path |
| `-D, --directory` | option | `.` | Directory containing executables |
| `-v, --verbose` | count | `0` | Logging verbosity |
| `--timeout` | int | `600` | Per-input timeout in seconds |
| `-t, --tolerance` | flag (exclusive) | — | Update `tol` for failing numeric matches |
| `-r, --reference` | flag (exclusive) | — | Update reference values for failing matches |
| `-o, --output FILE` | option | `None` | Write updates to FILE instead of overwriting |

`--tolerance` and `--reference` are mutually exclusive and one is required.

## YAML schema

### Top-level keys

```
Name          (required str)
Enabled       (bool, default true)
Executable    (required str)
InputMethod   (str: argument|stdin|rename, default argument)
RenameTo      (str, required when InputMethod=rename)
Inputs        (required mapping)
```

### Per-input keys

```
ExtraFiles      (list[str])
Processors      (int, default 1)
ExpectedFailure (bool, default false)
InputMethod     (str, overrides top-level)
RenameTo        (str, overrides top-level)
Matches         (mapping)
```

Top-level keys (`Executable`, `InputMethod`, `RenameTo`) serve as defaults. Any per-input definition takes precedence via `ChainMap`.

### Match keys

```
file           target file path (for file/content matches)
directory      target directory path (for directory matches)
grep           substring to search for
line           1-based line number, or offset from grep match
field          1-based whitespace-separated field index
column         1-based character column start position
field_re       field index for real part (complex magnitude)
field_im       field index for imaginary part (complex magnitude)
value          reference value (content matches)
count          expected number of matching lines (grep)
size           expected file size in bytes
file_is_present  filename expected inside a directory
count_files    expected number of files in a directory
tol            absolute numeric tolerance
protected      bool; prevents pseudotest-update from modifying this match
match          (internal) broadcast element display label
```

### Configuration scoping

`TestConfig.input_scope(input_name)` returns a `ChainMap` with three layers:

1. Per-input overrides (the dict under `Inputs.<name>`)
2. Input-level defaults (empty unless explicitly provided)
3. Top-level defaults (`Name`, `Executable`, `InputMethod`, etc.)

This means any key present in the per-input dict shadows the same key from the top level, while missing keys fall through to top-level defaults automatically.

### Broadcast parameter expansion

`broadcast_params(params)` detects list-valued keys and expands the `ChainMap` into one `ChainMap` per list index. Rules:

- All list-valued keys must have the same length; a `UsageError` is raised otherwise.
- Scalar keys are copied unchanged into every expanded `ChainMap`.
- The internal `match` key is set to the index label for display purposes.

Example:

```python
params = {"file": ["a.txt", "b.txt"], "field": 2, "value": [1.0, 2.0]}
result = broadcast_params(params)
# result[0] = {"file": "a.txt", "field": 2, "value": 1.0, "match": "0"}
# result[1] = {"file": "b.txt", "field": 2, "value": 2.0, "match": "1"}
```

## Match system internals

`pseudotest.matchers` maintains a registry of `(predicate, handler)` pairs in `_MATCH_HANDLERS`. When `match()` is called, it iterates the registry and calls the first handler whose predicate returns `True` for the given params.

### Key sets

Four sets are accumulated by `register_match_handler()` and used by the runner and updater:

| Set | Purpose |
|---|---|
| `RESERVED_KEYS` | All keys recognised by any handler; used to detect unknown keys |
| `REFERENCE_KEYS` | Keys that hold a reference value (`value`, `count`, `size`, `count_files`, `file_is_present`) |
| `INTERNAL_KEYS` | Keys excluded from reports (`match`) |
| `NON_UPDATABLE_KEYS` | Reference keys that `pseudotest-update` must never modify (`file_is_present`) |

### Adding a new match type

Implement a handler with the signature:

```python
def my_handler(target_path: Path, params: ChainMap[str, Any]) -> tuple[str | None, Any]:
    """Return (calculated_value, reference_value).

    Return (None, None) to signal extraction failure (the match is marked as failed).
    """
    ...
```

Register it:

```python
from pseudotest.matchers import register_match_handler

register_match_handler(
    predicate=lambda params: "my_key" in params,
    handler=my_handler,
    keys={"my_key", "my_ref"},          # all recognised keys for this handler
    reference_keys={"my_ref"},           # key(s) holding the expected value
    internal_keys=set(),                 # keys excluded from reports
    non_updatable_keys=set(),            # reference keys that must not be auto-updated
)
```

Complete example — a handler that checks a file's line count:

```python
from collections import ChainMap
from pathlib import Path
from typing import Any

from pseudotest.matchers import register_match_handler


def handle_line_count(filepath: Path, params: ChainMap[str, Any]) -> tuple[str | None, Any]:
    try:
        lines = filepath.read_text().splitlines()
    except OSError:
        return None, None
    calculated = str(len(lines))
    reference = params["line_count"]
    return calculated, reference


register_match_handler(
    predicate=lambda params: "file" in params and "line_count" in params,
    handler=handle_line_count,
    keys={"file", "line_count"},
    reference_keys={"line_count"},
)
```

This handler can then be used in YAML:

```yaml
Matches:
  output_lines:
    file: results.txt
    line_count: 42
```

After registering, add unit tests in `tests/test_matchers.py` and integration coverage in `tests/test_integration.py`.

## Value extractors

`pseudotest.value_extractors` contains four pure functions with no I/O or side effects:

### `get_target_line(lines, line_num)`

Returns `lines[line_num - 1]` for positive `line_num` (1-based), or `lines[line_num]` for negative values (Python-style end indexing: `-1` = last line). Returns `None` for out-of-bounds.

Note: this function receives a 0-based index internally (`matchers.py` subtracts 1 before calling it for the `line` case).

### `find_pattern_line(lines, pattern, offset=0)`

Returns the line at `offset` from the first line containing `pattern` as a substring (case-sensitive). Returns `None` if the pattern is not found or the offset takes the index out of range.

### `extract_field_from_line(line, field_num)`

Splits `line` on whitespace and returns the element at `field_num - 1` (1-based, like `awk '{print $N}'`). Returns `None` for `None` input or out-of-range index.

### `extract_column_from_line(line, column_pos)`

Equivalent to `cut -c<column_pos>- | awk '{print $1}'`. Slices the line starting at `column_pos` (1-based), strips leading whitespace, and returns the first token. Returns `None` if `column_pos` exceeds line length; returns `""` if there are no tokens after that position.

## Execution internals

`TestExecutor.execute()` performs four steps:

1. **Resolve executable** – verifies the file exists at `exec_path/Executable` and has the execute bit.
2. **Prepare files** – copies the input file and each `ExtraFiles` entry from the test directory into `temp_dir`. For `rename` mode, the input is copied as `RenameTo`; for other modes, the original filename is preserved.
3. **Build command** – assembles the subprocess argument list. When `MPIEXEC` is set, prepends `[mpiexec, <flag>, <Processors>]` using the flag from `_MPI_NP_FLAG` (keyed by launcher basename).
4. **Run subprocess** – runs inside `temp_dir`, capturing stdout and stderr to files named `stdout` and `stderr` in the work directory. A non-zero exit code is a failure unless `ExpectedFailure=true`.

For `stdin` mode, the input file is opened and passed as `stdin`; the file handle is closed in a `finally` block. For `argument` and `rename` modes, the copied input file is deleted from the work directory after execution to avoid polluting match checks.

## Comparison and tolerance behavior

`match_compare_result` dispatches on whether both values are numeric:

- **Numeric**: `abs(float(calculated) - float(reference)) <= tol` (or `== 0.0` if no `tol`).
- **String**: `str(calculated) == str(reference)`.

Special float strings (`nan`, `inf`, `-inf`, `+inf`) are recognised as numeric.

Fortran-style `D`/`d` exponent notation (e.g. `1.23D-04`) is normalised to `e` before parsing by `get_precision_from_string_format`.

When `tol` is set and the effective precision implied by the string format of the calculated value is coarser than `tol`, a `WARNING` log is emitted. For example, a value printed as `1.234` has precision `0.001`; setting `tol: 1e-6` would trigger this warning because the output cannot distinguish differences smaller than `0.001`.

## Config updater internals

`apply_match_updates(match_def, results, total, mode)` iterates over broadcast results and patches the raw ruamel.yaml dict in-place:

**Tolerance mode** (`_update_tolerance`):
1. Computes `compute_tolerance(|calculated - reference|)`.
2. If `total > 1` (broadcast), ensures `tol` in `match_def` is a list of length `total`, then sets the element at the failing index.
3. If `total == 1`, sets `tol` directly.

**Reference mode** (`_update_reference`):
1. Identifies the reference key (the first key in `REFERENCE_KEYS` present in `match_def`).
2. Calls `_cast_to_reference_type(calculated_value, original_ref)` to match the original Python/YAML type.
3. For `ScalarFloat`, uses `_make_scalar_float` to preserve decimal precision from the original template.

Type mapping:

| ruamel.yaml type | Python cast |
|---|---|
| `ScalarFloat` | `float` (with decimal precision preserved) |
| `ScalarInt` | `int` |
| `ScalarBoolean` | `bool` |
| anything else | same type as reference, fallback to string |

## Report format internals

`ReportWriter.write(path, data)` serialises a nested dict to YAML using `ruamel.yaml` in block style. If the file already exists, the new document is appended with a `---` separator (standard YAML multi-document format).

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

`build_match_entry` constructs one entry per match with:
- all non-internal params from the match definition
- the original reference value under the `reference` key
- the calculated value under the `"<reference_key>"` defined in the corresponding match handler.

Keys in `INTERNAL_KEYS` (currently just `match`) are excluded.

## Error handling and exit codes

Defined in `exceptions.py`:

| Code | Constant | Meaning |
|---|---|---|
| `0` | `ExitCode.OK` | All tests passed |
| `1` | `ExitCode.TEST_FAILURE` | One or more tests/matches failed |
| `2` | `ExitCode.USAGE` | Bad configuration or command-line usage |
| `3` | `ExitCode.RUNTIME` | Runtime error during execution |
| `99` | `ExitCode.INTERNAL` | Unexpected internal error |

`CliError` is the base class for user-facing errors; `UsageError` is its subclass for configuration errors. Both carry an `exit_code` attribute. CLI entry points catch `CliError` (returns attached code) and bare `Exception` (returns `INTERNAL`).

## Testing strategy

- **Unit tests** target isolated modules: extractors, matchers, comparator, executor, updater, formatting, report.
- **Integration tests** (`test_integration.py`) build self-contained workspaces with mock executables written in Python (so they run on any platform), input files, and YAML configs. They call `main()` directly and assert exit codes plus YAML side-effects.
- `conftest.py` provides factory fixtures: `make_executable`, `make_input`, `make_yaml`, `run_pseudotest`, `run_update`.

Prefer adding tests close to the changed behavior. For a new match handler, add:

1. Unit test in `test_matchers.py` covering successful extraction, extraction failure (`None`), and any `UsageError` paths.
2. Integration test in `test_integration.py` using a mock executable that writes the expected output format.

## Contribution checklist

1. Keep API and YAML behavior backward-compatible unless intentionally versioned.
2. Add or update tests for new logic and edge cases.
3. Run `pytest` and `ruff check .`.
4. Update the user guide and README for any user-facing behavior changes.
5. Keep match, update, and report semantics consistent. A new reference key must be added to `REFERENCE_KEYS` for update and report to handle it correctly.

## Documentation with MkDocs

```bash
pip install -e .[docs]
zensical serve      # live-reload preview at http://127.0.0.1:8000
zensical build      # build static site to _site/
```

Navigation is defined in `mkdocs.yml`.
