"""Built-in strategies. Each module defines classes decorated with ``@register_strategy``.

Importing this package imports every module in it, so the registry sees them. The packaged
registry holds the strategy cards' modules (S00, S17 from P1-T14; the rest follow in
P1-T15..P1-T19); tests register local classes under their own ids.
"""

from __future__ import annotations

import importlib
import pkgutil

for _module in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{_module.name}")
