# Reference

This page lists every key of a test file, every match parameter, the command-line options, the exit codes and the
report format. The [User Guide](user-guide.md) explains how to use them.

## Test file keys

Keys marked *both* can be set at the top level, as a default for every input, or in an input, for that input only.

| Key | Where | Type | Default | Description |
|---|---|---|---|---|
| `Name` | top | string | required | Name of the test, printed as a header and written to the report |
| `Enabled` | top | bool | `true` | `false` skips the whole test file, which then passes |
| `Inputs` | top | mapping | required | Input files, relative to the directory of the test file, each with its parameters (which may be empty). They run in the order they are listed |
| `Executable` | both | string | required | Executable looked up in the `-D/--directory` directory; an absolute path is used as is |
| `InputMethod` | both | `argument`, `stdin` or `rename` | `argument` | How the executable receives the input file, see [Input methods](#input-methods) |
| `RenameTo` | both | string | — | Name the input file is copied to; required with `InputMethod: rename` |
| `ExtraFiles` | both | list of strings | `[]` | Files, relative to the directory of the test file, copied into the working directory before the input runs |
| `Processors` | both | int | `1` | Number of MPI processes; used only when `MPIEXEC` is set |
| `ExpectedFailure` | both | bool | `false` | `true` when the executable must fail (non-zero exit code); a successful run is then a failure |
| `Matches` | both | mapping | none | Checks of the outputs, see [Match parameters](#match-parameters). The `Matches` of an input replace the top-level ones as a whole |

### Input methods

| `InputMethod` | Command run in the working directory |
|---|---|
| `argument` | `solver.x case_01.in` |
| `stdin` | `solver.x < case_01.in` |
| `rename` | `solver.x`, with the input copied to the `RenameTo` name |

With `MPIEXEC` set, the command is prefixed by the launcher, see [Environment variables](#environment-variables).

## Match parameters

A match whose value contains other matches is a *group*: its parameters are inherited by all the matches it contains,
which can override them. Any other match is a *leaf* and is evaluated; it can only contain the parameters below.

| Parameter | Used by | Description |
|---|---|---|
| `file` | file and content matches | File to check, relative to the working directory, e.g. `results.txt` or `stdout` |
| `directory` | directory matches | Directory to check, relative to the working directory |
| `grep` | content matches | Text to search for (case-sensitive substring); the first line containing it is selected |
| `line` | content matches | Without `grep`: 1-based line number, or counted from the end when negative (`-1` is the last line); `0` is an error. With `grep`: offset from the line found by `grep` (`0` is that line, `1` the next one, `-1` the previous one) |
| `field` | content matches | 1-based field of the selected line; fields are separated by whitespace or commas |
| `column` | content matches | 1-based character position in the selected line; the first token from there is extracted |
| `field_re`, `field_im` | content matches | Fields holding the real and imaginary parts of a complex number, whose magnitude `sqrt(re² + im²)` is compared |
| `value` | content matches | Reference value, a number or a string |
| `count` | content matches with `grep` | Reference number of lines containing `grep` |
| `size` | file matches | Reference size of the file, in bytes |
| `count_files` | directory matches | Reference number of files directly in the directory (subdirectories are not counted) |
| `file_is_present` | directory matches | Name of a file that must be in the directory |
| `tol` | numeric comparisons | Absolute tolerance: the match passes when `abs(calculated - reference) <= tol` |
| `protected` | all matches | `true` prevents `pseudotest-update` from changing the match |
| `match` | broadcast matches | List of names of the broadcast elements |

Any parameter can be given a list of values instead of a single value. The match is then *broadcast*: it is evaluated
once per element, and all the lists must have the same length. The elements are named after the `match` list, or
`name[0]`, `name[1]`, ... without one.

### How a match is evaluated

1. With `directory`, a directory match: `file_is_present` if present, otherwise `count_files`.
2. With `file` and `size`, a file size match.
3. With `file`, a content match: with both `grep` and `count`, the lines containing `grep` are counted. Otherwise a
   line is selected with `grep` and/or `line`, and a value is extracted from it with `field`, `column`, or
   `field_re`/`field_im`, in this order of precedence. It is compared with `value`.

A match fails when its value cannot be extracted: the file or directory does not exist, `grep` is not found, or the
line, field or column is out of range. The output gives the reason.

### Comparison

- When both the calculated and the reference values are numbers, they are compared numerically. Numbers include
  `inf`, `nan` and Fortran exponents such as `1.5D+00`; equal infinities match, and so do two `nan`s.
- Without `tol`, numbers must be equal. With `tol`, the tolerance must not be smaller than the precision of the
  calculated value as printed (`0.01` for `1.23`, `1e-6` for `1.234567E+00`), otherwise the match fails as an
  unreliable comparison. A zero printed in scientific notation, `inf` and `nan` are exact.
- Otherwise, the values are compared as strings.

### Reference values and updates

| Reference parameter | Match type | `pseudotest-update -t` | `pseudotest-update -r`/`-R` |
|---|---|---|---|
| `value` | content | sets `tol` when numeric | replaces `value` |
| `count` | content | sets `tol` | replaces `count` |
| `size` | file | sets `tol` | replaces `size` |
| `count_files` | directory | sets `tol` | replaces `count_files` |
| `file_is_present` | directory | never | never |

`pseudotest-update` never changes a match that is `protected` (also when inherited from a group), a match whose value
could not be extracted, or a numeric reference that the calculated value would replace with text, such as a Fortran
overflow `***`.

## Command line

### `pseudotest`

```bash
pseudotest TEST_FILE [-D DIRECTORY] [-p] [-t TIMEOUT] [-r FILE] [-v | -vv]
```

`python -m pseudotest` runs the same command.

| Option | Default | Description |
|---|---|---|
| `TEST_FILE` | — | YAML test file to run |
| `-D, --directory DIRECTORY` | `.` | Directory containing the executables |
| `-p, --preserve` | off | Keep the working directory after the run |
| `-t, --timeout TIMEOUT` | `600` | Timeout of each input, in seconds |
| `-r, --report FILE` | — | Append a YAML report of the run to `FILE` |
| `-v`, `-vv` | — | Show INFO or DEBUG messages; `-vv` also shows the full output of failed executions and the traceback of errors |
| `-V, --version` | — | Show the version and exit |

### `pseudotest-update`

```bash
pseudotest-update TEST_FILE (-t | -r | -R) [-D DIRECTORY] [-o FILE] [-p] [--timeout TIMEOUT] [--report FILE] [-v | -vv]
```

| Option | Default | Description |
|---|---|---|
| `TEST_FILE` | — | YAML test file to run and update |
| `-t, --tolerance` | — | Set the tolerances of failing numeric matches so that they pass |
| `-r, --reference` | — | Replace the reference values of failing matches with the calculated values |
| `-R, --reference-all` | — | Replace the reference values of all matches, passing or failing, with the calculated values |
| `-D, --directory DIRECTORY` | `.` | Directory containing the executables |
| `-o, --output FILE` | — | Write the updated test file to `FILE` instead of overwriting `TEST_FILE` |
| `-p, --preserve` | off | Keep the working directory after the run |
| `--timeout TIMEOUT` | `600` | Timeout of each input, in seconds |
| `--report FILE` | — | Append a YAML report of the run to `FILE` |
| `-v`, `-vv`, `-V` | — | As for `pseudotest` |

Exactly one of `-t`, `-r` and `-R` must be given. As they select the update mode, the timeout and the report only have
long options, `--timeout` and `--report`, which are `-t` and `-r` for `pseudotest`.

## Environment variables

| Variable | Description |
|---|---|
| `MPIEXEC` | MPI launcher prefixed to every command, with the number of processes set by `Processors`. It can include options of the launcher, e.g. `mpirun --oversubscribe` |
| `TMPDIR` | Directory in which the working directories are created |

The flag giving the number of processes depends on the launcher:

| Launcher | Flag |
|---|---|
| `mpiexec`, `mpirun`, `mpiexec.hydra`, `orterun` | `-np` |
| `srun` (SLURM) | `-n` |
| `aprun` (Cray) | `-n` |
| any other | `-np` |

## Exit codes

| Code | Meaning |
|---|---|
| `0` | All executions and matches passed, or the test is disabled |
| `1` | At least one execution or match failed |
| `2` | Usage error: invalid command line, test file missing or invalid, executable, input or extra file missing |
| `3` | Runtime error (reserved, not used yet) |
| `99` | Internal error, i.e. a bug in pseudotest; use `-vv` to see the traceback |

## Report

With `--report FILE`, each run appends one YAML document to `FILE`:

```yaml
---
tests/solver.yaml:
  Name: Solver regression suite
  Enabled: true
  Executable: solver.x
  Inputs:
    case_01.in:
      InputMethod: argument
      Processors: 4
      ExpectedFailure: false
      Execution: pass
      Elapsed time: 3.142
      Matches:
        Total Energy:
          file: results.txt
          grep: 'Total energy:'
          field: 3
          value: -42.5001
          reference: -42.5000
          tol: 0.0001
          status: pass
        Band Gap:
          file: bands.txt
          grep: Band gap
          column: 21
          value:
          reference: 1.0342
          status: fail
          reason: "'Band gap' not found in 'bands.txt'"
```

- The document is keyed by the test file as given on the command line, without a leading `./`.
- `Execution` is `pass` or `fail`, after taking `ExpectedFailure` into account. `Matches` is absent when the
  execution failed.
- Each match lists its parameters, in their order with the inherited ones first. The reference parameter (`value`
  above) holds the calculated value, empty when none could be extracted, and `reference` the reference value. Then
  come the `status` of the match, `pass` or `fail`, and the `reason` of a failure. Groups are nested mappings, and
  broadcast elements appear under their own names.
- A disabled test has `Enabled: false` and no inputs.

## Public API

From version 1.0.0, `pseudotest` follows [semantic versioning](https://semver.org/): a change that is not backward
compatible needs a new major version. Its public API is:

- the command-line tools `pseudotest` and `pseudotest-update` (also `python -m pseudotest`), with their options and
  exit codes;
- the format of the test files, and the match parameters;
- the format of the reports;
- the Python names exported by the `pseudotest` package: `PseudoTestRunner`, `RunSummary`, `MatchResult`,
  `UpdateMode`, `Colors`, `ReportWriter`, `main` and `update_main`, and, for new match types,
  `register_match_handler` and `ExtractionError`.

The modules of the package and everything they contain are internal, except for these names, and can change in any
release. The texts of the messages are not part of the API either.

## Python API

```python
from pseudotest import PseudoTestRunner

runner = PseudoTestRunner()
summary = runner.run(
    test_file_path="test.yaml",
    executable_directory="./bin",
    preserve_workdir=False,
    timeout=600,
    report_file="report.yaml",  # optional
    update_mode=None,  # None, or an UpdateMode, e.g. UpdateMode.TOLERANCE, or its value, e.g. "tolerance"
    update_output=None,  # optional path for the updated test file
)

print(summary.failed_matches, "of", summary.total_matches, "matches failed")
for result in summary.match_results:
    if not result.passed:
        print(result.name, result.calculated, result.reference, result.reason)
```

`run()` returns a `RunSummary`:

| Attribute | Description |
|---|---|
| `name`, `enabled` | Name of the test, and whether it is enabled; a disabled test is not run |
| `failed_executions` | Number of inputs whose execution failed |
| `match_results` | `MatchResult` of each evaluated match, in order: `name`, `passed`, `status`, `calculated`, `reference`, `reference_key`, `tolerance`, `difference`, `precision` and `reason` |
| `total_matches`, `failed_matches` | Numbers of evaluated and of failed matches |
| `passed`, `exit_code` | Whether all executions and matches passed, and the corresponding exit code, `0` or `1` |
| `updated_file` | Test file written by an update, if any |

`RunSummary`, `MatchResult` and `UpdateMode` can be imported from `pseudotest`. `PseudoTestRunner(colors=...)` takes
a `pseudotest.Colors`, used for all the output; by default, colours are used when the output is a terminal.

The update modes are `UpdateMode.TOLERANCE`, `UpdateMode.REFERENCE` and `UpdateMode.REFERENCE_ALL`, or their
values `"tolerance"`, `"reference"` and `"reference_all"`, as for `-t`, `-r` and
`-R`. `run()` raises `pseudotest.exceptions.UsageError` for the usage errors listed above; the command-line tools turn
it into exit code 2.
