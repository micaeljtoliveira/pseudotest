# Pseudotest

A regression testing framework for scientific software.

## Features

- YAML-based test configuration
- Multiple match types: `grepfield`, `line`, `grepcount`, `size`, `grep`, `linefield`, `linefield_abs`
- Support for both numeric and string comparisons
- Configurable precision per test file
- Comprehensive error reporting
- Colored terminal output

## Installation

```bash
pip install -e .
```

## Usage

### Command Line

```bash
pseudotest test_file.yaml -D /path/to/executables
```

### Python API

```python
from pseudotest import YamlTestRunner

runner = YamlTestRunner()
runner.run()
```

## YAML Test Format

```yaml
Name: Test Description
Enabled: Yes
Executable: program_name
InputMethod: argument  # argument, stdin, or rename
RenameTo: expected_name.inp  # Required when InputMethod is 'rename'
Precision: 1e-4
Tests:
  Input:
    File: input.txt
    ExtraFiles: [file1.txt, file2.txt]
    Matches:
      field_extraction: [grepfield: [output.txt, 'pattern', 3], 1.23]
      error_count: [grepcount: [log.txt, 'ERROR'], 0]
      file_size: [size: [data.dat], 1024]
```

### Input Methods

The framework supports three ways to pass input files to executables:

1. **argument** (default): Pass the input file as the first argument
   ```yaml
   InputMethod: argument
   Tests:
     Input:
       File: input.dat
   ```
   Executes as: `program_name input.dat`

2. **stdin**: Redirect the input file to standard input
   ```yaml
   InputMethod: stdin
   Tests:
     Input:
       File: input.dat
   ```
   Executes as: `program_name < input.dat`

3. **rename**: Rename the input file to a specific name expected by the executable
   ```yaml
   InputMethod: rename
   RenameTo: input.inp
   Tests:
     Input:
       File: input.dat
   ```
   Copies `input.dat` to `input.inp` and executes as: `program_name`

### Match Format

The `Matches` section uses a dictionary format where each match has a descriptive name as the key and a list containing the match specification and expected value:

```yaml
Matches:
  match_name: [match_type_specification, expected_value]
```

Examples:
- `field_test: [grepfield: [output.txt, 'Energy:', 2], 1.23456]`
- `count_test: [grepcount: [log.txt, 'WARNING'], 0]`
- `size_test: [size: [data.dat], 1024]`

## Match Types

- **grepfield**: Extract field from line matching pattern
- **line**: Extract field from specific line number
- **grepcount**: Count lines matching pattern
- **size**: Get file size in bytes
- **grep**: Extract substring from matching line
- **linefield**: Alias for line match
- **linefield_abs**: Calculate absolute value from complex fields

## License

Mozilla Public License 2.0 (MPL-2.0)
