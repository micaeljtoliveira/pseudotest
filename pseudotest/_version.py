"""Version of pseudotest, set by setuptools_scm from the git tags."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pseudotest")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "unknown"
