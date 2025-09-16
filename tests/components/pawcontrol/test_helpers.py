"""Tests for helper utilities."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from custom_components.pawcontrol.helpers import PawControlDataStorage
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


class _DummyCache:
    """Simple in-memory cache stand-in for tests."""

    def __init__(self) -> None:
        self.values: dict[str, Any] = {}

    async def get(self, key: str, default: Any = None) -> Any:
        """Return a cached value if present."""

        return self.values.get(key, default)

    async def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        """Store a value in the cache."""

        self.values[key] = value


@pytest.mark.asyncio
async def test_async_load_all_data_uses_cached_empty_payload() -> None:
    """An empty payload stored in the cache should be returned without reload."""

    storage = object.__new__(PawControlDataStorage)
    storage._cache = _DummyCache()  # type: ignore[attr-defined]
    storage._stores = {"test": object()}  # type: ignore[attr-defined]

    called = False

    async def fake_loader(store_key: str) -> dict[str, Any]:
        nonlocal called
        called = True
        return {store_key: "loaded"}

    storage._load_store_data_cached = fake_loader  # type: ignore[attr-defined]

    await storage._cache.set("all_data", {})

    result = await PawControlDataStorage.async_load_all_data(storage)

    assert result == {}
    assert called is False


@pytest.mark.asyncio
async def test_async_load_data_starts_event_processor_on_failure(monkeypatch) -> None:
    """Ensure the event processor starts even when initial loading fails."""

    hass = MagicMock(spec=HomeAssistant)
    config_entry = MagicMock(spec=ConfigEntry)
    config_entry.data = {}

    storage = MagicMock()
    storage.async_load_all_data = AsyncMock(side_effect=RuntimeError("load failed"))

    created_coroutines: list[Coroutine[Any, Any, Any]] = []
    sentinel_task = MagicMock(spec=asyncio.Task)
    sentinel_task.done.return_value = False

    def _capture_task(coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        created_coroutines.append(coro)
        return sentinel_task  # type: ignore[return-value]

    monkeypatch.setattr(
        "custom_components.pawcontrol.helpers.asyncio.create_task",
        _capture_task,
    )

    with patch(
        "custom_components.pawcontrol.helpers.PawControlDataStorage",
        return_value=storage,
    ):
        data = PawControlData(hass, config_entry)
        await data.async_load_data()

    storage.async_load_all_data.assert_awaited_once()
    assert data._event_task is sentinel_task
    assert len(created_coroutines) == 1
    assert set(data._data.keys()) == {
        "walks",
        "feedings",
        "health",
        "routes",
        "statistics",
    }
