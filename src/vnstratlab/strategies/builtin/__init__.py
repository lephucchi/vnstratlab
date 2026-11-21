"""Built-in strategies. Each module defines classes decorated with ``@register_strategy``.

Importing this package imports every module in it, so the registry sees them. The packaged
registry is empty until the strategy cards (P1-T14..P1-T19) add modules; tests register local
classes instead.
"""

from __future__ import annotations

import importlib
import pkgutil

for _module in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{_module.name}")
