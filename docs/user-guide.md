# User Guide

This guide explains how to write and run `pseudotest` regression tests in day-to-day workflows.

## What pseudotest does

`pseudotest` runs your executable in an isolated temporary working directory for each input case, then compares generated outputs against expected references defined in YAML.

Each test run:

1. Reads a YAML config file.
2. For every listed input file, copies the input (and any extra files) into a fresh temporary directory.
3. Executes the program inside that directory.
4. Checks specified outputs against reference values.
5. Reports pass/fail and exits with a status code.

Typical use cases:

- Regression testing of scientific codes after refactors or optimisation passes
- Verifying numeric outputs, log patterns, file sizes, and directory contents
- CI checks for numerical stability and expected failures
- Baseline capture with `pseudotest-update` after intentional changes

## Install

### Using pip

You can install the latest release directly from PyPI:

```bash
pip install access-profiling
```

### From source

From a local clone:

```bash
pip install -e .
```

With optional test/developer extras:

```bash
pip install -e .[test,devel]
```

## Quick start

1. Create a YAML config file (for example `test.yaml`).
2. Ensure your target executable is in a directory (for example `./bin`).
3. Run:

```bash
pseudotest test.yaml -D ./bin
```

The command returns:

- `0` when all executions and matches pass
- `1` when any execution or match fails
- `2` on a configuration/usage error
- `3` on a runtime error

## Configuration model

### Top-level keys

| Key | Required | Description |
|---|---|---|
| `Name` | Yes | Human-readable test suite name |
| `Enabled` | No | If `false`, test is skipped (default: `true`) |
| `Executable` | Yes | Executable filename looked up in `-D/--directory` |
| `InputMethod` | No | `argument`, `stdin`, or `rename` (default: `argument`) |
| `RenameTo` | Conditional | Required if `InputMethod: rename` |
| `Inputs` | Yes | Mapping of input filename to per-input config |

### Per-input keys

| Key | Required | Description |
|---|---|---|
| `ExtraFiles` | No | List of additional files to copy into work dir |
| `Processors` | No | Number of MPI processes when `MPIEXEC` is set (default: `1`) |
| `ExpectedFailure` | No | If `true`, execution failure is treated as pass |
| `InputMethod` | No | Overrides the top-level `InputMethod` for this input only |
| `RenameTo` | Conditional | Overrides the top-level `RenameTo` for this input only |
| `Matches` | No | Mapping of named checks |

Top-level keys (`Executable`, `InputMethod`, `RenameTo`) act as defaults and can be overridden per input.

### ExtraFiles resolution

Paths in `ExtraFiles` are resolved relative to the directory containing the YAML test file. All files are copied flat into the temporary working directory before the executable runs.

## Complete example

This example covers the most common match types in a single config:

```yaml
Name: Solver regression suite
Enabled: true
Executable: solver.x
InputMethod: argument

Inputs:
  case_01.in:
    ExtraFiles: [basis.dat, pseudo.UPF]
    Processors: 4
    Matches:

      # Extract a field by searching for a keyword
      Total Energy:
        file: results.txt
        grep: "Total energy:"
        field: 3
        value: -42.5000
        tol: 1e-4

      # Read from a specific line number (1-based)
      Convergence Flag:
        file: results.txt
        line: 5
        field: 2
        value: converged

      # Count occurrences of a pattern
      Warning count:
        file: run.log
        grep: WARNING
        count: 0

      # Fixed-width column extraction
      Band Gap:
        file: bands.txt
        grep: "Band gap"
        column: 20
        value: 1.0342
        tol: 1e-3

      # Complex number magnitude
      Wavefunction magnitude:
        file: wf.txt
        grep: "Value:"
        field_re: 2
        field_im: 3
        value: 3.1416
        tol: 1e-4

      # File size check
      Restart File:
        file: restart.bin
        size: 65536

      # Directory checks
      Output directory count:
        directory: output
        count_files: 3

      Output summary:
        directory: output
        file_is_present: summary.txt

  # A case expected to fail (used for negative testing)
  bad_input.in:
    ExpectedFailure: true
Convergence:
  file: output.txt
  line: 3
  field: 2
  value: converged
```

Negative `line` values count from the end of the file (`line: -1` is the last line):

```yaml
Final Status:
  file: output.txt
  line: -1
  field: 1
  value: DONE
```

**Offsetting from a `grep` match**

When both `grep` and `line` are present, `line` is treated as an offset from the matched line (0 = same line, 1 = next line, etc.). This is useful when the value appears on the line after a header:

```yaml
Force after header:
  file: results.txt
  grep: "Forces (Ha/Bohr):"
  line: 1
  field: 2
  value: -0.00123
  tol: 1e-5
```

Given:

```
Forces (Ha/Bohr):
  Atom 1   -0.00124   0.00000   0.00000
```

`grep` finds `"Forces (Ha/Bohr):"` and `line: 1` steps to the next line, then `field: 2` extracts `-0.00124`.

**Extracting by whitespace-separated field**

`field` is 1-based and equivalent to `awk '{print $N}'`:

```yaml
Pressure:
  file: output.txt
  grep: "Pressure:"
  field: 2    # second whitespace token
  value: 101.325
  tol: 0.01
```

**Extracting by character column**

`column` extracts from a fixed character position (1-based), then takes the first whitespace-delimited token. This is useful for fixed-width formatted output:

```yaml
# Output line: "Band gap (eV)       1.0342  direct"
#              123456789012345678901234567890
#                                  ^ column 21
Band Gap:
  file: bands.txt
  grep: "Band gap"
  column: 21
  value: 1.0342
  tol: 1e-3
```

**Complex number magnitude**

When output contains a complex number as two separate fields, `field_re` and `field_im` extract the real and imaginary parts and compare their magnitude (`sqrt(re² + im²)`) to `value`:

```yaml
# Output line: "Wavefunction:  2.2214  2.2214"
Wavefunction magnitude:
  file: evals.txt
  grep: "Wavefunction:"
  field_re: 2   # field holding the real part
  field_im: 3   # field holding the imaginary part
  value: 3.1416
  tol: 1e-4
```

**Counting matching lines**

When `count` is used instead of a value-extraction key, `pseudotest` counts all lines containing the `grep` pattern. The `count` check takes precedence over `field`/`column`/`field_re`/`field_im` if both are present.

```yaml
No warnings:
  file: run.log
  grep: "WARNING"
  count: 0

Error count:
  file: run.log
  grep: "ERROR"
  count: 2
```

**Numeric tolerance**

`tol` is an absolute tolerance applied when both the extracted value and the reference are numeric:

```yaml
energy:
  file: results.txt
  grep: "Energy:"
  field: 2
  value: -42.5000
  tol: 1e-4      # pass if |calculated - reference| <= 1e-4
```

Without `tol`, numeric values must match exactly (difference == 0). String values always require exact equality regardless of `tol`.

If the specified `tol` is smaller than the effective precision implied by the format of the extracted value (e.g. `tol: 1e-8` for a value printed as `1.234`), a warning is emitted suggesting a larger tolerance.

### File metadata match

Compare a file's size in bytes:

```yaml
Restart size:
  file: restart.bin
  size: 65536
```

### Directory matches

**File presence**: assert that a specific file exists inside a directory:

```yaml
Has summary:
  directory: output
  file_is_present: summary.txt
```

**File count**: count files directly inside a directory (subdirectories are not counted):

```yaml
Output count:
  directory: output
  count_files: 5
```

If the directory does not exist, both directory matches fail.

## Broadcasted matches (vector-style checks)

When any parameter value in a match is a list, `pseudotest` expands that match into one logical sub-match per list element. All list-valued parameters in the same match must have equal length; scalar parameters are reused for every element.

```yaml
multi_energy:
  matches: [R1, R2, R3]
  file: [r1.txt, r2.txt, r3.txt]
  grep: "Energy:"
  field: 2
  value: [-10.0, -20.0, -30.0]
  tol: 1e-6      # scalar: same tolerance applied to all three
```

This is equivalent to writing three separate named matches, with names "R1", "R2", and "R3". Any element that fails is reported individually.

Broadcast works with any match type:

```yaml
# Check the same field across multiple files
band_gaps:
  matches: [Case1, Case2]
  file: [case1/bands.txt, case2/bands.txt]
  grep: "Band gap"
  field: 3
  value: [1.1, 2.3]
  tol: [0.01, 0.01]

# Check file presence across multiple directories
Checkpoint directories:
  matches: [run1, run2]
  directory: [run1/output, run2/output]
  count_files: [4, 6]
```

## Running tests

```bash
pseudotest test.yaml -D ./bin
```

### Options

| Flag | Description |
|---|---|
| `-D, --directory DIR` | Directory containing executables (default: `.`) |
| `-p, --preserve` | Keep temporary work directory after the run for debugging |
| `-t, --timeout N` | Per-input execution timeout in seconds (default: `600`) |
| `-r, --report FILE` | Append a YAML execution report to `FILE` |
| `-v` / `-vv` | Increase logging verbosity (INFO / DEBUG) |

### Inspecting failures

Add `-p` to retain the working directory after a failed run, then inspect generated files:

```bash
pseudotest test.yaml -D ./bin -p
# The temporary directory path is printed in the output
```

Use `-vv` to see the full stdout/stderr of the executable on failure, and to trace match evaluation in detail.

## Updating failing configs

`pseudotest-update` re-runs the test suite and automatically patches the YAML config for failing matches. Two modes are available.

### Update tolerances

```bash
pseudotest-update test.yaml -D ./bin --tolerance
```

For each failing numeric match, computes `|calculated - reference| × 1.1` rounded up to two significant figures and writes that value as `tol`. Reference values are not changed.

Example: if the observed difference is `0.0034`, the written tolerance is `0.0038`.

### Update reference values

```bash
pseudotest-update test.yaml -D ./bin --reference
```

Replaces each failing reference value with the observed calculated value. Tolerances are not changed. The replacement is type-preserving: a `ScalarFloat` reference retains its original decimal precision.

### Write to a different file

```bash
pseudotest-update test.yaml -D ./bin --reference --output updated.yaml
```

The original file is left untouched; changes are written to `updated.yaml`.

### Protecting matches from updates

Add `protected: true` to any match that must never be modified automatically:

```yaml
Critical Reference:
  file: results.txt
  grep: "Final value"
  field: 3
  value: 123.45
  protected: true
```

This is useful for cases where the references are obtained through some other method (e.g., theorical values). 

Note that `file_is_present` checks are never updated automatically regardless of the `protected` flag.

### Broadcast and tolerance updates

When a tolerance update applies to a broadcasted match, the scalar `tol` is automatically expanded to a list of the correct length, and only the failing elements are changed:

```yaml
# Before update (two values, one failing)
multi:
  file: [r1.txt, r2.txt]
  value: [1.0, 2.0]
  tol: 1e-6

# After --tolerance update (only the second element was failing)
multi:
  file: [r1.txt, r2.txt]
  value: [1.0, 2.0]
  tol: [1e-6, 5.5e-4]
```

## MPI execution

Set `MPIEXEC` to your MPI launcher to enable parallel execution:

```bash
MPIEXEC=mpiexec pseudotest test.yaml -D ./bin
```

The launcher is prepended automatically and the per-input `Processors` key controls the process count:

```
mpiexec -np 4 solver.x case_01.in
```

Supported launchers and their process-count flag:

| Launcher | Flag |
|---|---|
| `mpiexec`, `mpirun`, `mpiexec.hydra`, `orterun` | `-np` |
| `srun` (SLURM) | `-n` |
| `aprun` (Cray) | `-n` |
| any other | `-np` (default) |

Different inputs can use different process counts:

```yaml
Inputs:
  small.in:
    Processors: 1
    Matches: ...
  large.in:
    Processors: 16
    Matches: ...
```

When `MPIEXEC` is not set, `Processors` has no effect and the executable is run directly.

## YAML report output

Pass `--report FILE` to append a YAML document with per-run results:

```bash
pseudotest test.yaml -D ./bin --report results.yaml
```

If `results.yaml` already exists, the new document is appended with a `---` separator (multi-document YAML).

Report structure:

```yaml
test.yaml:
  Name: Solver regression suite
  Enabled: true
  Executable: solver.x
  Inputs:
    case_01.in:
      InputMethod: argument
      Processors: 4
      ExpectedFailure: false
      Execution: pass
      Elapsed time: 3.14
      Matches:
        total_energy:
          file: results.txt
          grep: "Total energy:"
          field: 3
          reference: -42.5000  # original reference
          value: -42.5001      # calculated value
```

This output can be useful as a CI artifact or for further processing.

## Troubleshooting

### Executable not found

- Verify that `Executable` in the YAML matches the actual filename.
- Check that the path given to `-D` contains the executable.
- Confirm the executable has the execute bit set (`chmod +x`).

### Match extraction returns `None` / match fails with no detail

- Use `-p` to keep the work directory and open the target file directly.
- Check that `grep` matches a line that actually exists.
- Check that `field` or `column` index is within range for that line.
- If the file is empty or missing, the match will always fail.

### Tolerance warning

A warning like *"Tolerance 1e-8 is smaller than the effective precision 1e-4"* means the printed value has fewer significant digits than the tolerance requires. Either reduce the tolerance or print more digits.

### Timeout failures

- Increase `--timeout`.
- Add `-vv` to see if the executable starts at all.
- Verify MPI settings and that the launcher is available.

### Unexpected update behavior

- Matches with `protected: true` are never modified.
- `file_is_present` checks are never reference-updated.
- Only failing matches are updated; passing ones are left alone.
