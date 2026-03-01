"""Unit tests for external entity binding helpers."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.external_bindings import (
    _STORE_KEY,
    _Binding,
    _domain_store,
    _extract_coords,
    _haversine_m,
    async_setup_external_bindings,
    async_unload_external_bindings,
)


def test_domain_store_repairs_non_mapping_domain_bucket() -> None:
    """_domain_store should normalize DOMAIN storage to a dictionary."""
    hass = SimpleNamespace(data={DOMAIN: "invalid"})

    store = _domain_store(hass)

    assert isinstance(store, dict)
    assert hass.data[DOMAIN] == {}


def test_extract_coords_handles_mapping_and_invalid_payloads() -> None:
    """Coordinate extraction should parse numeric attrs and reject invalid values."""
    state_ok = SimpleNamespace(
        attributes={
            "latitude": 52.5,
            "longitude": 13.4,
            "gps_accuracy": 8,
            "altitude": 34,
        }
    )
    state_bad = SimpleNamespace(attributes={"latitude": "52.5", "longitude": 13.4})

    assert _extract_coords(state_ok) == (52.5, 13.4, 8.0, 34.0)
    assert _extract_coords(state_bad) == (None, None, None, None)
    assert _extract_coords(SimpleNamespace(attributes=None)) == (None, None, None, None)


def test_haversine_returns_zero_for_same_coordinates() -> None:
    """Haversine distance should be zero for identical coordinate pairs."""
    assert _haversine_m(52.5, 13.4, 52.5, 13.4) == 0.0


@pytest.mark.asyncio
async def test_async_setup_external_bindings_exits_without_gps_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setup should no-op when runtime data has no GPS manager available."""
    hass = SimpleNamespace(data={})
    entry = SimpleNamespace(entry_id="entry-1", data={"dogs": []})
    runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(gps_geofence_manager=None),
        gps_geofence_manager=None,
    )

    monkeypatch.setattr(
        "custom_components.pawcontrol.external_bindings.require_runtime_data",
        lambda *_: runtime_data,
    )

    await async_setup_external_bindings(hass, entry)

    assert _STORE_KEY not in hass.data.get(DOMAIN, {})


@pytest.mark.asyncio
async def test_async_unload_external_bindings_unsubscribes_and_cancels() -> None:
    """Unload should call unsub handlers and cancel outstanding tasks."""
    unsub = MagicMock()
    task = MagicMock()
    task.done.return_value = False
    task.cancel = MagicMock()

    hass = SimpleNamespace(
        data={
            DOMAIN: {
                _STORE_KEY: {
                    "entry-1": {
                        "dog-1": _Binding(unsub=unsub, task=task),
                    }
                }
            }
        }
    )
    entry = SimpleNamespace(entry_id="entry-1")

    await async_unload_external_bindings(hass, entry)

    unsub.assert_called_once_with()
    task.cancel.assert_called_once_with()
    assert "entry-1" not in hass.data[DOMAIN][_STORE_KEY]
