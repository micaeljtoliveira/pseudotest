from collections import ChainMap
from pathlib import Path
from typing import Any, Dict, List

# Try to import yaml
try:
    from ruamel.yaml import YAML

    yaml = YAML()
except ImportError as e:
    raise ImportError("ruamel.yaml not available. Install with: pip install ruamel.yaml") from e

RESERVED_KEYS = {
    "match",
    "file",
    "value",
    "size",
    "grep",
    "field",
    "column",
    "line",
    "field_re",
    "field_im",
    "count",
    "tol",
}


def broadcast_params(params: ChainMap[str, Any]) -> List[ChainMap[str, Any]]:
    """Broadcast parameters containing lists to multiple parameter sets"""
    from pseudotest.utils import UsageError

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

    def __init__(self):
        """Initialize a new TestConfig instance"""
        self.data: Dict[str, Any] = {}

    def load(self, file: Path):
        """Load configuration from a YAML file"""

        # Load YAML test file
        if not file.is_file():
            raise FileNotFoundError(f"Test file not found: {file}")
        try:
            with file.open() as f:
                self.data = yaml.load(f)
        except Exception as e:
            raise ValueError(f"Failed to load test file: {e}") from e

    def input_scope(self, input_name: str) -> ChainMap[str, Any]:
        """Get input scope from loaded data"""

        inputs = self.data.get("Inputs", {})
        input_cfg = inputs.get(input_name, {})

        return ChainMap(input_cfg, inputs, self.data)
