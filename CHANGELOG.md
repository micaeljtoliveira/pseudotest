# Changelog

All notable changes to `pseudotest` are listed here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

These changes can change the result of existing test files:

- Errors in a test file or in the files it refers to (missing test file, executable, input or extra file, invalid
  match) are usage errors, reported in one line with exit code 2. They used to give a traceback and exit code 1, the
  code of a failed test. `-vv` shows the traceback.
- `line: -1` is the last line of the file, as documented; it was the second to last. `line: 0` is an error.
- Matches are checked: an unknown parameter, `matches:` instead of `match:`, a match without `file` or `directory`,
  and a match named after a parameter such as `count` are errors. A misspelled parameter used to turn the match into a
  group.
- Broadcast elements without a `match` list are named `name[0]`, `name[1]`, ...; they all had the same name, and the
  report kept only the last one.
- An input in a subdirectory is copied into the working directory by its file name, and run with that name.
- Fortran `D` exponents are compared as numbers, and equal infinities, or two nans, match.
- Python 3.10 or later is required, as the code already needed it.
- Match types registered with `register_match_handler` are tried before the built-in ones, which handle any match with
  a `file` or a `directory`. A new match type using `file` could not be used before.
- The input file is removed from the working directory after its run with the `stdin` input method too, as with the
  other methods.

### Added

- `python -m pseudotest` runs `pseudotest`.
- `MPIEXEC` can include options of the launcher, e.g. `mpirun --oversubscribe`.

### Fixed

- `pseudotest-update -t` no longer rounds floating-point noise up: a difference of `0.005` gave a tolerance of `0.0056`
  instead of `0.0055`.
- The parameters of a match are written to the report in their order; their order changed from run to run.
- A value that cannot be extracted (missing file, pattern not found, field out of range) is reported as a failure with
  its reason; nothing was printed.
- The details of a tolerance below the precision of the calculated value are printed on separate lines, with the
  suggested minimum tolerance.
- Timeouts and launch failures are reported.
- An input written without parameters runs with the top-level ones, and a key under `Inputs` is an error instead of
  being run as an input.
- `pseudotest-update`:
    - does not crash on a Fortran overflow (`***`) or an infinite value, and does not replace a numeric reference with
      text;
    - does not write `count_files: 'False'` for a missing directory;
    - keeps boolean references right;
    - writes tolerances that are not below the precision of the calculated value, so that the match passes on the next
      run.
- The working directory is removed when a run stops on an error.
- A disabled test is written to the report.
- The counters of `PseudoTestRunner` are reset by each run.

### Documentation

- The README is a short introduction, and the manual has a new [Reference](docs/reference.md) page listing every key,
  option and exit code, and the report format.
- The user guide describes the execution model and the scopes, and its errors are fixed.
- The YAML examples of the documentation are checked by the tests, and the examples of the docstrings are run as
  doctests.

## [0.3.1] - 2026-10-31

### Fixed

- A zero written in scientific notation (e.g. `0.00000000E+000`) is exact when checking that a tolerance is not below
  the precision of the calculated value. A match that is exactly zero with one compiler and a rounding residue with
  another could not pass on both.

## [0.3.0] - 2026-10-30

### Fixed

- Reference values written by `pseudotest-update`:
    - keep their scientific notation and digits; they were written in fixed notation, so `1.25568286E-01` became
      `0.12556829`;
    - always have one digit before the decimal point of the mantissa;
    - have the sign of the new value;
    - long flow sequences are no longer re-wrapped at 80 columns.

### Documentation

- How to use scopes to avoid repetition, and a link to the manual in the README.

## [0.2.0] - 2026-03-23

### Added

- `pseudotest-update -R/--reference-all` updates the reference values of all matches, including passing ones.

### Changed

- A tolerance smaller than the precision of the calculated value is an error instead of a warning, and
  `pseudotest-update -t` takes it into account.
- Commas are separators when extracting values with `field` or `column`.

### Fixed

- `protected: true` on a match group protects the matches it contains.

## [0.1.0] - 2026-02-25

First release:

- YAML test files with inputs, scopes and broadcast matches.
- Matches by keyword, line, field, column and complex magnitude, line counts, file sizes, and file counts and presence
  in directories.
- Numeric comparisons with tolerances, and a check of the tolerance against the precision of the calculated value.
- Input passed as an argument, on the standard input, or under a fixed name.
- Expected failures and execution timeouts.
- MPI support via the `MPIEXEC` environment variable.
- YAML reports.
- `pseudotest-update` to update tolerances or reference values in place.

[Unreleased]: https://github.com/micaeljtoliveira/pseudotest/compare/v0.3.1...HEAD
[0.3.1]: https://github.com/micaeljtoliveira/pseudotest/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/micaeljtoliveira/pseudotest/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/micaeljtoliveira/pseudotest/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/micaeljtoliveira/pseudotest/releases/tag/v0.1.0
