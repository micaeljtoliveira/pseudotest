# pseudotest

`pseudotest` is a YAML-driven regression testing framework for scientific software. It runs an executable on one or
more input files in a temporary working directory, then checks the files it writes against reference values, with
tolerances for numbers.

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

```bash
pip install pseudotest
pseudotest test.yaml -D ./bin
```

## Guides

- [User Guide](user-guide.md): writing and running tests, match types, scopes, updating references, MPI and reports.
- [Reference](reference.md): every key, option and exit code, and the report format.
- [Developer Guide](developer-guide.md): architecture, extending pseudotest with new match types, and contributing.

Changes between releases are listed in the
[changelog](https://github.com/micaeljtoliveira/pseudotest/blob/main/CHANGELOG.md).
