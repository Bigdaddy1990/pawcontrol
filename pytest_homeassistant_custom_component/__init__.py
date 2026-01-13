"""Shim for pytest-homeassistant-custom-component.

The real plugin is optional for the lightweight stub environment. This module
only exposes a marker placeholder so pytest can start without external
dependencies.
"""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register a marker placeholder used by the upstream plugin."""

    config.addinivalue_line(
        'markers', 'hacc: compatibility marker for pytest-homeassistant stubs'
    )
