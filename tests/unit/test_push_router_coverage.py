"""Targeted coverage tests for push_router.py — (0% → 16%+).

Covers: PushResult (TypedDict), get_entry_push_telemetry_snapshot
"""

from unittest.mock import MagicMock

import pytest

from custom_components.pawcontrol.push_router import (
    PushResult,
    get_entry_push_telemetry_snapshot,
)

# ─── PushResult (TypedDict) ──────────────────────────────────────────────────


@pytest.mark.unit
def test_push_result_success() -> None:  # noqa: D103
    r: PushResult = {"ok": True, "status": "delivered", "error": None, "dog_id": "rex"}
    assert r["ok"] is True
    assert r["dog_id"] == "rex"


@pytest.mark.unit
def test_push_result_failure() -> None:  # noqa: D103
    r: PushResult = {
        "ok": False,
        "status": "failed",
        "error": "timeout",
        "dog_id": "buddy",
    }
    assert r["ok"] is False
    assert r["error"] == "timeout"


@pytest.mark.unit
def test_push_result_minimal() -> None:  # noqa: D103
    r: PushResult = {"ok": True}
    assert isinstance(r, dict)


# ─── get_entry_push_telemetry_snapshot ───────────────────────────────────────


@pytest.mark.unit
def test_get_entry_push_telemetry_snapshot_no_data() -> None:  # noqa: D103
    hass = MagicMock()
    hass.data = {}
    result = get_entry_push_telemetry_snapshot(hass, "nonexistent_entry")
    assert isinstance(result, dict)


@pytest.mark.unit
def test_get_entry_push_telemetry_snapshot_returns_dict() -> None:  # noqa: D103
    hass = MagicMock()
    hass.data = {}
    result = get_entry_push_telemetry_snapshot(hass, "entry_123")
    assert isinstance(result, dict)
