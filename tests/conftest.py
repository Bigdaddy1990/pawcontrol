"""Global test configuration for PawControl tests."""

from __future__ import annotations

import importlib.util
import sys

_REQUIRED_MODULES = (
    "homeassistant",
    "pytest_homeassistant_custom_component",
)

_missing = [
    module for module in _REQUIRED_MODULES if importlib.util.find_spec(module) is None
]

if _missing:
    import pytest

    # Only the Home Assistant integration tests require the optional
    # dependencies.  Unit tests targeting pure python helpers should still run
    # to provide meaningful coverage for CI.
    collect_ignore_glob = [
        "components/*",
    ]

    def pytest_addoption(parser):
        """Register pytest-asyncio compatibility option when dependencies are absent."""

        parser.addini(
            "asyncio_mode",
            "pytest-asyncio compatibility shim for missing dependency",
            default="auto",
        )

    print(
        "Home Assistant test dependencies are unavailable – integration tests under "
        "tests/components are skipped.",
        file=sys.stderr,
    )

else:
    import pytest_homeassistant_custom_component

    pytest_plugins = ("pytest_homeassistant_custom_component",)
