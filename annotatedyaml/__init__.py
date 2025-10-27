"""Proxy that exposes the installed ``annotatedyaml`` distribution."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
from pathlib import Path


def _load_vendor_module() -> None:
    module_name = __name__
    current_path = Path(__file__).resolve()
    current_parent = current_path.parent

    search_roots: list[str] = []
    for path_entry in sys.path:
        try:
            entry_path = Path(path_entry).resolve()
        except OSError:  # pragma: no cover - defensive for unreadable paths
            continue
        if entry_path == current_parent:
            continue
        search_roots.append(path_entry)

    for root in search_roots:
        spec = importlib.machinery.PathFinder.find_spec(module_name, [root])
        if spec is None or spec.origin is None:
            continue
        candidate = Path(spec.origin).resolve()
        if candidate == current_path:
            continue
        loader = spec.loader
        if loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        loader.exec_module(module)
        return

    msg = "annotatedyaml vendor package was not found in site-packages"
    raise ImportError(msg)


_load_vendor_module()

_VENDOR = sys.modules.get(__name__)

if _VENDOR is None:  # pragma: no cover - defensive
    raise ImportError("annotatedyaml vendor package could not be loaded")

__all__ = list(getattr(_VENDOR, "__all__", ()))

for attribute in dir(_VENDOR):
    if attribute.startswith("__") and attribute not in {"__all__"}:
        continue
    globals()[attribute] = getattr(_VENDOR, attribute)


