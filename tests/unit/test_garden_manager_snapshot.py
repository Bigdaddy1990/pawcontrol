from __future__ import annotations

from datetime import timedelta
from typing import cast

from custom_components.pawcontrol.garden_manager import (
  GardenActivity,
  GardenActivityPayload,
  GardenActivityType,
  GardenManager,
  GardenSession,
  GardenSessionPayload,
  GardenSessionStatus,
  GardenStats,
)
from custom_components.pawcontrol.types import (
  GardenFavoriteActivity,
  GardenWeeklySummary,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util


def test_build_garden_snapshot_returns_structured_payload(hass: HomeAssistant) -> None:
  """Garden snapshots should expose structured TypedDict payloads."""

  manager = GardenManager(hass, "entry")
  now = dt_util.utcnow()

  active_session = GardenSession(
    session_id="garden-active",
    dog_id="dog",
    dog_name="Buddy",
    start_time=now - timedelta(minutes=10),
    status=GardenSessionStatus.ACTIVE,
  )
  active_session.weather_conditions = "Sunny"
  active_session.temperature = 24.0
  active_session.activities.append(
    GardenActivity(
      activity_type=GardenActivityType.PLAY,
      timestamp=now - timedelta(minutes=5),
      duration_seconds=120,
    )
  )
  active_session.poop_count = 1

  completed_session = GardenSession(
    session_id="garden-complete",
    dog_id="dog",
    dog_name="Buddy",
    start_time=now - timedelta(hours=2),
    end_time=now - timedelta(hours=1, minutes=30),
    status=GardenSessionStatus.COMPLETED,
  )
  completed_session.weather_conditions = "Cloudy"
  completed_session.temperature = 20.0

  manager._active_sessions["dog"] = active_session
  manager._session_history.append(completed_session)

  favorite_activities = [
    cast(GardenFavoriteActivity, {"activity": "play", "count": 2}),
    cast(GardenFavoriteActivity, {"activity": "sniffing", "count": 1}),
  ]
  weekly_summary = cast(
    GardenWeeklySummary,
    {
      "session_count": 2,
      "total_time_minutes": 60.0,
      "poop_events": 2,
      "average_duration": 30.0,
      "updated": now.isoformat(),
    },
  )

  manager._dog_stats["dog"] = GardenStats(
    total_sessions=2,
    total_time_minutes=60.0,
    total_poop_count=2,
    average_session_duration=30.0,
    most_active_time_of_day="morning",
    favorite_activities=favorite_activities,
    total_activities=5,
    weekly_summary=weekly_summary,
    last_garden_visit=now,
  )

  manager._pending_confirmations["confirm"] = {
    "type": "poop_confirmation",
    "dog_id": "dog",
    "session_id": "garden-active",
    "timestamp": now - timedelta(minutes=1),
    "timeout": now + timedelta(minutes=4),
  }

  snapshot = manager.build_garden_snapshot("dog")

  assert snapshot["status"] == "active"
  assert snapshot["active_session"]
  assert snapshot["active_session"]["session_id"] == "garden-active"
  assert snapshot["stats"]["favorite_activities"][0]["activity"] == "play"
  assert snapshot["pending_confirmations"][0]["session_id"] == "garden-active"
  assert snapshot["weather_summary"]
  assert snapshot["weather_summary"]["conditions"] == ["Cloudy", "Sunny"]


def test_garden_activity_payload_roundtrip() -> None:
  """Activity payloads should round-trip through the TypedDict helpers."""

  now = dt_util.utcnow()
  activity = GardenActivity(
    activity_type=GardenActivityType.SNIFFING,
    timestamp=now,
    duration_seconds=45,
    location="rose bush",
    notes="Investigated new scents",
    confirmed=True,
  )

  payload = activity.to_dict()
  assert isinstance(payload, dict)
  assert payload["activity_type"] == "sniffing"

  restored = GardenActivity.from_dict(cast(GardenActivityPayload, payload))
  assert restored.activity_type is GardenActivityType.SNIFFING
  assert restored.duration_seconds == 45
  assert restored.confirmed is True


def test_garden_session_payload_roundtrip() -> None:
  """Session payloads should maintain structured activity lists."""

  now = dt_util.utcnow()
  session = GardenSession(
    session_id="garden-round-trip",
    dog_id="dog",
    dog_name="Buddy",
    start_time=now - timedelta(minutes=15),
    end_time=now,
    status=GardenSessionStatus.COMPLETED,
  )
  session.activities.append(
    GardenActivity(
      activity_type=GardenActivityType.DIGGING,
      timestamp=now - timedelta(minutes=10),
      duration_seconds=120,
    )
  )
  session.total_duration_seconds = 900
  session.poop_count = 0

  payload = session.to_dict()
  assert isinstance(payload, dict)
  assert payload["status"] == "completed"
  assert payload["activities"][0]["activity_type"] == "digging"

  restored = GardenSession.from_dict(cast(GardenSessionPayload, payload))
  assert restored.session_id == "garden-round-trip"
  assert restored.activities[0].activity_type is GardenActivityType.DIGGING
  assert restored.total_duration_seconds == 900
