"""Tests for the repairs helpers shipped with the integration."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

from unittest.mock import AsyncMock


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _ensure_package(name: str, path: Path) -> ModuleType:
    """Ensure that ``name`` is registered as a namespace package for tests."""

    module = sys.modules.get(name)
    if module is None:
        module = ModuleType(name)
        module.__path__ = [str(path)]  # type: ignore[attr-defined]
        sys.modules[name] = module
    return module


def _load_module(name: str, path: Path) -> ModuleType:
    """Load ``name`` from ``path`` without executing package ``__init__`` files."""

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _install_homeassistant_stubs(async_create_issue: AsyncMock) -> None:
    """Install lightweight Home Assistant shims for the repairs tests."""

    existing_issue_registry = sys.modules.get("homeassistant.helpers.issue_registry")
    if "homeassistant" in sys.modules and existing_issue_registry is not None:
        existing_issue_registry.async_create_issue = async_create_issue
        return

    homeassistant = ModuleType("homeassistant")
    sys.modules["homeassistant"] = homeassistant

    components = ModuleType("homeassistant.components")
    sys.modules["homeassistant.components"] = components

    repairs = ModuleType("homeassistant.components.repairs")

    class RepairsFlow:  # pragma: no cover - simple placeholder type
        pass

    repairs.RepairsFlow = RepairsFlow
    sys.modules["homeassistant.components.repairs"] = repairs

    config_entries = ModuleType("homeassistant.config_entries")

    class ConfigEntry:  # pragma: no cover - placeholder matching real API
        def __init__(self, entry_id: str) -> None:
            self.entry_id = entry_id
            self.data: dict[str, Any] = {}
            self.options: dict[str, Any] = {}
            self.version = 1

    config_entries.ConfigEntry = ConfigEntry
    sys.modules["homeassistant.config_entries"] = config_entries

    core = ModuleType("homeassistant.core")

    class HomeAssistant:  # pragma: no cover - container for hass attributes
        def __init__(self) -> None:
            self.data: dict[str, Any] = {}

    def callback(func):  # pragma: no cover - decorator passthrough
        return func

    core.HomeAssistant = HomeAssistant
    core.callback = callback
    sys.modules["homeassistant.core"] = core

    data_entry_flow = ModuleType("homeassistant.data_entry_flow")
    data_entry_flow.FlowResult = dict  # pragma: no cover - type alias shim
    sys.modules["homeassistant.data_entry_flow"] = data_entry_flow

    helpers = ModuleType("homeassistant.helpers")
    sys.modules["homeassistant.helpers"] = helpers

    issue_registry = ModuleType("homeassistant.helpers.issue_registry")
    issue_registry.DOMAIN = "repairs"

    class IssueSeverity(StrEnum):  # pragma: no cover - subset of real enum
        ERROR = "error"
        WARNING = "warning"
        INFO = "info"

    issue_registry.IssueSeverity = IssueSeverity
    issue_registry.async_create_issue = async_create_issue
    sys.modules["homeassistant.helpers.issue_registry"] = issue_registry

    selector_module = ModuleType("homeassistant.helpers.selector")

    def selector(config: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover
        return config

    selector_module.selector = selector
    sys.modules["homeassistant.helpers.selector"] = selector_module

    util_module = ModuleType("homeassistant.util")
    sys.modules["homeassistant.util"] = util_module

    dt_module = ModuleType("homeassistant.util.dt")
    dt_module.utcnow = lambda: datetime(2024, 1, 1, 12, 0, 0)  # pragma: no cover
    util_module.dt = dt_module
    sys.modules["homeassistant.util.dt"] = dt_module


def _load_repairs_module(async_create_issue: AsyncMock) -> ModuleType:
    """Load the repairs module with all required stubs registered."""

    _ensure_package("custom_components", PROJECT_ROOT / "custom_components")
    _ensure_package(
        "custom_components.pawcontrol",
        PROJECT_ROOT / "custom_components" / "pawcontrol",
    )

    _install_homeassistant_stubs(async_create_issue)

    _load_module(
        "custom_components.pawcontrol.const",
        PROJECT_ROOT / "custom_components" / "pawcontrol" / "const.py",
    )

    runtime_data_stub = ModuleType("custom_components.pawcontrol.runtime_data")
    runtime_data_stub.get_runtime_data = lambda hass, entry: None
    sys.modules["custom_components.pawcontrol.runtime_data"] = runtime_data_stub

    return _load_module(
        "custom_components.pawcontrol.repairs",
        PROJECT_ROOT / "custom_components" / "pawcontrol" / "repairs.py",
    )


def test_async_create_issue_serialises_payload() -> None:
    """Ensure list values become strings for placeholders and storage."""

    async_create_issue = AsyncMock()
    repairs = _load_repairs_module(async_create_issue)

    hass = SimpleNamespace(data={})
    entry = SimpleNamespace(entry_id="entry-id", data={}, options={})

    asyncio.run(
        repairs.async_create_issue(
            hass,
            entry,
            "issue-one",
            repairs.ISSUE_DUPLICATE_DOG_IDS,
            {"duplicate_ids": ["alpha", "beta"], "dogs_count": 2},
            severity="warning",
        )
    )

    async_create_issue.assert_awaited_once()
    _, kwargs = async_create_issue.await_args

    assert kwargs["data"]["duplicate_ids"] == "alpha, beta"
    assert kwargs["data"]["dogs_count"] == 2
    assert kwargs["translation_placeholders"]["duplicate_ids"] == "alpha, beta"
    assert kwargs["translation_placeholders"]["dogs_count"] == "2"


def test_async_create_issue_omits_none_placeholders() -> None:
    """None values are excluded from translation placeholders but kept as data."""

    async_create_issue = AsyncMock()
    repairs = _load_repairs_module(async_create_issue)

    hass = SimpleNamespace(data={})
    entry = SimpleNamespace(entry_id="entry-id", data={}, options={})

    asyncio.run(
        repairs.async_create_issue(
            hass,
            entry,
            "issue-two",
            repairs.ISSUE_INVALID_DOG_DATA,
            {"invalid_dog": None, "weight": 12.5},
            severity="error",
        )
    )

    async_create_issue.assert_awaited_once()
    _, kwargs = async_create_issue.await_args

    assert "invalid_dog" not in kwargs["translation_placeholders"]
    assert kwargs["data"]["invalid_dog"] is None
    assert kwargs["translation_placeholders"]["weight"] == "12.5"
