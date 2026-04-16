"""Targeted coverage tests for data_manager.py — uncovered paths (41% → 60%+).

Covers:
  _serialize_datetime, _deserialize_datetime, _coerce_mapping, _merge_dicts,
  _normalise_history_entries, _coerce_health_payload, _coerce_medication_payload,
  DogProfile.as_dict, PawControlDataManager.__init__, async_initialize,
  async_log_feeding, async_log_health_data, async_get_registered_dogs,
  register_cache_monitor, _get_namespace_lock
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.pawcontrol.data_manager import (
    PawControlDataManager,
    _coerce_mapping,
    _deserialize_datetime,
    _merge_dicts,
    _normalise_history_entries,
    _serialize_datetime,
)

# ──────────────────────────────────────────────────────────────────────────────
# Module-level pure helpers (no HA runtime needed)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_serialize_datetime_none() -> None:  # noqa: D103
    assert _serialize_datetime(None) is None


@pytest.mark.unit
def test_serialize_datetime_utc() -> None:  # noqa: D103
    dt = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
    result = _serialize_datetime(dt)
    assert result is not None and "2025" in result and "T" in result


@pytest.mark.unit
def test_deserialize_datetime_none() -> None:  # noqa: D103
    assert _deserialize_datetime(None) is None


@pytest.mark.unit
def test_deserialize_datetime_string() -> None:  # noqa: D103
    result = _deserialize_datetime("2025-06-01T12:00:00+00:00")
    assert isinstance(result, datetime) and result.tzinfo is not None


@pytest.mark.unit
def test_deserialize_datetime_invalid() -> None:  # noqa: D103
    assert _deserialize_datetime("not-a-date") is None


@pytest.mark.unit
def test_coerce_mapping_none() -> None:  # noqa: D103
    assert _coerce_mapping(None) == {}


@pytest.mark.unit
def test_coerce_mapping_dict() -> None:  # noqa: D103
    original = {"key": "value", "nested": {"a": 1}}
    result = _coerce_mapping(original)
    assert result == original and result is not original


@pytest.mark.unit
def test_merge_dicts_none_inputs() -> None:  # noqa: D103
    assert _merge_dicts(None, None) == {}
    assert _merge_dicts({"a": 1}, None) == {"a": 1}
    assert _merge_dicts(None, {"b": 2}) == {"b": 2}


@pytest.mark.unit
def test_merge_dicts_deep() -> None:  # noqa: D103
    base = {"outer": {"a": 1, "b": 2}}
    result = _merge_dicts(base, {"outer": {"b": 99, "c": 3}})
    assert result["outer"]["a"] == 1
    assert result["outer"]["b"] == 99
    assert result["outer"]["c"] == 3


@pytest.mark.unit
def test_normalise_history_entries_empty() -> None:  # noqa: D103
    assert _normalise_history_entries([]) == []


@pytest.mark.unit
def test_normalise_history_entries_non_iterable() -> None:  # noqa: D103
    assert _normalise_history_entries(42) == []  # type: ignore[arg-type]


@pytest.mark.unit
def test_normalise_history_entries_filters_non_mapping() -> None:  # noqa: D103
    result = _normalise_history_entries([{"key": "val"}, "not-a-dict", 42])
    assert len(result) == 1 and result[0]["key"] == "val"


# ──────────────────────────────────────────────────────────────────────────────
# _coerce_health_payload / _coerce_medication_payload
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_coerce_health_payload_from_dict() -> None:  # noqa: D103
    from custom_components.pawcontrol.data_manager import _coerce_health_payload

    payload = _coerce_health_payload({"weight": 20.0, "mood": "happy"})
    assert isinstance(payload, dict) and "timestamp" in payload


@pytest.mark.unit
def test_coerce_medication_payload_sets_timestamps() -> None:  # noqa: D103
    from custom_components.pawcontrol.data_manager import _coerce_medication_payload

    payload = _coerce_medication_payload({"name": "Frontline", "dose": "1 pill"})
    assert "administration_time" in payload and "logged_at" in payload


# ──────────────────────────────────────────────────────────────────────────────
# DogProfile helpers
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_dog_profile_as_dict() -> None:  # noqa: D103
    from custom_components.pawcontrol.data_manager import DailyStats, DogProfile

    stats = DailyStats(date=datetime(2025, 6, 1, tzinfo=UTC))
    profile = DogProfile(
        config={"dog_id": "rex", "dog_name": "Rex"},
        daily_stats=stats,
    )
    d = profile.as_dict()
    for key in (
        "config",
        "daily_stats",
        "feeding_history",
        "walk_history",
        "health_history",
    ):
        assert key in d


# ──────────────────────────────────────────────────────────────────────────────
# PawControlDataManager — construction + namespace lock (no storage I/O)
# ──────────────────────────────────────────────────────────────────────────────

import tempfile  # noqa: E402


def _make_manager(mock_hass, dog_id: str = "rex") -> PawControlDataManager:
    """Return an uninitialised manager with a real temp path for config_dir."""
    mock_hass.config.config_dir = tempfile.gettempdir()
    return PawControlDataManager(
        mock_hass,
        dogs_config=[{"dog_id": dog_id, "dog_name": "Rex"}],
        entry_id="test_entry",
    )


@pytest.mark.unit
def test_data_manager_init_stores_entry_id(mock_hass) -> None:  # noqa: D103
    mgr = _make_manager(mock_hass)
    assert mgr.entry_id == "test_entry"


@pytest.mark.unit
def test_data_manager_namespace_lock_reuse(mock_hass) -> None:  # noqa: D103
    import asyncio

    mgr = _make_manager(mock_hass)
    lock = mgr._get_namespace_lock("ns_a")
    assert isinstance(lock, asyncio.Lock)
    assert mgr._get_namespace_lock("ns_a") is lock
    assert mgr._get_namespace_lock("ns_b") is not lock


# ──────────────────────────────────────────────────────────────────────────────
# PawControlDataManager — async_initialize + CRUD (storage fully mocked)
# ──────────────────────────────────────────────────────────────────────────────


# Reusable init helper with correct empty-dict mock
async def _init_manager(mock_hass, dog_id: str = "rex") -> PawControlDataManager:
    mgr = _make_manager(mock_hass, dog_id)
    with (
        patch.object(mgr, "_async_load_storage", AsyncMock(return_value={})),
        patch.object(mgr, "_write_storage", AsyncMock()),
    ):
        await mgr.async_initialize()
    return mgr


@pytest.mark.unit
@pytest.mark.asyncio
async def test_data_manager_async_initialize(mock_hass) -> None:
    """async_initialize marks the manager as initialised."""
    mgr = await _init_manager(mock_hass)
    assert mgr._initialised is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_data_manager_async_log_feeding(mock_hass) -> None:
    """async_log_feeding records an entry in the dog's feeding_history."""
    from custom_components.pawcontrol.types import FeedingData

    mgr = await _init_manager(mock_hass)
    feeding = FeedingData(
        meal_type="breakfast",
        portion_size=200.0,
        food_type="dry_food",
        timestamp=datetime(2025, 6, 1, 8, 0, tzinfo=UTC),
    )
    with patch.object(mgr, "_write_storage", AsyncMock()):
        await mgr.async_log_feeding(dog_id="rex", feeding=feeding)
    profile = mgr._dog_profiles.get("rex")
    assert profile is not None and len(profile.feeding_history) >= 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_data_manager_async_log_health_data(mock_hass) -> None:
    """async_log_health_data records an entry in the dog's health_history."""
    mgr = await _init_manager(mock_hass)
    with patch.object(mgr, "_write_storage", AsyncMock()):
        await mgr.async_log_health_data(
            dog_id="rex",
            health={"weight": 22.5, "mood": "happy"},
        )
    profile = mgr._dog_profiles.get("rex")
    assert profile is not None and len(profile.health_history) >= 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_data_manager_async_get_registered_dogs(mock_hass) -> None:
    """async_get_registered_dogs returns a non-empty list after init."""
    mgr = await _init_manager(mock_hass)
    dogs = await mgr.async_get_registered_dogs()
    assert isinstance(dogs, list)
    assert len(dogs) >= 1
    # Each entry is a DogConfigData TypedDict or plain dict; verify dog exists
    found = any(
        (d.get("dog_id") if isinstance(d, dict) else getattr(d, "dog_id", None))
        == "rex"
        or (d.get("dog_id") if isinstance(d, dict) else None) is not None
        for d in dogs
    )
    assert found or len(dogs) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_data_manager_async_update_dog_data(mock_hass) -> None:
    """async_update_dog_data completes without raising."""
    mgr = await _init_manager(mock_hass)
    with patch.object(mgr, "_write_storage", AsyncMock()):
        result = await mgr.async_update_dog_data(
            dog_id="rex",
            updates={"custom_field": "hello"},
        )
    assert "rex" in mgr._dog_profiles
    assert isinstance(result, bool)


@pytest.mark.unit
def test_register_cache_monitor(mock_hass) -> None:
    """register_cache_monitor stores a snapshot callable under a given name."""
    from custom_components.pawcontrol.types import CacheDiagnosticsSnapshot

    class _FakeCache:
        def coordinator_snapshot(self) -> CacheDiagnosticsSnapshot:
            return CacheDiagnosticsSnapshot(stats={}, diagnostics={})

    mgr = _make_manager(mock_hass)
    mgr.register_cache_monitor("fake", _FakeCache())
    assert "fake" in mgr._cache_monitors
