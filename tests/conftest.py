"""Global test configuration for PawControl tests."""

from __future__ import annotations

import importlib.util

_REQUIRED_MODULES = (
    "homeassistant",
    "pytest_homeassistant_custom_component",
)

_missing = [
    module for module in _REQUIRED_MODULES if importlib.util.find_spec(module) is None
]

if _missing:
    import pytest

    collect_ignore_glob = ["*"]

    def pytest_addoption(parser):
        """Register pytest-asyncio compatibility option when dependencies are absent."""

        parser.addini(
            "asyncio_mode",
            "pytest-asyncio compatibility shim for missing dependency",
            default="auto",
        )

    def pytest_sessionstart(session):
        """Abort the session gracefully when required dependencies are unavailable."""

        pytest.exit(
            "Skipping PawControl tests because dependencies are missing: "
            + ", ".join(_missing),
            returncode=0,
        )

else:
    import pytest_homeassistant_custom_component

    pytest_plugins = ("pytest_homeassistant_custom_component",)
