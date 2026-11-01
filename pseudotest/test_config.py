"""Test configuration loading and parameter broadcasting for pseudotest."""

from collections import ChainMap
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pseudotest.exceptions import UsageError

# Try to import yaml
try:
    from ruamel.yaml import YAML

    yaml = YAML()
    yaml.preserve_quotes = True
    # Keep long flow sequences on one line when an updated config is written back
    yaml.width = 4096
except ImportError as e:  # pragma: no cover
    raise ImportError("ruamel.yaml not available. Install with: pip install ruamel.yaml") from e


def broadcast_params(params: ChainMap[str, Any]) -> list[ChainMap[str, Any]]:
    """Broadcast parameters containing lists to multiple parameter sets"""
    # Check if parameters include any list and get the broadcast length
    length = 0
    for value in params.values():
        if isinstance(value, list):
            if length == 0:
                length = len(value)
            elif len(value) != length:
                raise UsageError("All parameter lists must have the same length")

    # If no lists found, return single parameter set
    if length == 0:
        return [params]

    # Broadcast parameters across all positions
    broadcasted_params = []
    for i in range(length):
        param_set = ChainMap()
        for key, value in params.items():
            param_set[key] = value[i] if isinstance(value, list) else value
        broadcasted_params.append(param_set)

    return broadcasted_params


class TestConfig:
    """Class to load and store test configuration from YAML file"""

    # Not a test class, although its name matches pytest's discovery pattern
    __test__ = False

    def __init__(self):
        """Initialize a new TestConfig instance"""
        self.data: dict[str, Any] = {}

    def load(self, file: Path):
        """Load configuration from a YAML file

        Raises:
            UsageError: If the file is missing, is not valid YAML, or is not a test description
        """

        # Load YAML test file
        if not file.is_file():
            raise UsageError(f"Test file not found: {file}")
        try:
            with file.open() as f:
                data = yaml.load(f)
        except Exception as e:
            raise UsageError(f"Failed to load test file {file}: {e}") from e

        if not isinstance(data, Mapping):
            raise UsageError(f"Test file {file} must contain a mapping of test parameters")
        if "Name" not in data:
            raise UsageError(f"Test file {file} has no 'Name'")
        self.data = data

    def validate(self):
        """Check the structure of the inputs of an enabled test

        Raises:
            UsageError: If 'Inputs' is missing or an input is not a mapping of parameters
        """
        inputs = self.data.get("Inputs")
        if not isinstance(inputs, Mapping):
            raise UsageError("'Inputs' must be a mapping of input files to their parameters")
        for input_name, input_cfg in inputs.items():
            # An input without parameters (written 'input.txt:') is allowed
            if input_cfg is not None and not isinstance(input_cfg, Mapping):
                raise UsageError(f"Parameters of input '{input_name}' must be a mapping, got {input_cfg!r}")

    def input_scope(self, input_name: str) -> ChainMap[str, Any]:
        """Get input scope from loaded data"""

        input_cfg = self.data["Inputs"].get(input_name) or {}

        return ChainMap(input_cfg, self.data)
