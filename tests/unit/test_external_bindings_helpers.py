"""Tests for lightweight helpers in ``external_bindings``."""

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.pawcontrol import external_bindings
from custom_components.pawcontrol.const import DOMAIN


def test_domain_store_initializes_and_repairs_domain_bucket() -> None:
    """The domain bucket should always be a mutable mapping."""
    hass = SimpleNamespace(data={})

    store = external_bindings._domain_store(hass)

    assert store == {}
    assert hass.data[DOMAIN] is store

    hass.data[DOMAIN] = "broken"
    repaired = external_bindings._domain_store(hass)
    assert repaired == {}
    assert isinstance(hass.data[DOMAIN], dict)


def test_extract_coords_handles_valid_and_invalid_payloads() -> None:
    """Coordinate extraction should coerce numeric values and reject invalid data."""

    def _state(attributes: Any) -> SimpleNamespace:
        return SimpleNamespace(attributes=attributes)

    state = _state({
        "latitude": 50,
        "longitude": 8.5,
        "gps_accuracy": 12,
        "altitude": 99,
    })

    assert external_bindings._extract_coords(state) == (50.0, 8.5, 12.0, 99.0)
    invalid = _state({"latitude": "x", "longitude": 1})
    assert external_bindings._extract_coords(invalid) == (None, None, None, None)
    assert external_bindings._extract_coords(_state(None)) == (None, None, None, None)


def test_haversine_returns_zero_for_identical_points() -> None:
    """Distance helper should be deterministic for equal coordinates."""
    assert external_bindings._haversine_m(10.0, 20.0, 10.0, 20.0) == 0.0


@pytest.mark.asyncio
async def test_async_unload_external_bindings_cleans_up_registered_bindings() -> None:
    """Unload should unsubscribe and cancel pending tasks."""
    unsub_called = False

    def _unsub() -> None:
        nonlocal unsub_called
        unsub_called = True

    task = asyncio.create_task(asyncio.sleep(5))
    binding = external_bindings._Binding(unsub=_unsub, task=task)

    hass = SimpleNamespace(
        data={DOMAIN: {external_bindings._STORE_KEY: {"entry-id": {"dog": binding}}}}
    )
    entry = SimpleNamespace(entry_id="entry-id")

    await external_bindings.async_unload_external_bindings(hass, entry)

    assert unsub_called is True
    assert task.cancelling() > 0
    assert "entry-id" not in hass.data[DOMAIN][external_bindings._STORE_KEY]
