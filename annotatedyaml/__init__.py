"""Expose the vendored ``annotatedyaml`` module with a local fallback."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
from collections.abc import Iterable
from pathlib import Path
from types import ModuleType


def _iter_search_roots(current_parent: Path) -> Iterable[str]:
    """Yield import roots that may host a vendored ``annotatedyaml`` module."""

    for path_entry in sys.path:
        try:
            entry_path = Path(path_entry).resolve()
        except OSError:  # pragma: no cover - defensive for unreadable paths
            continue
        if entry_path == current_parent:
            continue
        yield path_entry


def _load_vendor_module() -> ModuleType | None:
    """Load the real ``annotatedyaml`` distribution when it is installed."""

    module_name = __name__
    current_path = Path(__file__).resolve()
    search_roots = list(_iter_search_roots(current_path.parent))

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
        return module

    return None


def _load_stub_module() -> ModuleType:
    """Return the lightweight loader stub bundled with the repository."""

    from . import loader as stub

    return stub


_vendor = _load_vendor_module()
if _vendor is None:
    _vendor = _load_stub_module()

__doc__ = getattr(_vendor, "__doc__", __doc__)
__all__ = list(getattr(_vendor, "__all__", ()))
if not __all__:
    __all__ = [name for name in dir(_vendor) if not name.startswith("_")]

for attribute in __all__:
    globals()[attribute] = getattr(_vendor, attribute)

# Preserve key module metadata for debuggability.
__version__ = getattr(_vendor, "__version__", globals().get("__version__"))
