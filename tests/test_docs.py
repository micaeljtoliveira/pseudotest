"""Checks of the YAML examples of the documentation.

Every ``yaml`` code block of the README and of the manual must be valid YAML and use only known keys, so that the
examples cannot drift from the code, as happened with ``matches:`` instead of ``match:``.
"""

import re
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest

from pseudotest.config import yaml
from pseudotest.matchers import RESERVED_KEYS

ROOT = Path(__file__).resolve().parents[1]
# The developer guide is left out, as its example of a new match type uses a key that is not registered
DOCUMENTS = [ROOT / "README.md", *sorted(p for p in (ROOT / "docs").glob("*.md") if p.name != "developer-guide.md")]

# Keys of a test file that are not match parameters
TEST_FILE_KEYS = {
    "Name",
    "Enabled",
    "Executable",
    "InputMethod",
    "RenameTo",
    "Inputs",
    "ExtraFiles",
    "Processors",
    "ExpectedFailure",
    "Matches",
}

_YAML_BLOCK = re.compile(r"^```yaml\n(.*?)^```", re.MULTILINE | re.DOTALL)


def _yaml_blocks() -> Iterator[Any]:
    """Yield one test parameter per YAML block, identified by its document and line."""
    for document in DOCUMENTS:
        text = document.read_text()
        for block in _YAML_BLOCK.finditer(text):
            line = text.count("\n", 0, block.start()) + 1
            yield pytest.param(block.group(1), id=f"{document.relative_to(ROOT)}:{line}")


def _unknown_keys(node: Any) -> Iterator[str]:
    """Yield the keys of *node*, at any depth, that are neither test-file keys nor match parameters.

    Keys holding a mapping are inputs, match groups or matches, whose names are free.
    """
    if isinstance(node, Mapping):
        for key, value in node.items():
            if isinstance(value, Mapping):
                yield from _unknown_keys(value)
            elif key not in TEST_FILE_KEYS and key not in RESERVED_KEYS:
                yield key


@pytest.mark.parametrize("block", list(_yaml_blocks()))
def test_yaml_example(block):
    data = yaml.load(block)

    # Report examples are keyed by the test file and use their own keys
    if isinstance(data, Mapping) and any(str(key).endswith(".yaml") for key in data):
        return

    assert list(_unknown_keys(data)) == []
