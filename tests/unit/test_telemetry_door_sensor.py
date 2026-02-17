from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import pytest

from custom_components.pawcontrol.telemetry import (
    record_door_sensor_persistence_failure,
)
from custom_components.pawcontrol.types import (
    DoorSensorPersistenceFailure,
    DoorSensorSettingsPayload,
    PawControlRuntimeData,
    RuntimeErrorHistoryEntry,
)


def _build_runtime_data(
    *,
    performance_stats: dict[str, object] | None = None,
    error_history: list[RuntimeErrorHistoryEntry] | None = None,
) -> PawControlRuntimeData:
    """Return a runtime data namespace with mutable telemetry containers."""  # noqa: E111

    return cast(  # noqa: E111
        PawControlRuntimeData,
        SimpleNamespace(
            performance_stats=performance_stats or {},
            error_history=list(error_history or []),
        ),
    )


def test_record_door_sensor_failure_records_structured_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Door sensor persistence failures should persist structured telemetry."""  # noqa: E111

    runtime_data = _build_runtime_data()  # noqa: E111
    recorded_at = datetime(2024, 1, 5, 12, 0, tzinfo=UTC)  # noqa: E111
    monkeypatch.setattr(  # noqa: E111
        "custom_components.pawcontrol.telemetry.dt_util.utcnow",
        lambda: recorded_at,
    )

    settings: DoorSensorSettingsPayload = {  # noqa: E111
        "walk_detection_timeout": 45,
        "minimum_walk_duration": 5,
        "maximum_walk_duration": 90,
        "door_closed_delay": 10,
        "require_confirmation": True,
        "auto_end_walks": False,
        "confidence_threshold": 0.75,
    }

    failure = record_door_sensor_persistence_failure(  # noqa: E111
        runtime_data,
        dog_id="alpha",
        dog_name="Ada",
        door_sensor="binary_sensor.front_door",
        settings=settings,
        error=ValueError("failed to persist"),
    )

    assert failure is not None  # noqa: E111
    assert failure["dog_id"] == "alpha"  # noqa: E111
    assert failure["recorded_at"] == recorded_at.isoformat()  # noqa: E111
    assert failure["dog_name"] == "Ada"  # noqa: E111
    assert failure["door_sensor"] == "binary_sensor.front_door"  # noqa: E111
    assert failure["settings"] == settings  # noqa: E111
    assert failure["error"] == "failed to persist"  # noqa: E111

    failures = runtime_data.performance_stats["door_sensor_failures"]  # noqa: E111
    assert failures == [failure]  # noqa: E111
    assert runtime_data.performance_stats["door_sensor_failure_count"] == 1  # noqa: E111
    assert runtime_data.performance_stats["last_door_sensor_failure"] == failure  # noqa: E111

    summary = runtime_data.performance_stats["door_sensor_failure_summary"]  # noqa: E111
    assert summary == {  # noqa: E111
        "alpha": {
            "dog_id": "alpha",
            "dog_name": "Ada",
            "failure_count": 1,
            "last_failure": failure,
        }
    }

    history = cast(list[RuntimeErrorHistoryEntry], runtime_data.error_history)  # noqa: E111
    assert len(history) == 1  # noqa: E111
    entry = history[0]  # noqa: E111
    assert entry["timestamp"] == recorded_at.isoformat()  # noqa: E111
    assert entry["source"] == "door_sensor_persistence"  # noqa: E111
    assert entry["dog_id"] == "alpha"  # noqa: E111
    assert entry["door_sensor"] == "binary_sensor.front_door"  # noqa: E111
    assert entry["error"] == "failed to persist"  # noqa: E111


def test_record_door_sensor_failure_enforces_history_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Door sensor failure telemetry should cap failure and error history lists."""  # noqa: E111

    existing_failures: list[DoorSensorPersistenceFailure] = [  # noqa: E111
        {
            "dog_id": f"dog-{index}",
            "recorded_at": f"2024-01-{index + 1:02d}T00:00:00",
        }
        for index in range(5)
    ]
    existing_history: list[RuntimeErrorHistoryEntry] = [  # noqa: E111
        {
            "timestamp": f"2024-01-{day:02d}T00:00:00",
            "source": "door_sensor_persistence",
            "dog_id": f"dog-{day}",
        }
        for day in range(1, 51)
    ]
    existing_summary = {  # noqa: E111
        "dog-3": {
            "dog_id": "dog-3",
            "failure_count": 2,
            "last_failure": existing_failures[3],
        },
        "dog-4": {
            "dog_id": "dog-4",
            "dog_name": "Zoe",
            "failure_count": 5,
            "last_failure": existing_failures[4],
        },
    }
    runtime_data = _build_runtime_data(  # noqa: E111
        performance_stats={
            "door_sensor_failures": existing_failures.copy(),
            "door_sensor_failure_summary": existing_summary,
        },
        error_history=existing_history.copy(),
    )

    recorded_at = datetime(2024, 2, 1, 9, 30, tzinfo=UTC)  # noqa: E111
    monkeypatch.setattr(  # noqa: E111
        "custom_components.pawcontrol.telemetry.dt_util.utcnow",
        lambda: recorded_at,
    )

    failure = record_door_sensor_persistence_failure(  # noqa: E111
        runtime_data,
        dog_id="omega",
        door_sensor="binary_sensor.back_door",
        error="database offline",
        limit=3,
    )

    assert failure is not None  # noqa: E111
    assert failure["dog_id"] == "omega"  # noqa: E111
    assert failure["recorded_at"] == recorded_at.isoformat()  # noqa: E111
    assert "settings" not in failure  # noqa: E111

    failures = runtime_data.performance_stats["door_sensor_failures"]  # noqa: E111
    assert len(failures) == 3  # noqa: E111
    assert failures[0] == existing_failures[3]  # noqa: E111
    assert failures[1] == existing_failures[4]  # noqa: E111
    assert failures[2] == failure  # noqa: E111
    assert runtime_data.performance_stats["door_sensor_failure_count"] == 3  # noqa: E111
    assert runtime_data.performance_stats["last_door_sensor_failure"] == failure  # noqa: E111

    history = cast(list[RuntimeErrorHistoryEntry], runtime_data.error_history)  # noqa: E111
    assert len(history) == 50  # noqa: E111
    assert history[0]["timestamp"] == "2024-01-02T00:00:00"  # noqa: E111
    assert history[-1]["timestamp"] == recorded_at.isoformat()  # noqa: E111
    assert history[-1]["door_sensor"] == "binary_sensor.back_door"  # noqa: E111
    assert history[-1]["error"] == "database offline"  # noqa: E111

    summary = runtime_data.performance_stats["door_sensor_failure_summary"]  # noqa: E111
    assert summary["dog-3"] == existing_summary["dog-3"]  # noqa: E111
    assert summary["dog-4"] == existing_summary["dog-4"]  # noqa: E111
    assert summary["omega"]["failure_count"] == 1  # noqa: E111
    assert summary["omega"]["dog_id"] == "omega"  # noqa: E111
    assert summary["omega"]["last_failure"] == failure  # noqa: E111


def test_record_door_sensor_failure_updates_existing_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recording another failure should bump summary counters for the same dog."""  # noqa: E111

    previous_failure: DoorSensorPersistenceFailure = {  # noqa: E111
        "dog_id": "alpha",
        "recorded_at": "2024-01-01T00:00:00",
        "dog_name": "Ada",
        "door_sensor": "binary_sensor.front_door",
        "error": "timeout",
    }
    runtime_data = _build_runtime_data(  # noqa: E111
        performance_stats={
            "door_sensor_failures": [previous_failure],
            "door_sensor_failure_summary": {
                "alpha": {
                    "dog_id": "alpha",
                    "dog_name": "Ada",
                    "failure_count": 2,
                    "last_failure": previous_failure,
                }
            },
        }
    )

    recorded_at = datetime(2024, 3, 2, 17, 45, tzinfo=UTC)  # noqa: E111
    monkeypatch.setattr(  # noqa: E111
        "custom_components.pawcontrol.telemetry.dt_util.utcnow",
        lambda: recorded_at,
    )

    failure = record_door_sensor_persistence_failure(  # noqa: E111
        runtime_data,
        dog_id="alpha",
        dog_name="Ada",
        door_sensor="binary_sensor.front_door",
        error="validation",
    )

    assert failure is not None  # noqa: E111
    summary = runtime_data.performance_stats["door_sensor_failure_summary"]  # noqa: E111
    assert summary["alpha"]["failure_count"] == 3  # noqa: E111
    assert summary["alpha"]["dog_name"] == "Ada"  # noqa: E111
    assert summary["alpha"]["last_failure"] == failure  # noqa: E111

    failures = runtime_data.performance_stats["door_sensor_failures"]  # noqa: E111
    assert failures[-1] == failure  # noqa: E111
    assert runtime_data.performance_stats["door_sensor_failure_count"] == len(failures)  # noqa: E111
