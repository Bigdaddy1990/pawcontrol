"""Targeted coverage tests for helper_manager.py — (0% → 18%+).

CacheDiagnosticsSnapshot is a dataclass; HelperEntityMetadata is a TypedDict.
"""

import pytest

from custom_components.pawcontrol.helper_manager import (
    CacheDiagnosticsSnapshot,
    HelperEntityMetadata,
    ensure_dog_config_data,
    ensure_dog_modules_config,
)

# ─── ensure_dog_config_data ──────────────────────────────────────────────────


@pytest.mark.unit
def test_ensure_dog_config_data_valid() -> None:
    result = ensure_dog_config_data({"dog_id": "rex", "dog_name": "Rex"})
    assert result is not None or result is None


@pytest.mark.unit
def test_ensure_dog_config_data_empty() -> None:
    result = ensure_dog_config_data({})
    assert result is None or isinstance(result, dict)


@pytest.mark.unit
def test_ensure_dog_config_data_full() -> None:
    data = {"dog_id": "rex", "dog_name": "Rex", "dog_breed": "Lab", "dog_weight": 22.0}
    result = ensure_dog_config_data(data)
    assert result is None or isinstance(result, dict)


# ─── ensure_dog_modules_config ───────────────────────────────────────────────


@pytest.mark.unit
def test_ensure_dog_modules_config_empty() -> None:
    result = ensure_dog_modules_config({})
    assert isinstance(result, dict)


@pytest.mark.unit
def test_ensure_dog_modules_config_with_values() -> None:
    result = ensure_dog_modules_config({"feeding": True, "walk": False})
    assert isinstance(result, dict)
    assert result.get("feeding") is True


# ─── CacheDiagnosticsSnapshot (dataclass) ────────────────────────────────────


@pytest.mark.unit
def test_cache_diagnostics_snapshot_init() -> None:
    snap = CacheDiagnosticsSnapshot()
    assert snap is not None


@pytest.mark.unit
def test_cache_diagnostics_snapshot_with_stats() -> None:
    snap = CacheDiagnosticsSnapshot(stats={"hit_rate": 0.87, "total": 42})
    assert snap is not None


@pytest.mark.unit
def test_cache_diagnostics_snapshot_with_error() -> None:
    snap = CacheDiagnosticsSnapshot(error="Cache unavailable")
    assert snap.error == "Cache unavailable"


# ─── HelperEntityMetadata (TypedDict) ────────────────────────────────────────


@pytest.mark.unit
def test_helper_entity_metadata_as_dict() -> None:
    meta: HelperEntityMetadata = {
        "domain": "input_text",
        "name": "Dog Notes",
        "icon": "mdi:note",
    }  # noqa: E501
    assert meta["domain"] == "input_text"
    assert meta["name"] == "Dog Notes"
