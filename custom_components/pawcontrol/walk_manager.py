"""Walk manager for PawControl."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .exceptions import WalkAlreadyInProgressError, WalkNotInProgressError
from .types import WalkModulePayload, WalkRoutePoint, WalkSessionSnapshot

_LOGGER = logging.getLogger(__name__)

_WALK_STORAGE_VERSION = 1
_WALK_HISTORY_LIMIT = 100


class WeatherCondition(StrEnum):
  """Enumeration of supported walk weather conditions."""

  SUNNY = "sunny"
  CLOUDY = "cloudy"
  RAINY = "rainy"
  SNOWY = "snowy"
  WINDY = "windy"
  HOT = "hot"
  COLD = "cold"


@dataclass(slots=True)
class _WalkSession:
  """In-memory walk session representation."""

  data: WalkSessionSnapshot

  def finish(self, ended_at: datetime) -> WalkSessionSnapshot:
    """Finalize the session and return the serialized snapshot."""

    start = dt_util.parse_datetime(self.data.get("start_time", ""))
    if start is None:
      start = ended_at

    duration = max((ended_at - start).total_seconds(), 0.0)
    self.data.update(
      {
        "end_time": dt_util.as_utc(ended_at).isoformat(),
        "duration": duration,
        "current_duration": duration,
        "status": "completed",
      },
    )
    return self.data


class WalkManager:
  """Manages walk sessions without background timers."""

  def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
    self._store = Store(hass, _WALK_STORAGE_VERSION, f"pawcontrol_walk_{entry_id}")
    self._active_walks: dict[str, _WalkSession] = {}
    self._history: dict[str, list[WalkSessionSnapshot]] = {}

  async def async_initialize(self, dog_ids: list[str]) -> None:
    """Initialize internal caches."""
    for dog_id in dog_ids:
      self._history.setdefault(dog_id, [])
    await self._async_restore_history()

  async def _async_restore_history(self) -> None:
    """Restore history from storage."""
    data = await self._store.async_load()
    if not isinstance(data, dict):
      return

    raw_history = data.get("history")
    if not isinstance(raw_history, dict):
      return

    for dog_id, sessions in raw_history.items():
      if not isinstance(dog_id, str) or not isinstance(sessions, list):
        continue
      filtered = [session for session in sessions if isinstance(session, dict)]
      self._history[dog_id] = filtered[-_WALK_HISTORY_LIMIT:]

  async def _async_store_history(self) -> None:
    """Persist walk history to storage."""
    payload = {
      "history": {
        dog_id: sessions[-_WALK_HISTORY_LIMIT:]
        for dog_id, sessions in self._history.items()
      },
    }
    await self._store.async_save(payload)

  async def async_get_walk_data(self, dog_id: str) -> WalkModulePayload:
    """Return current walk data for ``dog_id``."""
    active_session = self._active_walks.get(dog_id)
    history = self._history.get(dog_id, [])
    now = dt_util.utcnow()
    today = now.date()
    week_start = now - timedelta(days=7)

    sessions_today = 0
    total_duration_today = 0.0
    total_distance_today = 0.0
    weekly_walks = 0
    weekly_distance = 0.0

    def _session_start(snapshot: WalkSessionSnapshot) -> datetime | None:
      start_raw = snapshot.get("start_time")
      if isinstance(start_raw, str):
        return dt_util.parse_datetime(start_raw)
      return None

    for session in history:
      start = _session_start(session)
      if start is None:
        continue
      if start.date() == today:
        sessions_today += 1
        duration = session.get("duration")
        if isinstance(duration, int | float):
          total_duration_today += float(duration)
        distance = session.get("distance")
        if isinstance(distance, int | float):
          total_distance_today += float(distance)
      if start >= week_start:
        weekly_walks += 1
        distance = session.get("distance")
        if isinstance(distance, int | float):
          weekly_distance += float(distance)

    if active_session is not None:
      sessions_today += 1

    last_session = history[-1] if history else None
    last_walk_id = last_session.get("walk_id") if last_session else None

    payload: WalkModulePayload = {
      "walk_in_progress": active_session is not None,
      "current_walk": active_session.data if active_session else None,
      "walks_today": sessions_today,
      "total_duration_today": total_duration_today,
      "total_distance_today": total_distance_today,
      "weekly_walks": weekly_walks,
      "weekly_distance": weekly_distance,
      "needs_walk": sessions_today == 0,
      "walk_streak": 0,
      "energy_level": "unknown",
      "status": "active" if active_session else "idle",
      "last_walk": last_walk_id,
      "last_walk_duration": (
        float(last_session.get("duration"))
        if last_session and isinstance(last_session.get("duration"), int | float)
        else None
      ),
      "last_walk_distance": (
        float(last_session.get("distance"))
        if last_session and isinstance(last_session.get("distance"), int | float)
        else None
      ),
    }
    return payload

  async def async_start_walk(self, dog_id: str, **kwargs: Any) -> str:
    """Start a new walk and return its walk id."""
    if dog_id in self._active_walks:
      existing = self._active_walks[dog_id].data
      raise WalkAlreadyInProgressError(
        dog_id=dog_id,
        walk_id=str(existing.get("walk_id", dog_id)),
        start_time=dt_util.parse_datetime(str(existing.get("start_time")))
        if existing.get("start_time")
        else None,
      )

    started_at = dt_util.utcnow()
    walk_id = f"walk_{dog_id}_{int(started_at.timestamp())}"
    session: WalkSessionSnapshot = {
      "walk_id": walk_id,
      "dog_id": dog_id,
      "walk_type": str(kwargs.get("walk_type", "manual")),
      "start_time": dt_util.as_utc(started_at).isoformat(),
      "status": "active",
      "path": [],
    }
    session.update({k: v for k, v in kwargs.items() if k not in {"walk_type"}})

    self._active_walks[dog_id] = _WalkSession(data=session)
    _LOGGER.debug("Started walk for %s", dog_id)
    return walk_id

  async def async_end_walk(self, dog_id: str, **kwargs: Any) -> WalkSessionSnapshot:
    """End the current walk and return its snapshot."""
    active = self._active_walks.pop(dog_id, None)
    if active is None:
      raise WalkNotInProgressError(dog_id=dog_id)

    finished = active.finish(dt_util.utcnow())
    finished.update(kwargs)
    history = self._history.setdefault(dog_id, [])
    history.append(finished)
    if len(history) > _WALK_HISTORY_LIMIT:
      self._history[dog_id] = history[-_WALK_HISTORY_LIMIT:]
    await self._async_store_history()
    _LOGGER.debug("Ended walk for %s", dog_id)
    return finished

  async def async_add_gps_point(
    self,
    dog_id: str,
    *,
    latitude: float,
    longitude: float,
    altitude: float | None = None,
    accuracy: float | None = None,
  ) -> bool:
    """Add a GPS point to the active walk."""
    active = self._active_walks.get(dog_id)
    if active is None:
      return False

    timestamp = dt_util.utcnow().isoformat()
    point: WalkRoutePoint = {
      "latitude": float(latitude),
      "longitude": float(longitude),
      "timestamp": timestamp,
    }
    if altitude is not None:
      point["altitude"] = float(altitude)
    if accuracy is not None:
      point["accuracy"] = float(accuracy)

    path = active.data.setdefault("path", [])
    if isinstance(path, list):
      path.append(point)
    return True

  async def async_cleanup(self) -> None:
    """Cleanup hook."""

  async def async_shutdown(self) -> None:
    """Shutdown hook."""
    await self.async_cleanup()
