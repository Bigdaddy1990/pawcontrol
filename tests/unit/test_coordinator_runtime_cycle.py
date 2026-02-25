"""Tests for coordinator_runtime classes not covered by test_adaptive_polling.

Covers RuntimeCycleInfo.to_dict, EntityBudgetSnapshot properties,
summarize_entity_budgets, and CoordinatorRuntime.execute_cycle via mocking.
"""

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.pawcontrol.coordinator_runtime import (
    CoordinatorRuntime,
    EntityBudgetSnapshot,
    RuntimeCycleInfo,
    summarize_entity_budgets,
)
from custom_components.pawcontrol.exceptions import UpdateFailed

# ---------------------------------------------------------------------------
# EntityBudgetSnapshot
# ---------------------------------------------------------------------------


class TestEntityBudgetSnapshot:
    """Tests for EntityBudgetSnapshot computed properties."""

    def _make(
        self,
        *,
        capacity: int = 100,
        base_allocation: int = 20,
        dynamic_allocation: int = 10,
        denied_requests: tuple[str, ...] = (),
    ) -> EntityBudgetSnapshot:
        return EntityBudgetSnapshot(
            dog_id="rex",
            profile="standard",
            capacity=capacity,
            base_allocation=base_allocation,
            dynamic_allocation=dynamic_allocation,
            requested_entities=("sensor.a",),
            denied_requests=denied_requests,
            recorded_at=datetime.now(UTC),
        )

    def test_total_allocated(self) -> None:
        snap = self._make(base_allocation=15, dynamic_allocation=5)
        assert snap.total_allocated == 20

    def test_remaining(self) -> None:
        snap = self._make(capacity=50, base_allocation=20, dynamic_allocation=10)
        assert snap.remaining == 20

    def test_remaining_cannot_be_negative(self) -> None:
        snap = self._make(capacity=5, base_allocation=20, dynamic_allocation=0)
        assert snap.remaining == 0

    def test_saturation_normal(self) -> None:
        snap = self._make(capacity=100, base_allocation=50, dynamic_allocation=0)
        assert snap.saturation == pytest.approx(0.5)

    def test_saturation_zero_capacity(self) -> None:
        snap = self._make(capacity=0, base_allocation=0, dynamic_allocation=0)
        assert snap.saturation == 0.0

    def test_saturation_clamped_to_one(self) -> None:
        snap = self._make(capacity=10, base_allocation=15, dynamic_allocation=5)
        assert snap.saturation == 1.0


# ---------------------------------------------------------------------------
# RuntimeCycleInfo
# ---------------------------------------------------------------------------


class TestRuntimeCycleInfo:
    """Tests for RuntimeCycleInfo.to_dict."""

    def _make(
        self,
        *,
        dog_count: int = 3,
        errors: int = 1,
        success_rate: float = 0.667,
        duration: float = 0.5,
        new_interval: float = 120.0,
        error_ratio: float = 0.333,
        success: bool = True,
    ) -> RuntimeCycleInfo:
        return RuntimeCycleInfo(
            dog_count=dog_count,
            errors=errors,
            success_rate=success_rate,
            duration=duration,
            new_interval=new_interval,
            error_ratio=error_ratio,
            success=success,
        )

    def test_to_dict_contains_dog_count(self) -> None:
        info = self._make(dog_count=5)
        result = info.to_dict()
        assert result["dog_count"] == 5

    def test_to_dict_contains_errors(self) -> None:
        info = self._make(errors=2)
        result = info.to_dict()
        assert result["errors"] == 2

    def test_to_dict_success_rate_rounded(self) -> None:
        info = self._make(success_rate=0.6667)
        result = info.to_dict()
        assert result["success_rate"] == pytest.approx(66.67, abs=0.01)

    def test_to_dict_duration_in_ms(self) -> None:
        info = self._make(duration=0.25)
        result = info.to_dict()
        assert result["duration_ms"] == pytest.approx(250.0)

    def test_to_dict_next_interval(self) -> None:
        info = self._make(new_interval=60.5)
        result = info.to_dict()
        assert result["next_interval_s"] == pytest.approx(60.5)

    def test_to_dict_success_flag(self) -> None:
        info_ok = self._make(success=True)
        info_fail = self._make(success=False)
        assert info_ok.to_dict()["success"] is True
        assert info_fail.to_dict()["success"] is False


# ---------------------------------------------------------------------------
# summarize_entity_budgets
# ---------------------------------------------------------------------------


class TestSummarizeEntityBudgets:
    """Tests for the summarize_entity_budgets helper."""

    def _snap(
        self,
        dog_id: str = "rex",
        capacity: int = 100,
        base: int = 30,
        dynamic: int = 10,
        denied: tuple[str, ...] = (),
    ) -> EntityBudgetSnapshot:
        return EntityBudgetSnapshot(
            dog_id=dog_id,
            profile="standard",
            capacity=capacity,
            base_allocation=base,
            dynamic_allocation=dynamic,
            requested_entities=("sensor.a",),
            denied_requests=denied,
            recorded_at=datetime.now(UTC),
        )

    def test_empty_snapshots_returns_zero_summary(self) -> None:
        result = summarize_entity_budgets([])
        assert result["active_dogs"] == 0
        assert result["total_capacity"] == 0
        assert result["average_utilization"] == 0.0

    def test_single_snapshot_utilization(self) -> None:
        snap = self._snap(capacity=100, base=50, dynamic=0)
        result = summarize_entity_budgets([snap])
        assert result["active_dogs"] == 1
        assert result["total_capacity"] == 100
        assert result["total_allocated"] == 50
        assert result["average_utilization"] == pytest.approx(50.0)

    def test_multiple_snapshots_aggregate_capacity(self) -> None:
        snaps = [
            self._snap("dog1", capacity=100, base=30, dynamic=10),
            self._snap("dog2", capacity=200, base=50, dynamic=20),
        ]
        result = summarize_entity_budgets(snaps)
        assert result["active_dogs"] == 2
        assert result["total_capacity"] == 300
        assert result["total_allocated"] == 110

    def test_denied_requests_counted(self) -> None:
        snap = self._snap(denied=("sensor.a", "sensor.b"))
        result = summarize_entity_budgets([snap])
        assert result["denied_requests"] == 2

    def test_peak_utilization_reflects_most_saturated(self) -> None:
        snaps = [
            self._snap("dog1", capacity=100, base=90, dynamic=0),
            self._snap("dog2", capacity=100, base=20, dynamic=0),
        ]
        result = summarize_entity_budgets(snaps)
        assert result["peak_utilization"] == pytest.approx(90.0)

    def test_total_remaining_calculated(self) -> None:
        snaps = [
            self._snap("dog1", capacity=100, base=40, dynamic=10),  # remaining=50
            self._snap("dog2", capacity=200, base=50, dynamic=20),  # remaining=130
        ]
        result = summarize_entity_budgets(snaps)
        assert result["total_remaining"] == 180


# ---------------------------------------------------------------------------
# CoordinatorRuntime.execute_cycle
# ---------------------------------------------------------------------------


class TestCoordinatorRuntimeExecuteCycle:
    """Tests for CoordinatorRuntime.execute_cycle via mocking."""

    def _make_runtime(
        self,
        fetch_result: object = None,
        fetch_error: type[Exception] | None = None,
    ) -> CoordinatorRuntime:
        from custom_components.pawcontrol.coordinator_runtime import (
            AdaptivePollingController,
        )
        from custom_components.pawcontrol.coordinator_support import (
            CoordinatorMetrics,
            DogConfigRegistry,
        )
        from custom_components.pawcontrol.resilience import RetryConfig

        registry = MagicMock(spec=DogConfigRegistry)
        registry.get.return_value = {"dog_id": "rex", "dog_name": "Rex"}

        modules_mock = MagicMock()
        modules_mock.build_tasks.return_value = []

        resilience_mock = MagicMock()

        async def _fake_execute(func, dog_id, **kwargs):
            if fetch_error is not None:
                raise fetch_error("error")
            return fetch_result or {
                "dog_info": {"dog_id": dog_id},
                "status": "online",
            }

        resilience_mock.execute_with_resilience = AsyncMock(side_effect=_fake_execute)

        metrics = MagicMock(spec=CoordinatorMetrics)
        metrics.start_cycle = MagicMock()
        metrics.record_cycle.return_value = (1.0, False)

        polling = AdaptivePollingController(initial_interval_seconds=120.0)

        return CoordinatorRuntime(
            registry=registry,
            modules=modules_mock,
            resilience_manager=resilience_mock,
            retry_config=cast(RetryConfig, MagicMock()),
            metrics=metrics,
            adaptive_polling=polling,
            logger=MagicMock(),
        )

    @pytest.mark.asyncio
    async def test_execute_cycle_raises_when_no_dogs(self) -> None:
        runtime = self._make_runtime()
        with pytest.raises(UpdateFailed, match="No valid dogs"):
            await runtime.execute_cycle([], {}, empty_payload_factory=dict)

    @pytest.mark.asyncio
    async def test_execute_cycle_returns_data_for_dogs(self) -> None:
        runtime = self._make_runtime()
        data, info = await runtime.execute_cycle(
            ["rex"],
            {},
            empty_payload_factory=dict,
        )
        assert "rex" in data
        assert info.dog_count == 1
        assert info.errors == 0

    @pytest.mark.asyncio
    async def test_execute_cycle_raises_when_all_fail(self) -> None:
        from custom_components.pawcontrol.exceptions import NetworkError

        runtime = self._make_runtime(fetch_error=NetworkError)
        runtime._resilience.execute_with_resilience = AsyncMock(
            side_effect=NetworkError("Network error")
        )

        with pytest.raises(UpdateFailed):
            await runtime.execute_cycle(["rex"], {}, empty_payload_factory=dict)

    @pytest.mark.asyncio
    async def test_cycle_info_success_flag_true_on_no_errors(self) -> None:
        runtime = self._make_runtime()
        _data, info = await runtime.execute_cycle(
            ["rex"], {}, empty_payload_factory=dict
        )  # noqa: E501
        assert info.success is True

    @pytest.mark.asyncio
    async def test_cycle_info_contains_dog_count(self) -> None:
        runtime = self._make_runtime()
        _data, info = await runtime.execute_cycle(
            ["rex", "max"], {}, empty_payload_factory=dict
        )
        assert info.dog_count == 2
