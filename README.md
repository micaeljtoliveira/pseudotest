# pseudotest

`pseudotest` is a YAML-driven regression testing framework for scientific software.

It runs an executable on one or more input files in a temporary working directory, then checks the files it writes
against reference values, with tolerances for numbers.

## Highlights

- Test files in YAML, with scopes to write shared settings once
- Values extracted by keyword (`grep`), line, field or column, including complex magnitudes
- File size, file count and file presence checks
- Numeric comparisons with absolute tolerances, which must not be finer than the printed precision; Fortran `D`
  exponents, `inf` and `nan` are handled
- Broadcast matches, to check several values with one definition
- `pseudotest-update` to update reference values or tolerances in place, keeping comments and number formats
- YAML reports for CI artifacts
- MPI support via the `MPIEXEC` environment variable

## Installation

```bash
pip install pseudotest
```

or from source:

```bash
git clone https://github.com/micaeljtoliveira/pseudotest.git
cd pseudotest
pip install -e .                # add [devel,test] for development, [docs] for the documentation
```

`pseudotest` requires Python 3.11 or later.

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

and run it, with `solver.x` in `./bin`:

```bash
pseudotest test.yaml -D ./bin
```

This runs `solver.x case_01.in` in a temporary directory, finds the first line of `output.txt` containing `Energy:`,
and checks that its second field is `-42.5000` within `1e-4`.

## Command-line tools

| Command | Description |
|---|---|
| `pseudotest TEST_FILE -D DIR` | Run the test. Options: `-t` timeout per input (default 600 s), `-r FILE` append a YAML report, `-p` keep the working directory, `-v`/`-vv` more messages |
| `pseudotest-update TEST_FILE -D DIR -t` | Run the test and set the tolerances of failing numeric matches |
| `pseudotest-update TEST_FILE -D DIR -r` | Run the test and replace the reference values of failing matches |
| `pseudotest-update TEST_FILE -D DIR -R` | Run the test and replace the reference values of all matches |

`pseudotest-update` overwrites the test file, or writes to the file given by `-o FILE`. Matches marked
`protected: true` are never updated. It also accepts `-p`, and `--timeout` and `--report` (long options only, as `-t`
and `-r` select the update mode).

Exit codes: `0` all passed, `1` an execution or a match failed, `2` invalid test file or command line, `99` internal
error.

## Documentation

The manual is at **https://micaeljtoliveira.github.io/pseudotest/**:

- [User Guide](https://micaeljtoliveira.github.io/pseudotest/user-guide/): writing and running tests, match types,
  scopes, updates, MPI
- [Reference](https://micaeljtoliveira.github.io/pseudotest/reference/): every key, option and exit code, and the
  report format
- [Developer Guide](https://micaeljtoliveira.github.io/pseudotest/developer-guide/): architecture and contributing

Changes between releases are listed in the
[changelog](https://github.com/micaeljtoliveira/pseudotest/blob/main/CHANGELOG.md).

## License

Mozilla Public License 2.0 (MPL-2.0)
