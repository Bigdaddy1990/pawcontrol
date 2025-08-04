"""Compatibility wrapper for module helper functions.

Historically Paw Control exposed helper functions through a dedicated
``module_manager`` module. The actual implementation now lives in
``module_registry``. This module simply re-exports those helpers so existing
imports continue to function while keeping the logic in a single place.
"""

from __future__ import annotations

from .module_registry import (
    MODULES,
    Module,
    async_ensure_helpers,
    async_setup_modules,
    async_unload_modules,
)

__all__ = [
    "MODULES",
    "Module",
    "async_ensure_helpers",
    "async_setup_modules",
    "async_unload_modules",
]

