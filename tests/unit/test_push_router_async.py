"""Async coverage tests for push GPS router behavior."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.pawcontrol import push_router
from custom_components.pawcontrol.const import CONF_DOGS, CONF_GPS_SOURCE


def _entry(*, source: str = "webhook") -> SimpleNamespace:
    return SimpleNamespace(
        entry_id="entry-1",
        options={},
        data={
            CONF_DOGS: [
                {
                    "dog_id": "dog-1",
                    "gps_config": {CONF_GPS_SOURCE: source},
                }
            ]
        },
    )


@pytest.mark.asyncio
async def test_async_process_gps_push_rejects_payload_and_missing_dog_id() -> None:
    """Large payloads and missing IDs should be rejected with telemetry updates."""
    hass = SimpleNamespace(data={})
    entry = _entry()

    result = await push_router.async_process_gps_push(
        hass,
        entry,
        payload={"dog_id": "dog-1"},
        source="webhook",
        raw_size=10**9,
    )

    assert result == {
        "ok": False,
        "status": 413,
        "error": "payload_too_large",
        "dog_id": "unknown",
    }

    result = await push_router.async_process_gps_push(
        hass,
        entry,
        payload={"latitude": 1.0, "longitude": 2.0},
        source="webhook",
    )
    assert result["error"] == "missing_dog_id"


@pytest.mark.asyncio
async def test_async_process_gps_push_rejects_source_mismatch_and_nonce_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mismatched source and replayed nonce should be blocked."""
    hass = SimpleNamespace(data={})
    entry = _entry(source="mqtt")

    mismatch = await push_router.async_process_gps_push(
        hass,
        entry,
        payload={"dog_id": "dog-1", "latitude": 1.0, "longitude": 2.0},
        source="webhook",
    )
    assert mismatch["error"] == "gps_source_mismatch"

    entry = _entry(source="webhook")
    runtime = SimpleNamespace(
        coordinator=SimpleNamespace(
            gps_geofence_manager=SimpleNamespace(
                async_add_gps_point=AsyncMock(return_value=True)
            ),
            async_patch_gps_update=AsyncMock(),
            async_refresh_dog=AsyncMock(),
        ),
        gps_geofence_manager=None,
    )

    monkeypatch.setattr(
        push_router, "require_runtime_data", lambda _hass, _entry: runtime
    )

    first = await push_router.async_process_gps_push(
        hass,
        entry,
        payload={"dog_id": "dog-1", "latitude": 1.0, "longitude": 2.0},
        source="webhook",
        nonce="abc",
    )
    replay = await push_router.async_process_gps_push(
        hass,
        entry,
        payload={"dog_id": "dog-1", "latitude": 1.0, "longitude": 2.0},
        source="webhook",
        nonce="abc",
    )

    assert first["ok"] is True
    assert replay["error"] == "replay_nonce"


@pytest.mark.asyncio
async def test_async_process_gps_push_accepts_valid_payload_and_patches_coordinator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Valid payload should call GPS manager and coordinator patch hook."""
    hass = SimpleNamespace(data={})
    entry = _entry(source="entity")
    gps_manager = SimpleNamespace(async_add_gps_point=AsyncMock(return_value=True))
    coordinator = SimpleNamespace(
        gps_geofence_manager=None,
        async_patch_gps_update=AsyncMock(),
        async_refresh_dog=AsyncMock(),
    )
    runtime = SimpleNamespace(coordinator=coordinator, gps_geofence_manager=gps_manager)
    monkeypatch.setattr(
        push_router, "require_runtime_data", lambda _hass, _entry: runtime
    )

    result = await push_router.async_process_gps_push(
        hass,
        entry,
        payload={
            "dog_id": "dog-1",
            "latitude": 10.0,
            "longitude": 20.0,
            "altitude": 1,
            "accuracy": 2,
            "timestamp": "2025-01-01T01:02:03+00:00",
        },
        source="entity",
    )

    assert result == {"ok": True, "status": 200, "dog_id": "dog-1"}
    gps_manager.async_add_gps_point.assert_awaited_once()
    coordinator.async_patch_gps_update.assert_awaited_once_with("dog-1")
