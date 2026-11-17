"""vnstratlab: a strategy lab for Vietnamese stocks.

The package produces recommendations only. It never places, routes or confirms
orders with any broker. See DISCLAIMER.md and docs/adr/ADR-001.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("vnstratlab")
except PackageNotFoundError:  # pragma: no cover - running from a source tree without install
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
