"""Tests for helper utilities."""

from __future__ import annotations

from typing import Any

import pytest
from custom_components.pawcontrol.helpers import PawControlDataStorage


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
