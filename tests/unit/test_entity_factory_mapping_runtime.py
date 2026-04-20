"""Coverage tests for entity-factory mapping containers and runtime budgets."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from homeassistant.const import Platform

import custom_components.pawcontrol.entity_factory as entity_factory
from custom_components.pawcontrol.entity_factory import (
    _MIN_OPERATION_DURATION,
    EntityBudget,
    EntityCreationConfig,
    EntityFactory,
    EntityPerformanceMetrics,
    EntityProfileDefinition,
)


def test_entity_creation_config_mapping_behaviour() -> None:
    """Entity creation config should expose stable mapping semantics."""
    config = EntityCreationConfig(
        dog_id="dog-1",
        entity_type="sensor",
        module="feeding",
        profile="standard",
        priority=7,
        coordinator=None,
        platform=Platform.SENSOR,
        performance_impact="low",
        extras={"custom_key": 5},
    )

    assert config["dog_id"] == "dog-1"
    assert config["entity_type"] == "sensor"
    assert config["performance_impact"] == "low"
    assert config["custom_key"] == 5
    assert list(config) == [
        "dog_id",
        "entity_type",
        "module",
        "profile",
        "priority",
        "coordinator",
        "platform",
        "performance_impact",
        "custom_key",
    ]
    assert len(config) == 9
    assert config.as_dict()["custom_key"] == 5


def test_entity_profile_definition_mapping_behaviour() -> None:
    """Entity profile definitions should behave as immutable mappings."""
    profile = EntityProfileDefinition(
        name="Profile",
        description="Desc",
        max_entities=12,
        performance_impact="medium",
        recommended_for="General use",
        platforms=(Platform.SENSOR, Platform.BUTTON),
        priority_threshold=4,
        preferred_modules=("feeding", "walk"),
    )

    assert profile["name"] == "Profile"
    assert profile["platforms"] == (Platform.SENSOR, Platform.BUTTON)
    assert profile["preferred_modules"] == ("feeding", "walk")
    assert list(profile) == [
        "name",
        "description",
        "max_entities",
        "performance_impact",
        "recommended_for",
        "platforms",
        "priority_threshold",
        "preferred_modules",
    ]
    assert len(profile) == 8


def test_entity_performance_metrics_mapping_behaviour() -> None:
    """Performance metrics should provide deterministic mapping export."""
    metrics = EntityPerformanceMetrics(
        profile="standard",
        estimated_entities=10,
        max_entities=12,
        performance_impact="low",
        utilization_percentage=83.3,
        enabled_modules=5,
        total_modules=7,
    )

    assert metrics["profile"] == "standard"
    assert metrics["estimated_entities"] == 10
    assert list(metrics) == [
        "profile",
        "estimated_entities",
        "max_entities",
        "performance_impact",
        "utilization_percentage",
        "enabled_modules",
        "total_modules",
    ]
    assert len(metrics) == 7
    assert metrics.as_dict()["total_modules"] == 7


def test_entity_budget_clamps_capacity_and_tracks_requests() -> None:
    """Entity budget should clamp overflow and track denied/accepted reservations."""
    exhausted = EntityBudget(
        dog_id="dog-1",
        profile="basic",
        capacity=2,
        base_allocation=5,
    )
    assert exhausted.base_allocation == 2
    assert exhausted.remaining == 0
    assert not exhausted.reserve("sensor.denied", priority=2, weight=1)
    assert exhausted.denied_requests == ["sensor.denied|p2"]

    budget = EntityBudget(
        dog_id="dog-1",
        profile="basic",
        capacity=3,
        base_allocation=1,
    )
    assert budget.reserve("sensor.accepted", priority=7, weight=0)
    assert budget.dynamic_allocation == 1
    assert budget.requested_entities == ["sensor.accepted|p7"]

    snapshot = budget.snapshot()
    assert snapshot.dog_id == "dog-1"
    assert snapshot.capacity == 3
    assert snapshot.requested_entities == ("sensor.accepted|p7",)
    assert snapshot.denied_requests == ()
    assert snapshot.recorded_at.tzinfo is not None


def test_entity_factory_init_enforces_min_runtime_floor_after_prewarm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Factory init should restore the minimum floor after a low prewarm value."""

    def _force_low_floor(self: EntityFactory) -> None:
        self._runtime_guard_floor = 0.0

    monkeypatch.setattr(entity_factory.EntityFactory, "_prewarm_caches", _force_low_floor)

    factory = EntityFactory(coordinator=None, prewarm=True)

    assert factory._runtime_guard_floor == pytest.approx(_MIN_OPERATION_DURATION)


def test_entity_factory_prewarm_updates_runtime_guard_metrics_payload() -> None:
    """Prewarm should refresh runtime floor metadata in coordinator performance stats."""
    runtime_data = SimpleNamespace(
        performance_stats={
            "entity_factory_guard_metrics": {
                "baseline_floor": 0.0,
                "samples": 3,
            }
        }
    )
    coordinator = SimpleNamespace(config_entry=SimpleNamespace(runtime_data=runtime_data))
    factory = EntityFactory(coordinator=coordinator, prewarm=False, enforce_min_runtime=True)
    factory._runtime_guard_floor = _MIN_OPERATION_DURATION * 2

    factory._prewarm_caches()

    metrics = runtime_data.performance_stats["entity_factory_guard_metrics"]
    assert metrics["baseline_floor"] >= _MIN_OPERATION_DURATION
    assert metrics["runtime_floor"] >= _MIN_OPERATION_DURATION
    assert metrics["runtime_floor_delta"] >= 0.0
    assert int(metrics["expansions"]) >= 0
    assert int(metrics["contractions"]) >= 0
    assert int(metrics["stable_samples"]) >= 1
