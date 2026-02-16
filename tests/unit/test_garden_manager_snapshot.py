from datetime import timedelta
from typing import cast

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

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


def test_build_garden_snapshot_returns_structured_payload(hass: HomeAssistant) -> None:
  """Garden snapshots should expose structured TypedDict payloads."""  # noqa: E111

  manager = GardenManager(hass, "entry")  # noqa: E111
  now = dt_util.utcnow()  # noqa: E111

  active_session = GardenSession(  # noqa: E111
    session_id="garden-active",
    dog_id="dog",
    dog_name="Buddy",
    start_time=now - timedelta(minutes=10),
    status=GardenSessionStatus.ACTIVE,
  )
  active_session.weather_conditions = "Sunny"  # noqa: E111
  active_session.temperature = 24.0  # noqa: E111
  active_session.activities.append(  # noqa: E111
    GardenActivity(
      activity_type=GardenActivityType.PLAY,
      timestamp=now - timedelta(minutes=5),
      duration_seconds=120,
    )
  )
  active_session.poop_count = 1  # noqa: E111

  completed_session = GardenSession(  # noqa: E111
    session_id="garden-complete",
    dog_id="dog",
    dog_name="Buddy",
    start_time=now - timedelta(hours=2),
    end_time=now - timedelta(hours=1, minutes=30),
    status=GardenSessionStatus.COMPLETED,
  )
  completed_session.weather_conditions = "Cloudy"  # noqa: E111
  completed_session.temperature = 20.0  # noqa: E111

  manager._active_sessions["dog"] = active_session  # noqa: E111
  manager._session_history.append(completed_session)  # noqa: E111

  favorite_activities = [  # noqa: E111
    cast(GardenFavoriteActivity, {"activity": "play", "count": 2}),
    cast(GardenFavoriteActivity, {"activity": "sniffing", "count": 1}),
  ]
  weekly_summary = cast(  # noqa: E111
    GardenWeeklySummary,
    {
      "session_count": 2,
      "total_time_minutes": 60.0,
      "poop_events": 2,
      "average_duration": 30.0,
      "updated": now.isoformat(),
    },
  )

  manager._dog_stats["dog"] = GardenStats(  # noqa: E111
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

  manager._pending_confirmations["confirm"] = {  # noqa: E111
    "type": "poop_confirmation",
    "dog_id": "dog",
    "session_id": "garden-active",
    "timestamp": now - timedelta(minutes=1),
    "timeout": now + timedelta(minutes=4),
  }

  snapshot = manager.build_garden_snapshot("dog")  # noqa: E111

  assert snapshot["status"] == "active"  # noqa: E111
  assert snapshot["active_session"]  # noqa: E111
  assert snapshot["active_session"]["session_id"] == "garden-active"  # noqa: E111
  assert snapshot["stats"]["favorite_activities"][0]["activity"] == "play"  # noqa: E111
  assert snapshot["pending_confirmations"][0]["session_id"] == "garden-active"  # noqa: E111
  assert snapshot["weather_summary"]  # noqa: E111
  assert snapshot["weather_summary"]["conditions"] == ["Cloudy", "Sunny"]  # noqa: E111


def test_garden_activity_payload_roundtrip() -> None:
  """Activity payloads should round-trip through the TypedDict helpers."""  # noqa: E111

  now = dt_util.utcnow()  # noqa: E111
  activity = GardenActivity(  # noqa: E111
    activity_type=GardenActivityType.SNIFFING,
    timestamp=now,
    duration_seconds=45,
    location="rose bush",
    notes="Investigated new scents",
    confirmed=True,
  )

  payload = activity.to_dict()  # noqa: E111
  assert isinstance(payload, dict)  # noqa: E111
  assert payload["activity_type"] == "sniffing"  # noqa: E111

  restored = GardenActivity.from_dict(cast(GardenActivityPayload, payload))  # noqa: E111
  assert restored.activity_type is GardenActivityType.SNIFFING  # noqa: E111
  assert restored.duration_seconds == 45  # noqa: E111
  assert restored.confirmed is True  # noqa: E111


def test_garden_session_payload_roundtrip() -> None:
  """Session payloads should maintain structured activity lists."""  # noqa: E111

  now = dt_util.utcnow()  # noqa: E111
  session = GardenSession(  # noqa: E111
    session_id="garden-round-trip",
    dog_id="dog",
    dog_name="Buddy",
    start_time=now - timedelta(minutes=15),
    end_time=now,
    status=GardenSessionStatus.COMPLETED,
  )
  session.activities.append(  # noqa: E111
    GardenActivity(
      activity_type=GardenActivityType.DIGGING,
      timestamp=now - timedelta(minutes=10),
      duration_seconds=120,
    )
  )
  session.total_duration_seconds = 900  # noqa: E111
  session.poop_count = 0  # noqa: E111

  payload = session.to_dict()  # noqa: E111
  assert isinstance(payload, dict)  # noqa: E111
  assert payload["status"] == "completed"  # noqa: E111
  assert payload["activities"][0]["activity_type"] == "digging"  # noqa: E111

  restored = GardenSession.from_dict(cast(GardenSessionPayload, payload))  # noqa: E111
  assert restored.session_id == "garden-round-trip"  # noqa: E111
  assert restored.activities[0].activity_type is GardenActivityType.DIGGING  # noqa: E111
  assert restored.total_duration_seconds == 900  # noqa: E111
