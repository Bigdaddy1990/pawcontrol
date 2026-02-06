"""Garden session manager for PawControl."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .types import (
  GardenActiveSessionSnapshot,
  GardenConfirmationSnapshot,
  GardenModulePayload,
  GardenSessionSnapshot,
  GardenStatsSnapshot,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class GardenSession:
  """Simple in-memory garden session."""

  dog_id: str
  dog_name: str
  session_id: str
  start_time: datetime
  end_time: datetime | None = None
  activities: list[dict[str, Any]] = field(default_factory=list)
  poop_count: int = 0
  notes: str | None = None
  weather_conditions: str | None = None
  temperature: float | None = None
  detection_method: str | None = None

  @property
  def duration_minutes(self) -> float:
    """Return session duration in minutes."""
    end_time = self.end_time or dt_util.utcnow()
    return max((end_time - self.start_time).total_seconds() / 60.0, 0.0)

  def as_snapshot(
    self,
    *,
    active: bool,
  ) -> GardenSessionSnapshot | GardenActiveSessionSnapshot:
    """Return a snapshot for module payloads."""
    if active:
      return {
        "session_id": self.session_id,
        "start_time": dt_util.as_utc(self.start_time).isoformat(),
        "duration_minutes": self.duration_minutes,
        "activity_count": len(self.activities),
        "poop_count": self.poop_count,
      }

    return {
      "session_id": self.session_id,
      "start_time": dt_util.as_utc(self.start_time).isoformat(),
      "end_time": (
        dt_util.as_utc(self.end_time).isoformat() if self.end_time else None
      ),
      "duration_minutes": self.duration_minutes,
      "activity_count": len(self.activities),
      "poop_count": self.poop_count,
      "status": "completed",
      "weather_conditions": self.weather_conditions,
      "temperature": self.temperature,
      "notes": self.notes,
    }


class GardenManager:
  """Manages garden sessions without background timers."""

  def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
    self.hass = hass
    self.entry_id = entry_id
    self._sessions: dict[str, GardenSession] = {}
    self._history: dict[str, list[GardenSession]] = {}
    self._pending_confirmations: dict[str, GardenConfirmationSnapshot] = {}

  async def async_initialize(self, dogs: list[str], **kwargs: Any) -> None:
    """Initialize manager state."""
    for dog_id in dogs:
      self._history.setdefault(dog_id, [])

  def get_active_session(self, dog_id: str) -> GardenSession | None:
    """Return active session if any."""
    return self._sessions.get(dog_id)

  def is_dog_in_garden(self, dog_id: str) -> bool:
    """Return True when a dog has an active garden session."""
    return dog_id in self._sessions

  def has_pending_confirmation(self, dog_id: str) -> bool:
    """Return True when a confirmation is pending."""
    return dog_id in self._pending_confirmations

  def build_garden_snapshot(self, dog_id: str) -> GardenModulePayload:
    """Return a garden module payload snapshot."""
    active_session = self._sessions.get(dog_id)
    active_payload: GardenActiveSessionSnapshot | None = None
    if active_session is not None:
      active_payload = active_session.as_snapshot(active=True)

    history = self._history.get(dog_id, [])
    last_session = history[-1] if history else None
    last_payload: GardenSessionSnapshot | None = (
      last_session.as_snapshot(active=False) if last_session else None
    )

    sessions_today = 0
    time_today_minutes = 0.0
    poop_today = 0
    activities_today = 0

    today = dt_util.utcnow().date()
    for session in history:
      if session.start_time.date() != today:
        continue
      sessions_today += 1
      time_today_minutes += session.duration_minutes
      poop_today += session.poop_count
      activities_today += len(session.activities)

    if active_session is not None and active_session.start_time.date() == today:
      sessions_today += 1

    payload: GardenModulePayload = {
      "status": "active" if active_session else "idle",
      "sessions_today": sessions_today,
      "time_today_minutes": time_today_minutes,
      "poop_today": poop_today,
      "activities_today": activities_today,
      "activities_total": sum(len(session.activities) for session in history),
      "active_session": active_payload,
      "last_session": last_payload,
      "hours_since_last_session": None,
      "stats": GardenStatsSnapshot(),
      "pending_confirmations": list(self._pending_confirmations.values()),
      "weather_summary": None,
    }
    return payload

  async def async_start_garden_session(self, dog_id: str, **kwargs: Any) -> str:
    """Start garden session."""
    if dog_id in self._sessions:
      raise HomeAssistantError(f"Garden session already active for {dog_id}")

    session_id = f"garden_{dog_id}_{int(dt_util.utcnow().timestamp())}"
    dog_name = str(kwargs.get("dog_name", dog_id))
    session = GardenSession(
      dog_id=dog_id,
      dog_name=dog_name,
      session_id=session_id,
      start_time=dt_util.utcnow(),
      weather_conditions=kwargs.get("weather_conditions"),
      temperature=kwargs.get("temperature"),
      detection_method=kwargs.get("detection_method"),
    )
    self._sessions[dog_id] = session
    return session_id

  async def async_end_garden_session(
    self,
    dog_id: str,
    **kwargs: Any,
  ) -> GardenSession | None:
    """End garden session."""
    session = self._sessions.pop(dog_id, None)
    if session is None:
      return None

    session.end_time = dt_util.utcnow()
    session.notes = kwargs.get("notes", session.notes)
    self._history.setdefault(dog_id, []).append(session)
    self._pending_confirmations.pop(dog_id, None)
    return session

  async def async_add_activity(
    self,
    dog_id: str,
    activity_type: str,
    **kwargs: Any,
  ) -> bool:
    """Add activity during session."""
    session = self._sessions.get(dog_id)
    if session is None:
      return False

    confirmed = bool(kwargs.get("confirmed", True))
    activity = {
      "type": activity_type,
      "time": dt_util.utcnow().isoformat(),
      **{k: v for k, v in kwargs.items() if k != "confirmed"},
    }
    session.activities.append(activity)

    if activity_type == "poop" and not confirmed:
      self._pending_confirmations[dog_id] = {
        "session_id": session.session_id,
        "created": activity["time"],
        "expires": None,
      }
    elif activity_type == "poop" and confirmed:
      session.poop_count += 1

    return True

  async def async_log_activity(
    self,
    dog_id: str,
    activity_type: str,
    **kwargs: Any,
  ) -> bool:
    """Alias for activity logging."""
    return await self.async_add_activity(
      dog_id=dog_id,
      activity_type=activity_type,
      **kwargs,
    )

  async def async_handle_poop_confirmation(
    self,
    dog_id: str,
    confirmed: bool,
    **kwargs: Any,
  ) -> None:
    """Handle a pending poop confirmation."""
    pending = self._pending_confirmations.pop(dog_id, None)
    if pending is None:
      return

    if confirmed:
      session = self._sessions.get(dog_id)
      if session is not None:
        session.poop_count += 1
        session.activities.append(
          {
            "type": "poop",
            "time": dt_util.utcnow().isoformat(),
            **kwargs,
          },
        )

  async def async_export_sessions(
    self,
    dog_id: str,
    *,
    format: str = "json",
    **_kwargs: Any,
  ) -> Path:
    """Export recorded sessions to a file and return the path."""
    history = self._history.get(dog_id, [])
    data = [session.as_snapshot(active=False) for session in history]

    export_format = format.lower()
    filename = f"pawcontrol_garden_{dog_id}.{export_format}"
    path = Path(self.hass.config.path(filename))

    if export_format == "csv":
      header = (
        "session_id,start_time,end_time,duration_minutes,activity_count,poop_count\n"
      )
      rows = [
        ",".join(
          [
            str(item.get("session_id", "")),
            str(item.get("start_time", "")),
            str(item.get("end_time", "")),
            str(item.get("duration_minutes", 0.0)),
            str(item.get("activity_count", 0)),
            str(item.get("poop_count", 0)),
          ],
        )
        for item in data
      ]
      path.write_text(header + "\n".join(rows), encoding="utf-8")
    else:
      path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    return path

  async def async_cleanup(self) -> None:
    """Cleanup."""

  async def async_shutdown(self) -> None:
    """Cleanup."""
    await self.async_cleanup()
