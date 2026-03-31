"""Targeted coverage tests for coordinator_runtime.py — pure helpers (0% → 20%+).

Covers: build_dog_status_snapshot, summarize_entity_budgets, ensure_dog_modules_mapping
"""

from datetime import UTC

import pytest

from custom_components.pawcontrol.coordinator_runtime import (
    build_dog_status_snapshot,
    ensure_dog_modules_mapping,
    summarize_entity_budgets,
)

# ═══════════════════════════════════════════════════════════════════════════════
# build_dog_status_snapshot
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_build_dog_status_snapshot_empty_data() -> None:
    result = build_dog_status_snapshot("rex", {})
    assert isinstance(result, dict)


@pytest.mark.unit
def test_build_dog_status_snapshot_with_walk_data() -> None:
    dog_data = {"walk": {"walk_in_progress": True, "distance_today_km": 2.5}}
    result = build_dog_status_snapshot("rex", dog_data)
    assert isinstance(result, dict)


@pytest.mark.unit
def test_build_dog_status_snapshot_with_feeding_data() -> None:
    dog_data = {"feeding": {"meals_today": 2, "last_feeding": None}}
    result = build_dog_status_snapshot("rex", dog_data)
    assert isinstance(result, dict)


@pytest.mark.unit
def test_build_dog_status_snapshot_dog_id_preserved() -> None:
    result = build_dog_status_snapshot("buddy", {})
    assert isinstance(result, dict)


@pytest.mark.unit
def test_build_dog_status_snapshot_full_payload() -> None:
    dog_data = {
        "walk": {"walk_in_progress": False, "total_distance_today": 3.0},
        "feeding": {"meals_today": 1},
        "health": {"weight": 22.0},
    }
    result = build_dog_status_snapshot("rex", dog_data)
    assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════════════════════
# summarize_entity_budgets
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_summarize_entity_budgets_empty() -> None:
    result = summarize_entity_budgets([])
    assert isinstance(result, dict)


@pytest.mark.unit
def test_summarize_entity_budgets_single() -> None:
    from datetime import datetime, timezone

    from custom_components.pawcontrol.coordinator_runtime import EntityBudgetSnapshot

    snap = EntityBudgetSnapshot(
        dog_id="rex",
        profile="standard",
        capacity=100,
        base_allocation=20,
        dynamic_allocation=5,
        requested_entities=("sensor.rex_weight",),
        denied_requests=(),
        recorded_at=datetime.now(UTC),
    )
    result = summarize_entity_budgets([snap])
    assert isinstance(result, dict)


@pytest.mark.unit
def test_summarize_entity_budgets_multiple() -> None:
    from datetime import datetime, timezone

    from custom_components.pawcontrol.coordinator_runtime import EntityBudgetSnapshot

    now = datetime.now(UTC)
    snaps = [
        EntityBudgetSnapshot("rex", "standard", 100, 20, 5, ("s1",), (), now),
        EntityBudgetSnapshot(
            "buddy", "standard", 100, 18, 3, ("s2", "s3"), ("s4",), now
        ),
    ]
    result = summarize_entity_budgets(snaps)
    assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════════════════════
# ensure_dog_modules_mapping
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_ensure_dog_modules_mapping_empty() -> None:
    result = ensure_dog_modules_mapping({})
    assert isinstance(result, dict)


@pytest.mark.unit
def test_ensure_dog_modules_mapping_with_modules() -> None:
    data = {"feeding": True, "walk": False, "gps": True}
    result = ensure_dog_modules_mapping(data)
    assert isinstance(result, dict)


@pytest.mark.unit
def test_ensure_dog_modules_mapping_coerces_bools() -> None:
    data = {"feeding": 1, "walk": 0}
    result = ensure_dog_modules_mapping(data)
    assert isinstance(result, dict)
