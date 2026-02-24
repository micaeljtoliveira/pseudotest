# pseudotest

`pseudotest` is a YAML-driven regression testing framework for scientific software.

It runs one executable against one or more input files in an isolated temporary directory, then validates outputs with flexible file/content/directory match rules.

## Highlights

- YAML test definitions for reproducible regression checks
- Per-input execution settings (`InputMethod`, `Processors`, `ExpectedFailure`, `ExtraFiles`)
- Built-in content extraction: `grep`, `line`, `field`, `column`, `field_re`/`field_im` (complex magnitude)
- File and directory based checks: `size`, `count_files`, `file_is_present`
- Numeric and string comparisons with optional tolerance (`tol`)
- Vector-style broadcasted matches for concise match definition
- CLI for running tests and for updating failing references or tolerances in-place
- Optional YAML report output for CI artifacts
- MPI support via `MPIEXEC` environment variable

## Installation

### From PyPI

```bash
pip install pseudotest
```

### From source

```bash
git clone <repo-url>
cd pseudotest
pip install -e .
```

### Optional dependencies

```bash
pip install -e .[devel,test]   # ruff, pre-commit, pytest, pytest-mock, pytest-cov
pip install -e .[docs]         # mkdocs
```

## Command-line usage

Two entry points are installed:

- `pseudotest` — run tests from a YAML file
- `pseudotest-update` — run tests and update failing config entries in-place

### Run regression tests

```bash
pseudotest test.yaml -D /path/to/executables
```

| Option | Default | Description |
|---|---|---|
| `-D, --directory DIR` | `.` | Directory containing executables |
| `-p, --preserve` | off | Keep temporary working directory after run |
| `-v` / `-vv` | off | Logging verbosity (INFO / DEBUG) |
| `-t, --timeout N` | `600` | Per-input execution timeout in seconds |
| `-r, --report FILE` | — | Append YAML report document to FILE |

### Update failing tests

```bash
# Increase tolerances to cover observed deltas
pseudotest-update test.yaml -D ./bin --tolerance

# Replace reference values with observed values
pseudotest-update test.yaml -D ./bin --reference

# Write the updated config to a separate file
pseudotest-update test.yaml -D ./bin --reference --output updated.yaml
```

| Option | Description |
|---|---|
| `-t, --tolerance` | Compute and set `tol` for failing numeric matches |
| `-r, --reference` | Replace reference values with observed values |
| `-o, --output FILE` | Write changes to FILE instead of overwriting the original |
| `--timeout N` | Per-input execution timeout in seconds |

## YAML test format

### Minimal example

```yaml
Name: My regression test
Executable: solver.x

Inputs:
  case_01.in:
    Matches:
      total_energy:
        file: output.txt
        grep: "Energy:"
        field: 2
        value: -42.5000
        tol: 1e-4
```

### Full schema

```yaml
Name: My regression test        # required
Enabled: true                   # set to false to skip the entire suite
Executable: solver.x            # filename looked up in -D/--directory
InputMethod: argument           # argument | stdin | rename  (default: argument)
RenameTo: input.dat             # required when InputMethod: rename

Inputs:
  case_01.in:
    ExtraFiles: [basis.dat, pseudo.UPF]  # copied into work dir before execution
    Processors: 4               # MPI process count (requires MPIEXEC env var)
    ExpectedFailure: false      # true = non-zero exit code is treated as pass
    InputMethod: argument       # overrides top-level InputMethod for this input
    Matches:
      <match_name>: ...
```

### Input methods

| Mode | Execution shape |
|---|---|
| `argument` (default) | `solver.x case_01.in` |
| `stdin` | `solver.x < case_01.in` |
| `rename` | Copy input as `RenameTo`, then run `solver.x` |

### Match types

#### Extract a field from a line found by keyword

```yaml
Energy:
  file: results.txt
  grep: "Total energy:"   # find first line containing this substring
  field: 3                # extract the 3rd whitespace-separated token (1-based)
  value: -42.5000
  tol: 1e-4
```

#### Extract a field from a specific line number

```yaml
Status:
  file: output.txt
  line: 5       # 1-based; negative values count from the end (line: -1 = last line)
  field: 2
  value: converged
```

#### Extract from the line after a keyword

When both `grep` and `line` are present, `line` is an offset from the matched line (0 = same, 1 = next):

```yaml
Force:
  file: results.txt
  grep: "Forces (Ha/Bohr):"
  line: 1       # one line after the match
  field: 2
  value: -0.00123
  tol: 1e-5
```

#### Extract by character column (fixed-width output)

```yaml
Band Gap:
  file: bands.txt
  grep: "Band gap"
  column: 21    # start at character 21 (1-based), take first token
  value: 1.0342
  tol: 1e-3
```

#### Count matching lines

```yaml
Warnings:
  file: run.log
  grep: "WARNING"
  count: 0      # assert no lines contain "WARNING"
```

#### Complex number magnitude

Extracts two fields and compares `sqrt(re² + im²)` to `value`:

```yaml
eigenvalue:
  file: evals.txt
  grep: "Eigenvalue:"
  field_re: 2   # field holding the real part
  field_im: 3   # field holding the imaginary part
  value: 3.1416
  tol: 1e-4
```

#### File size

```yaml
restart:
  file: restart.bin
  size: 65536
```

#### Directory checks

```yaml
dir_count:
  directory: output
  count_files: 5

dir_has_file:
  directory: output
  file_is_present: summary.txt
```

#### Broadcast (vector checks)

List values expand a single match into one sub-check per element. All list parameters must have equal length; scalars are reused:

```yaml
multi_energy:
  matches: ["Run1", "Run2"]
  file: [run1/out.txt, run2/out.txt]
  grep: "Energy:"
  field: 2
  value: [-10.0, -20.0]
  tol: 1e-6     # scalar: applies to both elements
```

`matches` is optional and names each match in the list.

#### Protecting a match from automatic updates

```yaml
critical:
  file: results.txt
  grep: "Final value"
  field: 3
  value: 123.45
  protected: true   # pseudotest-update will never modify this match
```

## MPI support

Set `MPIEXEC` to your MPI launcher to enable parallel execution:

```bash
MPIEXEC=mpiexec pseudotest test.yaml -D ./bin
```

`Processors` in each input controls the process count. Supported launchers:

| Launcher | Process-count flag |
|---|---|
| `mpiexec`, `mpirun`, `mpiexec.hydra`, `orterun` | `-np` |
| `srun` (SLURM) | `-n` |
| `aprun` (Cray) | `-n` |

## Python API

```python
from pseudotest import PseudoTestRunner

runner = PseudoTestRunner()
exit_code = runner.run(
    test_file_path="test.yaml",
    executable_directory="./bin",
    preserve_workdir=False,
    timeout=600,
    report_file="report.yaml",     # optional
    update_mode=None,               # "tolerance" | "reference" | None
    update_output=None,             # optional path for updated config
)
```

## Exit codes

| Code | Meaning |
|---|---|
| `0` | All tests passed |
| `1` | One or more executions or matches failed |
| `2` | Configuration or usage error |
| `3` | Runtime error |
| `99` | Internal/unexpected error |

## Documentation

Detailed MkDocs-ready guides are in `docs/`:

- `docs/user-guide.md` — full feature reference with examples
- `docs/developer-guide.md` — architecture, adding match types, internals

Run locally:

```bash
pip install -e .[docs]
zensical serve
```

## License

Mozilla Public License 2.0 (MPL-2.0)
