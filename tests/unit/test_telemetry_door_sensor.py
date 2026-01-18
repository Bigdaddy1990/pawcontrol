from __future__ import annotations

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
  """Return a runtime data namespace with mutable telemetry containers."""

  return cast(
    PawControlRuntimeData,
    SimpleNamespace(
      performance_stats=performance_stats or {},
      error_history=list(error_history or []),
    ),
  )


def test_record_door_sensor_failure_records_structured_payload(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Door sensor persistence failures should persist structured telemetry."""

  runtime_data = _build_runtime_data()
  recorded_at = datetime(2024, 1, 5, 12, 0, tzinfo=UTC)
  monkeypatch.setattr(
    "custom_components.pawcontrol.telemetry.dt_util.utcnow",
    lambda: recorded_at,
  )

  settings: DoorSensorSettingsPayload = {
    "walk_detection_timeout": 45,
    "minimum_walk_duration": 5,
    "maximum_walk_duration": 90,
    "door_closed_delay": 10,
    "require_confirmation": True,
    "auto_end_walks": False,
    "confidence_threshold": 0.75,
  }

  failure = record_door_sensor_persistence_failure(
    runtime_data,
    dog_id="alpha",
    dog_name="Ada",
    door_sensor="binary_sensor.front_door",
    settings=settings,
    error=ValueError("failed to persist"),
  )

  assert failure is not None
  assert failure["dog_id"] == "alpha"
  assert failure["recorded_at"] == recorded_at.isoformat()
  assert failure["dog_name"] == "Ada"
  assert failure["door_sensor"] == "binary_sensor.front_door"
  assert failure["settings"] == settings
  assert failure["error"] == "failed to persist"

  failures = runtime_data.performance_stats["door_sensor_failures"]
  assert failures == [failure]
  assert runtime_data.performance_stats["door_sensor_failure_count"] == 1
  assert runtime_data.performance_stats["last_door_sensor_failure"] == failure

  summary = runtime_data.performance_stats["door_sensor_failure_summary"]
  assert summary == {
    "alpha": {
      "dog_id": "alpha",
      "dog_name": "Ada",
      "failure_count": 1,
      "last_failure": failure,
    }
  }

  history = cast(list[RuntimeErrorHistoryEntry], runtime_data.error_history)
  assert len(history) == 1
  entry = history[0]
  assert entry["timestamp"] == recorded_at.isoformat()
  assert entry["source"] == "door_sensor_persistence"
  assert entry["dog_id"] == "alpha"
  assert entry["door_sensor"] == "binary_sensor.front_door"
  assert entry["error"] == "failed to persist"


def test_record_door_sensor_failure_enforces_history_limits(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Door sensor failure telemetry should cap failure and error history lists."""

  existing_failures: list[DoorSensorPersistenceFailure] = [
    {
      "dog_id": f"dog-{index}",
      "recorded_at": f"2024-01-{index + 1:02d}T00:00:00",
    }
    for index in range(5)
  ]
  existing_history: list[RuntimeErrorHistoryEntry] = [
    {
      "timestamp": f"2024-01-{day:02d}T00:00:00",
      "source": "door_sensor_persistence",
      "dog_id": f"dog-{day}",
    }
    for day in range(1, 51)
  ]
  existing_summary = {
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
  runtime_data = _build_runtime_data(
    performance_stats={
      "door_sensor_failures": existing_failures.copy(),
      "door_sensor_failure_summary": existing_summary,
    },
    error_history=existing_history.copy(),
  )

  recorded_at = datetime(2024, 2, 1, 9, 30, tzinfo=UTC)
  monkeypatch.setattr(
    "custom_components.pawcontrol.telemetry.dt_util.utcnow",
    lambda: recorded_at,
  )

  failure = record_door_sensor_persistence_failure(
    runtime_data,
    dog_id="omega",
    door_sensor="binary_sensor.back_door",
    error="database offline",
    limit=3,
  )

  assert failure is not None
  assert failure["dog_id"] == "omega"
  assert failure["recorded_at"] == recorded_at.isoformat()
  assert "settings" not in failure

  failures = runtime_data.performance_stats["door_sensor_failures"]
  assert len(failures) == 3
  assert failures[0] == existing_failures[3]
  assert failures[1] == existing_failures[4]
  assert failures[2] == failure
  assert runtime_data.performance_stats["door_sensor_failure_count"] == 3
  assert runtime_data.performance_stats["last_door_sensor_failure"] == failure

  history = cast(list[RuntimeErrorHistoryEntry], runtime_data.error_history)
  assert len(history) == 50
  assert history[0]["timestamp"] == "2024-01-02T00:00:00"
  assert history[-1]["timestamp"] == recorded_at.isoformat()
  assert history[-1]["door_sensor"] == "binary_sensor.back_door"
  assert history[-1]["error"] == "database offline"

  summary = runtime_data.performance_stats["door_sensor_failure_summary"]
  assert summary["dog-3"] == existing_summary["dog-3"]
  assert summary["dog-4"] == existing_summary["dog-4"]
  assert summary["omega"]["failure_count"] == 1
  assert summary["omega"]["dog_id"] == "omega"
  assert summary["omega"]["last_failure"] == failure


def test_record_door_sensor_failure_updates_existing_summary(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """Recording another failure should bump summary counters for the same dog."""

  previous_failure: DoorSensorPersistenceFailure = {
    "dog_id": "alpha",
    "recorded_at": "2024-01-01T00:00:00",
    "dog_name": "Ada",
    "door_sensor": "binary_sensor.front_door",
    "error": "timeout",
  }
  runtime_data = _build_runtime_data(
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

  recorded_at = datetime(2024, 3, 2, 17, 45, tzinfo=UTC)
  monkeypatch.setattr(
    "custom_components.pawcontrol.telemetry.dt_util.utcnow",
    lambda: recorded_at,
  )

  failure = record_door_sensor_persistence_failure(
    runtime_data,
    dog_id="alpha",
    dog_name="Ada",
    door_sensor="binary_sensor.front_door",
    error="validation",
  )

  assert failure is not None
  summary = runtime_data.performance_stats["door_sensor_failure_summary"]
  assert summary["alpha"]["failure_count"] == 3
  assert summary["alpha"]["dog_name"] == "Ada"
  assert summary["alpha"]["last_failure"] == failure

  failures = runtime_data.performance_stats["door_sensor_failures"]
  assert failures[-1] == failure
  assert runtime_data.performance_stats["door_sensor_failure_count"] == len(failures)
