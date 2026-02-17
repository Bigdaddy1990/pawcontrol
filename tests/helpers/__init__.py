"""Shared test helpers for the PawControl integration."""

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from typing import TypeVar

from . import homeassistant_test_stubs
from .homeassistant_test_stubs import (
    ConfigEntryNotReady,
    HomeAssistantError,
    install_homeassistant_stubs,
)

__all__ = [
    "ConfigEntryNotReady",
    "HomeAssistantError",
    "ensure_package",
    "homeassistant_test_stubs",
    "install_homeassistant_stubs",
    "load_module",
    "typed_deepcopy",
]

T = TypeVar("T")


T = TypeVar("T")


def typed_deepcopy[T](value: T) -> T:
    """Return a type-preserving deep copy for complex fixtures."""  # noqa: E111

    return deepcopy(value)  # noqa: E111


def ensure_package(name: str, path: Path) -> None:
    """Create a placeholder package in ``sys.modules`` for dynamic imports."""  # noqa: E111

    if name not in sys.modules:  # noqa: E111
        module = importlib.util.module_from_spec(
            importlib.util.spec_from_loader(name, loader=None),
        )
        module.__path__ = [str(path)]  # type: ignore[attr-defined]
        sys.modules[name] = module


def load_module(name: str, path: Path) -> ModuleType:
    """Load a module from ``path`` under the provided module name."""  # noqa: E111

    spec = importlib.util.spec_from_file_location(name, path)  # noqa: E111
    if spec is None or spec.loader is None:  # noqa: E111
        raise RuntimeError(f"Cannot load module {name} from {path}")
    module = importlib.util.module_from_spec(spec)  # noqa: E111
    sys.modules[name] = module  # noqa: E111
    spec.loader.exec_module(module)  # noqa: E111
    return module  # noqa: E111
