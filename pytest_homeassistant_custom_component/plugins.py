"""Compatibility pytest plugin hooks for local Home Assistant tests."""

from __future__ import annotations


def pytest_configure(config: object) -> None:
    add_line = getattr(config, "addinivalue_line", None)
    if callable(add_line):
        add_line("markers", "hacc: compatibility marker for pytest-homeassistant stubs")
