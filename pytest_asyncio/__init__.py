"""Lightweight local pytest-asyncio compatibility shim."""

from .plugin import (
    event_loop,
    fixture,
    pytest_addoption,
    pytest_configure,
    pytest_pyfunc_call,
)

__all__ = [
    "event_loop",
    "fixture",
    "pytest_addoption",
    "pytest_configure",
    "pytest_pyfunc_call",
]
