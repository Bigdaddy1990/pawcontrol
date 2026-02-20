"""Lightweight pytest-homeassistant-custom-component compatibility shim."""

from __future__ import annotations


def pytest_configure(config: object) -> None:
    """Register compatibility marker used by local tests."""
    add_line = getattr(config, "addinivalue_line", None)
    if callable(add_line):
        add_line("markers", "hacc: compatibility marker for pytest-homeassistant stubs")
