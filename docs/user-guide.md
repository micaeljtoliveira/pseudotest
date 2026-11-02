# User Guide

This guide explains how to write and run `pseudotest` regression tests. The [Reference](reference.md) lists every
key, option and exit code.

## What pseudotest does

`pseudotest` runs an executable on one or more input files and compares what it writes against reference values
stored in a YAML test file. Each run:

1. Reads the YAML test file.
2. Creates a temporary working directory.
3. For each input, in the order they are listed: copies the input file (and any extra files) into the working
   directory, runs the executable there, and checks the outputs against the reference values.
4. Prints a summary, removes the working directory, and exits with a status code.

Typical uses:

- Regression testing of scientific codes after refactors or optimisations
- Checking numeric outputs, log messages, file sizes and directory contents
- CI checks of numerical stability and of expected failures
- Updating references with `pseudotest-update` after an intended change

## Install

Install the latest release from PyPI:

```bash
pip install pseudotest
```

or, from a clone of the repository:

```bash
pip install -e .
```

## Quick start

Write a test file, `test.yaml`:

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

This runs `solver.x case_01.in`, finds the first line of `output.txt` containing `Energy:`, and checks that its
second field is `-42.5000` within `1e-4`. With `solver.x` in `./bin`:

```console
$ pseudotest test.yaml -D ./bin
***** My regression test *****
Using workdir: /tmp/pseudotest_bljde68p
Inputs:
  case_01.in:
    Elapsed time: 0.033s
    Execution                                              [ OK ]
    Matches:
      total_energy                                         [ OK ]
Test Summary:
  Failed executions :     0
  Total matches     :     1
  Failed matches    :     0
```

The exit code is `0` when all executions and matches pass, `1` when any fails, and `2` when the test file or the
command line is wrong (see [Exit codes](reference.md#exit-codes)).

## Writing a test file

A test file has a `Name`, an `Executable`, and the `Inputs` to run, each with the `Matches` that check its outputs.
Inputs can also set how the executable receives them (`InputMethod`, `RenameTo`), extra files to copy (`ExtraFiles`),
the number of MPI processes (`Processors`), and whether the executable must fail (`ExpectedFailure`). The
[Reference](reference.md#test-file-keys) describes each key.

### Execution model

- **One working directory per test file.** All the inputs of a test file run in the same temporary working
  directory, one after the other, in the order they are listed. Files written by an input are still there for the
  next ones, e.g. to restart from a previous calculation.
- **Files are copied flat.** The input file and the `ExtraFiles`, given relative to the directory of the test file,
  are copied into the working directory under their file names, without their directories.
- **The input file is removed after its run**, whatever the input method, so that it is not mistaken for an output.
- **Standard output and error** are written to the files `stdout` and `stderr` of the working directory, which each
  input overwrites. Use `file: stdout` to check the standard output.
- **Matches are checked only after a successful execution**: a zero exit code, or a non-zero one with
  `ExpectedFailure: true`.
- **The working directory is removed** at the end of the run, unless `-p/--preserve` is given.

### Input methods

The executable receives the input file as a command-line argument (`InputMethod: argument`, the default), on its
standard input (`stdin`), or under a fixed name in the working directory (`rename`, with the name given by
`RenameTo`):

```yaml
Name: Fixed input name
Executable: solver.x
InputMethod: rename
RenameTo: inp
Inputs:
  case_01.in:
    Matches: ...
  case_02.in:
    Matches: ...
```

### Avoiding repetition with scopes

Two scope mechanisms let you write shared settings once.

**Execution scope.** Any input key placed at the top level is a default for every input, which can override it. For
example, instead of repeating `InputMethod: stdin` for every input:

```yaml
Name: Solver tests
Executable: solver.x
InputMethod: stdin      # inherited by all inputs
Inputs:
  case_01.in:
    Matches: ...
  case_02.in:
    Matches: ...
  case_03.in:
    InputMethod: argument   # override for this input only
    Matches: ...
```

`Matches` can also be set at the top level, for the inputs that do not have their own. An input's `Matches`
replace the top-level ones as a whole; they are not merged.

**Match scope.** A match that contains other matches is a *group*. The match parameters placed directly in a group,
such as `file:` or `tol:`, are inherited by every match in it. Instead of repeating `file:` and `tol:`:

```yaml
Matches:
  energy:
    file: results.txt
    grep: "Total energy:"
    field: 3
    value: -42.5000
    tol: 1e-4
  force_x:
    file: results.txt
    grep: "Force x:"
    field: 2
    value: -0.00123
    tol: 1e-4
```

write them once in a group:

```yaml
Matches:
  results:              # group: shared parameters for all its matches
    file: results.txt
    tol: 1e-4
    energy:
      grep: "Total energy:"
      field: 3
      value: -42.5000
    force_x:
      grep: "Force x:"
      field: 2
      value: -0.00123
```

A match overrides an inherited parameter by defining it, and groups can be nested to any depth:

```yaml
Matches:
  results:
    file: results.txt
    energies:
      tol: 1e-6        # tighter tolerance for the energies
      total:
        grep: "Total energy:"
        field: 3
        value: -42.5000
    forces:
      tol: 1e-4        # looser tolerance for the forces
      atom_1:
        grep: "Atom 1:"
        field: 2
        value: -0.00123
    checksum:
      file: checksums.txt   # overrides the group's file
      grep: "SHA256:"
      field: 2
      value: abc123def456
```

A match is a group when it contains other matches, i.e. mappings under names that are not match parameters.
Otherwise it is a leaf, and it can only contain match parameters: a misspelled parameter such as `fiel:` is reported
as an error. For the same reason, a match cannot be named after a parameter, such as `count` or `value`.

## Match types

### Extract a field from a line found by keyword

```yaml
Energy:
  file: results.txt
  grep: "Total energy:"   # first line containing this text
  field: 3                # third field of that line (1-based)
  value: -42.5000
  tol: 1e-4
```

`field` splits the line on whitespace or commas (with optional surrounding whitespace), like `awk '{print $N}'` for
whitespace-separated output but also handling CSV-style output. Two consecutive commas give an empty field.

### Extract a field from a given line

```yaml
Status:
  file: output.txt
  line: 5       # 1-based line number
  field: 2
  value: converged
```

Negative line numbers count from the end of the file, `-1` being the last line:

```yaml
Final Status:
  file: output.txt
  line: -1
  field: 1
  value: DONE
```

`line: 0` is an error.

### Extract from a line after a keyword

When both `grep` and `line` are given, `line` is an offset from the line found by `grep` (`0` is that line, `1` the
next one). This is useful when the value follows a header:

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

`grep` finds `Forces (Ha/Bohr):`, `line: 1` steps to the next line, and `field: 2` extracts `-0.00124`.

### Extract by character column

For fixed-width output, `column` gives the 1-based position from which the first token (delimited by whitespace or
commas) is extracted:

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

### Complex number magnitude

When a complex number is written as two fields, `field_re` and `field_im` give the fields of its real and imaginary
parts, and their magnitude `sqrt(re² + im²)` is compared to `value`:

```yaml
# Output line: "Wavefunction:  2.2214  2.2214"
Wavefunction magnitude:
  file: evals.txt
  grep: "Wavefunction:"
  field_re: 2
  field_im: 3
  value: 3.1416
  tol: 1e-4
```

### Count matching lines

With `count`, the lines containing the `grep` text are counted. `count` takes precedence over `field`, `column` and
`field_re`/`field_im`.

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

### File size

```yaml
Restart size:
  file: restart.bin
  size: 65536     # bytes
```

### Directory checks

Check that a file is in a directory:

```yaml
Has summary:
  directory: output
  file_is_present: summary.txt
```

or count the files directly in a directory (subdirectories are not counted):

```yaml
Output count:
  directory: output
  count_files: 5
```

Both fail if the directory does not exist.

### Broadcast matches

When parameters of a match are lists, the match is evaluated once per element. All the lists must have the same
length, and single values are used for every element:

```yaml
multi_energy:
  match: [R1, R2, R3]          # names of the elements
  file: [r1.txt, r2.txt, r3.txt]
  grep: "Energy:"
  field: 2
  value: [-10.0, -20.0, -30.0]
  tol: 1e-6                    # same tolerance for the three elements
```

This is equivalent to three matches named `R1`, `R2` and `R3`, and each element is reported on its own. Without a
`match` list, the elements are named `multi_energy[0]`, `multi_energy[1]` and `multi_energy[2]`.

Broadcast works with any match type:

```yaml
Checkpoint directories:
  match: [run1, run2]
  directory: [run1/output, run2/output]
  count_files: [4, 6]
```

### When a value cannot be extracted

A match fails when its file or directory does not exist, when `grep` is not found, or when the line, field or column
is out of range. The output gives the reason:

```
      missing_pattern                                      [FAIL]
        ---------------------------------------------
        'Not there' not found in 'results.txt'
        ---------------------------------------------
```

Other reasons are, e.g., `'results.txt' not found`, `No line 10 in 'results.txt', which has 6 lines`, or
`No field 5 in line 'Energy: -42.5000 Ry'`.

## Comparing values

When both the calculated and the reference values are numbers, they are compared numerically; otherwise they are
compared as strings, and must be equal.

Without `tol`, numbers must be equal. `tol` is an absolute tolerance:

```yaml
energy:
  file: results.txt
  grep: "Energy:"
  field: 2
  value: -42.5000
  tol: 1e-4      # pass if |calculated - reference| <= 1e-4
```

A failed numeric comparison shows the details:

```
      total_energy                                         [FAIL]
        ---------------------------------------------
        Calculated value : -42.50003
        Reference value  : -42.4
        Difference       : 0.10003000000000384
        Deviation [%]    : 0.235920
        Tolerance        : 0.0001
        Tolerance [%]    : 0.000236
        ---------------------------------------------
```

### Tolerance and precision

A tolerance smaller than the precision of the calculated value, as printed, cannot be checked: a value printed as
`1.23` cannot resolve differences smaller than `0.01`. Such a match fails as an unreliable comparison:

```
      short                                                [FAIL]
        ---------------------------------------------
        Unreliable comparison: the tolerance is smaller than the precision of the calculated value
        Calculated value    : 1.23
        Effective precision : 0.01
        Tolerance           : 1e-06
        Use a tolerance of at least 0.01, or print the value with more digits
        ---------------------------------------------
```

Either relax the tolerance, or make the executable print more digits. A zero printed in scientific notation (e.g.
`0.00000000E+000`) is exact, so any tolerance is accepted for it, as for `inf` and `nan`.

### Special values

- Fortran exponents such as `1.5D+00` are numbers.
- `inf` and `nan` are numbers: equal infinities match, and so do two `nan`s (`.inf` and `.nan` in YAML).

## Complete example

```yaml
Name: Solver regression suite
Executable: solver.x

Inputs:
  case_01.in:
    ExtraFiles: [basis.dat, pseudo.UPF]
    Processors: 4
    Matches:
      results:
        file: results.txt
        Total Energy:
          grep: "Total energy:"
          field: 3
          value: -42.5000
          tol: 1e-4
        Convergence Flag:
          line: 5
          field: 2
          value: converged
        Band Gap:
          grep: "Band gap"
          column: 21
          value: 1.0342
          tol: 1e-3
      Warning count:
        file: run.log
        grep: WARNING
        count: 0
      Restart File:
        file: restart.bin
        size: 65536
      Output summary:
        directory: output
        file_is_present: summary.txt

  # Restarts from the files written by case_01.in
  case_02.in:
    Matches:
      Final Status:
        file: stdout
        line: -1
        field: 1
        value: DONE

  # A case expected to fail (negative testing)
  bad_input.in:
    ExpectedFailure: true
    Matches:
      Error message:
        file: stderr
        grep: "Invalid input"
        count: 1
```

## Running tests

```bash
pseudotest test.yaml -D ./bin
```

The main options are `-D` for the directory of the executables, `-t` for the timeout of each input (600 seconds by
default), `-r` for a report, `-p` to keep the working directory, and `-v`/`-vv` for more messages. See
[Command line](reference.md#pseudotest) for all of them.

### Inspecting failures

When an execution fails, the last 10 lines of its standard output and error are shown, or all of them with `-vv`.

Add `-p` to keep the working directory, whose path is printed at the start of the run, and inspect the files there:

```bash
pseudotest test.yaml -D ./bin -p
```

## Updating test files

`pseudotest-update` runs a test, like `pseudotest`, and then updates its test file. It has three modes.

### Update tolerances

```bash
pseudotest-update test.yaml -D ./bin --tolerance
```

For each failing numeric match, sets `tol` to `|calculated - reference| × 1.1` rounded up to two significant figures,
e.g. `0.0038` for a difference of `0.0034`. The tolerance is never smaller than the precision of the calculated
value, so that the match passes on the next run. Reference values are not changed.

### Update reference values

```bash
pseudotest-update test.yaml -D ./bin --reference       # failing matches only
pseudotest-update test.yaml -D ./bin --reference-all   # all matches
```

Replaces the reference values of the failing matches (`--reference`, `-r`) or of all matches (`--reference-all`,
`-R`) with the calculated values. Tolerances are not changed. The new values keep the format of the old ones: a
reference written as `1.25568282E-01` stays in scientific notation with the same number of digits, and `-42.5000`
keeps four decimals.

### Write to a different file

```bash
pseudotest-update test.yaml -D ./bin --reference --output updated.yaml
```

The original file is left untouched; the changes are written to `updated.yaml`. Comments and formatting are
preserved in both cases.

### What is never updated

- Matches with `protected: true`, set on the match or on one of its groups. This is useful for references obtained
  in another way, e.g. theoretical values:

    ```yaml
    Critical Reference:
      file: results.txt
      grep: "Final value"
      field: 3
      value: 123.45
      protected: true
    ```

- `file_is_present` checks.
- Matches whose value could not be extracted.
- Numeric references that the calculated value would replace with text, such as a Fortran overflow `***`. A warning
  is printed instead.

### Broadcast and tolerance updates

When a tolerance update applies to a broadcast match, a single `tol` is expanded to a list, and only the elements of
the failing matches are changed. With the outputs `1.0000000` and `2.0034000`, this match:

```yaml
multi:
  file: [r1.txt, r2.txt]
  grep: "Value:"
  field: 2
  value: [1.0, 2.0]
  tol: 1e-6
```

becomes:

```yaml
multi:
  file: [r1.txt, r2.txt]
  grep: "Value:"
  field: 2
  value: [1.0, 2.0]
  tol:
  - 1e-6
  - 0.0038
```

## MPI execution

Set `MPIEXEC` to your MPI launcher to run the executable in parallel:

```bash
MPIEXEC=mpiexec pseudotest test.yaml -D ./bin
```

The launcher is prefixed to the command, with the number of processes given by `Processors`:

```
mpiexec -np 4 solver.x case_01.in
```

`MPIEXEC` can include options of the launcher, e.g. `MPIEXEC="mpirun --oversubscribe"`.

Different inputs can use different numbers of processes:

```yaml
Inputs:
  small.in:
    Processors: 1
    Matches: ...
  large.in:
    Processors: 16
    Matches: ...
```

When `MPIEXEC` is not set, `Processors` has no effect. The launchers and their flags are listed in the
[Reference](reference.md#environment-variables).

## Reports

Pass `--report FILE` to append a YAML document with the results of the run to `FILE`:

```bash
pseudotest test.yaml -D ./bin --report results.yaml
```

Several runs can append to the same file, which then holds one document per run. The report lists, for every match,
its parameters, the calculated value, the reference value, its status (`pass` or `fail`), and the reason of a
failure; see [Report](reference.md#report) for its format. It is useful as a CI artifact or for further processing.

## Troubleshooting

### Errors in the test file

Mistakes in the test file stop the run with exit code `2` and a one-line message, e.g.:

```
ERROR: Unknown match parameter 'fiel' in 'Inputs > input.txt > Matches > energy'
ERROR: Match 'energy' requires a 'file' or 'directory' parameter
ERROR: Executable 'solver.x' not available at bin/solver.x
```

Add `-vv` to see the traceback.

### Executable not found

- Check that `Executable` matches the file name of the executable.
- Check that the directory given to `-D` contains it.
- Check that it is executable (`chmod +x`).

### A value cannot be extracted

The failure gives the reason: the file does not exist, the `grep` text is not in it, or the line, field or column is
out of range. Add `-p` to keep the working directory, and open the file there to check it.

### Timeouts

A timeout is reported as `=== case_01.in: timed out after 600 s ===`.

- Increase `--timeout`.
- Add `-vv` to see the full output of the executable.
- Check the MPI settings, and that the launcher is available.

### Unexpected updates

- Matches with `protected: true` are never changed, and neither are `file_is_present` checks.
- `--tolerance` and `--reference` only change failing matches; `--reference-all` changes all of them.
