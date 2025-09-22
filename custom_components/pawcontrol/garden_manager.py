"""Garden activity tracking and management for PawControl integration.

Monitors garden activities, tracks duration, manages poop logging, and provides
contextual push confirmations for enhanced garden behavior monitoring.

Quality Scale: Platinum
Home Assistant: 2025.9.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    EVENT_GARDEN_ENTERED,
    EVENT_GARDEN_LEFT,
    STORAGE_VERSION,
)
from .notifications import NotificationPriority, NotificationType

_LOGGER = logging.getLogger(__name__)

# Garden tracking constants
DEFAULT_GARDEN_SESSION_TIMEOUT = 1800  # 30 minutes
MIN_GARDEN_SESSION_DURATION = 60  # 1 minute
MAX_GARDEN_SESSION_DURATION = 7200  # 2 hours
POOP_CONFIRMATION_TIMEOUT = 300  # 5 minutes


class GardenActivityType(Enum):
    """Types of garden activities."""

    GENERAL = "general"
    POOP = "poop"
    PLAY = "play"
    SNIFFING = "sniffing"
    DIGGING = "digging"
    RESTING = "resting"


class GardenSessionStatus(Enum):
    """Status of garden sessions."""

    ACTIVE = "active"
    COMPLETED = "completed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class GardenActivity:
    """Represents a single garden activity within a session."""

    activity_type: GardenActivityType
    timestamp: datetime
    duration_seconds: int | None = None
    location: str | None = None
    notes: str | None = None
    confirmed: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "activity_type": self.activity_type.value,
            "timestamp": self.timestamp.isoformat(),
            "duration_seconds": self.duration_seconds,
            "location": self.location,
            "notes": self.notes,
            "confirmed": self.confirmed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GardenActivity:
        """Create from dictionary data."""
        return cls(
            activity_type=GardenActivityType(data["activity_type"]),
            timestamp=dt_util.parse_datetime(data["timestamp"]) or dt_util.utcnow(),
            duration_seconds=data.get("duration_seconds"),
            location=data.get("location"),
            notes=data.get("notes"),
            confirmed=data.get("confirmed", False),
        )


@dataclass
class GardenSession:
    """Represents a complete garden session for a dog."""

    session_id: str
    dog_id: str
    dog_name: str
    start_time: datetime
    end_time: datetime | None = None
    status: GardenSessionStatus = GardenSessionStatus.ACTIVE
    activities: list[GardenActivity] = field(default_factory=list)
    total_duration_seconds: int = 0
    poop_count: int = 0
    weather_conditions: str | None = None
    temperature: float | None = None
    notes: str | None = None

    @property
    def duration_minutes(self) -> float:
        """Get session duration in minutes."""
        return self.total_duration_seconds / 60.0

    def add_activity(self, activity: GardenActivity) -> None:
        """Add an activity to this session."""
        self.activities.append(activity)
        if activity.activity_type == GardenActivityType.POOP:
            self.poop_count += 1

    def calculate_duration(self) -> int:
        """Calculate total session duration in seconds."""
        if not self.end_time:
            self.total_duration_seconds = int(
                (dt_util.utcnow() - self.start_time).total_seconds()
            )
        else:
            self.total_duration_seconds = int(
                (self.end_time - self.start_time).total_seconds()
            )
        return self.total_duration_seconds

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "session_id": self.session_id,
            "dog_id": self.dog_id,
            "dog_name": self.dog_name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "status": self.status.value,
            "activities": [activity.to_dict() for activity in self.activities],
            "total_duration_seconds": self.total_duration_seconds,
            "poop_count": self.poop_count,
            "weather_conditions": self.weather_conditions,
            "temperature": self.temperature,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GardenSession:
        """Create from dictionary data."""
        session = cls(
            session_id=data["session_id"],
            dog_id=data["dog_id"],
            dog_name=data["dog_name"],
            start_time=dt_util.parse_datetime(data["start_time"]) or dt_util.utcnow(),
            end_time=dt_util.parse_datetime(data["end_time"])
            if data.get("end_time")
            else None,
            status=GardenSessionStatus(data["status"]),
            total_duration_seconds=data["total_duration_seconds"],
            poop_count=data["poop_count"],
            weather_conditions=data.get("weather_conditions"),
            temperature=data.get("temperature"),
            notes=data.get("notes"),
        )

        # Reconstruct activities
        for activity_data in data.get("activities", []):
            session.activities.append(GardenActivity.from_dict(activity_data))

        return session


@dataclass
class GardenStats:
    """Statistics for garden activities."""

    total_sessions: int = 0
    total_time_minutes: float = 0.0
    total_poop_count: int = 0
    average_session_duration: float = 0.0
    most_active_time_of_day: str | None = None
    favorite_activities: list[dict[str, Any]] = field(default_factory=list)
    total_activities: int = 0
    weekly_summary: dict[str, Any] = field(default_factory=dict)
    last_garden_visit: datetime | None = None


class GardenManager:
    """Manager for garden activity tracking and monitoring."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize garden manager.

        Args:
            hass: Home Assistant instance
            entry_id: Configuration entry ID
        """
        self.hass = hass
        self.entry_id = entry_id

        # Storage for garden data
        self._store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry_id}_garden")

        # Runtime state
        self._active_sessions: dict[str, GardenSession] = {}
        self._session_history: list[GardenSession] = []
        self._dog_stats: dict[str, GardenStats] = {}
        self._pending_confirmations: dict[str, dict[str, Any]] = {}

        # Configuration
        self._session_timeout = DEFAULT_GARDEN_SESSION_TIMEOUT
        self._auto_poop_detection = True
        self._confirmation_required = True

        # Background tasks
        self._cleanup_task: asyncio.Task | None = None
        self._stats_update_task: asyncio.Task | None = None

        # Dependencies (injected during initialization)
        self._notification_manager = None
        self._door_sensor_manager = None

    async def async_initialize(
        self,
        dogs: list[str],
        notification_manager=None,
        door_sensor_manager=None,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize garden manager with dependencies.

        Args:
            dogs: List of dog IDs to track
            notification_manager: Notification manager instance
            door_sensor_manager: Door sensor manager instance
            config: Optional configuration settings
        """
        self._notification_manager = notification_manager
        self._door_sensor_manager = door_sensor_manager

        # Apply configuration
        if config:
            self._session_timeout = config.get(
                "session_timeout", DEFAULT_GARDEN_SESSION_TIMEOUT
            )
            self._auto_poop_detection = config.get("auto_poop_detection", True)
            self._confirmation_required = config.get("confirmation_required", True)

        # Load stored data
        await self._load_stored_data()

        # Initialize stats for each dog
        for dog_id in dogs:
            if dog_id not in self._dog_stats:
                self._dog_stats[dog_id] = GardenStats()

        # Start background tasks
        await self._start_background_tasks()

        _LOGGER.info(
            "Garden manager initialized for %d dogs with %d historical sessions",
            len(dogs),
            len(self._session_history),
        )

    async def _load_stored_data(self) -> None:
        """Load garden data from storage."""
        try:
            stored_data = await self._store.async_load() or {}

            # Load session history
            session_data = stored_data.get("sessions", [])
            for session_dict in session_data[-100:]:  # Keep last 100 sessions
                try:
                    session = GardenSession.from_dict(session_dict)
                    self._session_history.append(session)
                except Exception as err:
                    _LOGGER.warning("Failed to load garden session: %s", err)

            # Load dog statistics
            stats_data = stored_data.get("stats", {})
            for dog_id, stats_dict in stats_data.items():
                try:
                    self._dog_stats[dog_id] = GardenStats(**stats_dict)
                except Exception as err:
                    _LOGGER.warning(
                        "Failed to load garden stats for %s: %s", dog_id, err
                    )

            _LOGGER.debug(
                "Loaded %d garden sessions and stats for %d dogs",
                len(self._session_history),
                len(self._dog_stats),
            )

        except Exception as err:
            _LOGGER.error("Failed to load garden data: %s", err)

    async def _save_data(self) -> None:
        """Save garden data to storage."""
        try:
            data = {
                "sessions": [
                    session.to_dict() for session in self._session_history[-100:]
                ],
                "stats": {
                    dog_id: {
                        "total_sessions": stats.total_sessions,
                        "total_time_minutes": stats.total_time_minutes,
                        "total_poop_count": stats.total_poop_count,
                        "average_session_duration": stats.average_session_duration,
                        "most_active_time_of_day": stats.most_active_time_of_day,
                        "favorite_activities": stats.favorite_activities,
                        "total_activities": stats.total_activities,
                        "weekly_summary": stats.weekly_summary,
                        "last_garden_visit": stats.last_garden_visit.isoformat()
                        if stats.last_garden_visit
                        else None,
                    }
                    for dog_id, stats in self._dog_stats.items()
                },
                "last_updated": dt_util.utcnow().isoformat(),
            }

            await self._store.async_save(data)

        except Exception as err:
            _LOGGER.error("Failed to save garden data: %s", err)

    async def _start_background_tasks(self) -> None:
        """Start background monitoring tasks."""
        # Cleanup task for expired sessions and confirmations
        self._cleanup_task = self.hass.async_create_task(self._cleanup_loop())

        # Stats update task
        self._stats_update_task = self.hass.async_create_task(self._stats_update_loop())

        _LOGGER.debug("Started garden manager background tasks")

    async def _cleanup_loop(self) -> None:
        """Background cleanup task."""
        while True:
            try:
                await asyncio.sleep(300)  # Run every 5 minutes
                await self._cleanup_expired_sessions()
                await self._cleanup_expired_confirmations()
            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.error("Error in garden cleanup loop: %s", err)

    async def _stats_update_loop(self) -> None:
        """Background statistics update task."""
        while True:
            try:
                await asyncio.sleep(1800)  # Run every 30 minutes
                await self._update_all_statistics()
                await self._save_data()
            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.error("Error in garden stats update loop: %s", err)

    async def async_start_garden_session(
        self,
        dog_id: str,
        dog_name: str,
        detection_method: str = "manual",
        weather_conditions: str | None = None,
        temperature: float | None = None,
    ) -> str:
        """Start a new garden session for a dog.

        Args:
            dog_id: Dog identifier
            dog_name: Dog name for display
            detection_method: How the session was started
            weather_conditions: Current weather
            temperature: Current temperature

        Returns:
            Session ID of the started session
        """
        # End any existing active session for this dog
        await self._end_active_session_for_dog(dog_id)

        # Create new session
        session_id = f"garden_{dog_id}_{int(dt_util.utcnow().timestamp())}"
        session = GardenSession(
            session_id=session_id,
            dog_id=dog_id,
            dog_name=dog_name,
            start_time=dt_util.utcnow(),
            weather_conditions=weather_conditions,
            temperature=temperature,
        )

        self._active_sessions[dog_id] = session

        # Fire garden entered event
        self.hass.bus.async_fire(
            EVENT_GARDEN_ENTERED,
            {
                "dog_id": dog_id,
                "dog_name": dog_name,
                "session_id": session_id,
                "detection_method": detection_method,
                "timestamp": session.start_time.isoformat(),
            },
        )

        # Send notification
        if self._notification_manager:
            await self._notification_manager.async_send_notification(
                notification_type=NotificationType.SYSTEM_INFO,
                title=f"🌱 {dog_name} entered garden",
                message=f"{dog_name} started a garden session. Tracking activities...",
                dog_id=dog_id,
                priority=NotificationPriority.LOW,
            )

        # Schedule automatic poop confirmation if enabled
        if self._auto_poop_detection:
            asyncio.create_task(self._schedule_poop_confirmation(dog_id, session_id))  # noqa: RUF006

        _LOGGER.info(
            "Started garden session for %s (session: %s, method: %s)",
            dog_name,
            session_id,
            detection_method,
        )

        return session_id

    async def async_end_garden_session(
        self,
        dog_id: str,
        notes: str | None = None,
        activities: list[dict[str, Any]] | None = None,
    ) -> GardenSession | None:
        """End the active garden session for a dog.

        Args:
            dog_id: Dog identifier
            notes: Optional session notes
            activities: Optional list of activities to add

        Returns:
            Completed session data or None if no active session
        """
        session = self._active_sessions.get(dog_id)
        if not session:
            _LOGGER.warning("No active garden session for %s", dog_id)
            return None

        # Complete the session
        session.end_time = dt_util.utcnow()
        session.status = GardenSessionStatus.COMPLETED
        session.notes = notes
        session.calculate_duration()

        # Add any provided activities
        if activities:
            for activity_data in activities:
                try:
                    activity = GardenActivity(
                        activity_type=GardenActivityType(
                            activity_data.get("type", "general")
                        ),
                        timestamp=dt_util.parse_datetime(activity_data.get("timestamp"))
                        or dt_util.utcnow(),
                        duration_seconds=activity_data.get("duration_seconds"),
                        location=activity_data.get("location"),
                        notes=activity_data.get("notes"),
                        confirmed=activity_data.get("confirmed", False),
                    )
                    session.add_activity(activity)
                except Exception as err:
                    _LOGGER.warning("Failed to add activity: %s", err)

        # Move to history
        self._session_history.append(session)
        del self._active_sessions[dog_id]

        # Update statistics
        await self._update_dog_statistics(dog_id)

        # Fire garden left event
        self.hass.bus.async_fire(
            EVENT_GARDEN_LEFT,
            {
                "dog_id": dog_id,
                "dog_name": session.dog_name,
                "session_id": session.session_id,
                "duration_minutes": session.duration_minutes,
                "poop_count": session.poop_count,
                "activity_count": len(session.activities),
                "timestamp": session.end_time.isoformat(),
            },
        )

        # Send completion notification
        if self._notification_manager:
            await self._notification_manager.async_send_notification(
                notification_type=NotificationType.SYSTEM_INFO,
                title=f"🏠 {session.dog_name} finished garden time",
                message=f"{session.dog_name} spent {session.duration_minutes:.1f} minutes in the garden. "
                f"Activities: {len(session.activities)}, Poop events: {session.poop_count}.",
                dog_id=dog_id,
                priority=NotificationPriority.LOW,
            )

        # Save data
        await self._save_data()

        _LOGGER.info(
            "Ended garden session for %s: %.1f minutes, %d activities, %d poop events",
            session.dog_name,
            session.duration_minutes,
            len(session.activities),
            session.poop_count,
        )

        return session

    async def async_add_activity(
        self,
        dog_id: str,
        activity_type: str,
        duration_seconds: int | None = None,
        location: str | None = None,
        notes: str | None = None,
        confirmed: bool = False,
    ) -> bool:
        """Add an activity to the active garden session.

        Args:
            dog_id: Dog identifier
            activity_type: Type of activity
            duration_seconds: Activity duration
            location: Location within garden
            notes: Activity notes
            confirmed: Whether activity was confirmed

        Returns:
            True if activity was added successfully
        """
        session = self._active_sessions.get(dog_id)
        if not session:
            _LOGGER.warning("No active garden session for %s to add activity", dog_id)
            return False

        try:
            activity = GardenActivity(
                activity_type=GardenActivityType(activity_type),
                timestamp=dt_util.utcnow(),
                duration_seconds=duration_seconds,
                location=location,
                notes=notes,
                confirmed=confirmed,
            )

            session.add_activity(activity)

            _LOGGER.debug(
                "Added %s activity to garden session for %s",
                activity_type,
                session.dog_name,
            )

            return True

        except Exception as err:
            _LOGGER.error("Failed to add garden activity for %s: %s", dog_id, err)
            return False

    async def async_log_poop_event(
        self,
        dog_id: str,
        quality: str | None = None,
        size: str | None = None,
        location: str | None = None,
        notes: str | None = None,
        confirmed: bool = True,
    ) -> bool:
        """Log a poop event during garden session.

        Args:
            dog_id: Dog identifier
            quality: Poop quality assessment
            size: Poop size assessment
            location: Location in garden
            notes: Additional notes
            confirmed: Whether event was confirmed

        Returns:
            True if event was logged successfully
        """
        session = self._active_sessions.get(dog_id)
        if not session:
            # If no active session, this might be a standalone poop log
            _LOGGER.debug(
                "No active garden session for %s, logging standalone poop event", dog_id
            )
            return await self._log_standalone_poop_event(
                dog_id, quality, size, location, notes
            )

        # Add poop activity to session
        poop_notes = (
            f"Quality: {quality or 'not_specified'}, Size: {size or 'not_specified'}"
        )
        if notes:
            poop_notes += f", Notes: {notes}"

        activity = GardenActivity(
            activity_type=GardenActivityType.POOP,
            timestamp=dt_util.utcnow(),
            location=location,
            notes=poop_notes,
            confirmed=confirmed,
        )

        session.add_activity(activity)

        # Send poop event notification
        if self._notification_manager and confirmed:
            await self._notification_manager.async_send_notification(
                notification_type=NotificationType.SYSTEM_INFO,
                title=f"💩 Poop logged: {session.dog_name}",
                message=f"{session.dog_name} had a poop in the garden. {poop_notes}",
                dog_id=dog_id,
                priority=NotificationPriority.LOW,
            )

        _LOGGER.info(
            "Logged poop event for %s in garden session: %s",
            session.dog_name,
            poop_notes,
        )

        return True

    async def _log_standalone_poop_event(
        self,
        dog_id: str,
        quality: str | None,
        size: str | None,
        location: str | None,
        notes: str | None,
    ) -> bool:
        """Log a poop event outside of an active garden session."""
        # Update dog statistics directly
        if dog_id in self._dog_stats:
            self._dog_stats[dog_id].total_poop_count += 1
            await self._save_data()

        # Send notification
        if self._notification_manager:
            poop_details = f"Quality: {quality or 'not_specified'}, Size: {size or 'not_specified'}"
            if location:
                poop_details += f", Location: {location}"

            await self._notification_manager.async_send_notification(
                notification_type=NotificationType.SYSTEM_INFO,
                title=f"💩 Poop logged: {dog_id}",
                message=f"Poop event recorded for {dog_id}. {poop_details}",
                dog_id=dog_id,
                priority=NotificationPriority.LOW,
            )

        return True

    async def _schedule_poop_confirmation(self, dog_id: str, session_id: str) -> None:
        """Schedule automatic poop confirmation request.

        Args:
            dog_id: Dog identifier
            session_id: Garden session ID
        """
        # Wait a few minutes before asking
        await asyncio.sleep(180)  # 3 minutes

        session = self._active_sessions.get(dog_id)
        if not session or session.session_id != session_id:
            return  # Session ended or changed

        # Check if poop already logged
        poop_activities = [
            a for a in session.activities if a.activity_type == GardenActivityType.POOP
        ]
        if poop_activities:
            return  # Poop already logged

        # Send confirmation request
        if self._notification_manager:
            confirmation_id = f"poop_confirm_{dog_id}_{session_id}"
            self._pending_confirmations[confirmation_id] = {
                "type": "poop_confirmation",
                "dog_id": dog_id,
                "session_id": session_id,
                "timestamp": dt_util.utcnow(),
                "timeout": dt_util.utcnow()
                + timedelta(seconds=POOP_CONFIRMATION_TIMEOUT),
            }

            await self._notification_manager.async_send_notification(
                notification_type=NotificationType.SYSTEM_INFO,
                title=f"💩 Poop check: {session.dog_name}",
                message=f"Did {session.dog_name} have a poop in the garden? Tap to confirm or deny.",
                dog_id=dog_id,
                priority=NotificationPriority.NORMAL,
                data={
                    "confirmation_id": confirmation_id,
                    "actions": [
                        {
                            "action": f"confirm_poop_{dog_id}",
                            "title": "Yes, had a poop",
                        },
                        {
                            "action": f"deny_poop_{dog_id}",
                            "title": "No poop",
                        },
                    ],
                },
                expires_in=timedelta(seconds=POOP_CONFIRMATION_TIMEOUT),
            )

    async def async_handle_poop_confirmation(
        self,
        dog_id: str,
        confirmed: bool,
        quality: str | None = None,
        size: str | None = None,
        location: str | None = None,
    ) -> None:
        """Handle poop confirmation response.

        Args:
            dog_id: Dog identifier
            confirmed: Whether poop was confirmed
            quality: Optional poop quality
            size: Optional poop size
            location: Optional location
        """
        # Find and remove pending confirmation
        confirmation_id = None
        for conf_id, conf_data in self._pending_confirmations.items():
            if (
                conf_data.get("dog_id") == dog_id
                and conf_data.get("type") == "poop_confirmation"
            ):
                confirmation_id = conf_id
                break

        if confirmation_id:
            del self._pending_confirmations[confirmation_id]

        if confirmed:
            await self.async_log_poop_event(
                dog_id=dog_id,
                quality=quality or "normal",
                size=size or "normal",
                location=location,
                confirmed=True,
            )
        else:
            _LOGGER.debug("Poop confirmation denied for %s", dog_id)

    async def _end_active_session_for_dog(self, dog_id: str) -> None:
        """End any active session for a dog."""
        if dog_id in self._active_sessions:
            await self.async_end_garden_session(
                dog_id, notes="Auto-ended for new session"
            )

    async def _cleanup_expired_sessions(self) -> None:
        """Clean up expired garden sessions."""
        now = dt_util.utcnow()
        expired_dogs = []

        for dog_id, session in self._active_sessions.items():
            session_age = (now - session.start_time).total_seconds()
            if session_age > self._session_timeout:
                expired_dogs.append(dog_id)

        for dog_id in expired_dogs:
            session = self._active_sessions[dog_id]
            session.status = GardenSessionStatus.TIMEOUT
            await self.async_end_garden_session(dog_id, notes="Session timed out")

            _LOGGER.info(
                "Garden session for %s timed out after %.1f minutes",
                session.dog_name,
                session.duration_minutes,
            )

    async def _cleanup_expired_confirmations(self) -> None:
        """Clean up expired confirmation requests."""
        now = dt_util.utcnow()
        expired_confirmations = []

        for conf_id, conf_data in self._pending_confirmations.items():
            if now > conf_data.get("timeout", now):
                expired_confirmations.append(conf_id)

        for conf_id in expired_confirmations:
            del self._pending_confirmations[conf_id]

    async def _update_dog_statistics(self, dog_id: str) -> None:
        """Update statistics for a specific dog."""
        if dog_id not in self._dog_stats:
            self._dog_stats[dog_id] = GardenStats()

        stats = self._dog_stats[dog_id]

        # Get sessions for this dog
        dog_sessions = [s for s in self._session_history if s.dog_id == dog_id]

        if not dog_sessions:
            return

        # Calculate statistics
        stats.total_sessions = len(dog_sessions)
        stats.total_time_minutes = sum(
            s.calculate_duration() / 60 for s in dog_sessions
        )
        stats.total_poop_count = sum(s.poop_count for s in dog_sessions)
        stats.average_session_duration = stats.total_time_minutes / stats.total_sessions
        stats.last_garden_visit = max(s.end_time or s.start_time for s in dog_sessions)
        stats.total_activities = sum(len(s.activities) for s in dog_sessions)

        # Find most active time of day (simplified)
        hour_counts = {}
        for session in dog_sessions:
            hour = session.start_time.hour
            hour_counts[hour] = hour_counts.get(hour, 0) + 1

        if hour_counts:
            most_active_hour = max(hour_counts.items(), key=lambda x: x[1])[0]
            if 6 <= most_active_hour < 12:
                stats.most_active_time_of_day = "morning"
            elif 12 <= most_active_hour < 18:
                stats.most_active_time_of_day = "afternoon"
            elif 18 <= most_active_hour < 22:
                stats.most_active_time_of_day = "evening"
            else:
                stats.most_active_time_of_day = "night"

        # Find favorite activities
        activity_counts = {}
        for session in dog_sessions:
            for activity in session.activities:
                activity_type = activity.activity_type.value
                activity_counts[activity_type] = (
                    activity_counts.get(activity_type, 0) + 1
                )

        stats.favorite_activities = [
            {"activity": activity_type, "count": count}
            for activity_type, count in sorted(
                activity_counts.items(), key=lambda item: item[1], reverse=True
            )[:3]
        ]

        # Weekly summary (last 7 days)
        now_utc = dt_util.utcnow()
        week_start = now_utc - timedelta(days=7)
        weekly_sessions = [
            session
            for session in dog_sessions
            if (session.end_time or session.start_time) >= week_start
        ]

        if weekly_sessions:
            total_week_minutes = sum(
                session.calculate_duration() / 60 for session in weekly_sessions
            )
            stats.weekly_summary = {
                "session_count": len(weekly_sessions),
                "total_time_minutes": total_week_minutes,
                "poop_events": sum(session.poop_count for session in weekly_sessions),
                "average_duration": total_week_minutes / len(weekly_sessions),
                "updated": now_utc.isoformat(),
            }
        else:
            stats.weekly_summary = {}

    async def _update_all_statistics(self) -> None:
        """Update statistics for all dogs."""
        for dog_id in self._dog_stats:
            await self._update_dog_statistics(dog_id)

    def get_active_session(self, dog_id: str) -> GardenSession | None:
        """Get active garden session for a dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Active session or None
        """
        return self._active_sessions.get(dog_id)

    def get_dog_statistics(self, dog_id: str) -> GardenStats | None:
        """Get garden statistics for a dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Garden statistics or None
        """
        return self._dog_stats.get(dog_id)

    def get_recent_sessions(
        self, dog_id: str | None = None, limit: int = 10
    ) -> list[GardenSession]:
        """Get recent garden sessions.

        Args:
            dog_id: Optional dog ID filter
            limit: Maximum number of sessions to return

        Returns:
            List of recent sessions
        """
        sessions = self._session_history

        if dog_id:
            sessions = [s for s in sessions if s.dog_id == dog_id]

        # Sort by start time (most recent first)
        sessions.sort(key=lambda s: s.start_time, reverse=True)

        return sessions[:limit]

    def has_pending_confirmation(self, dog_id: str) -> bool:
        """Return True if a poop confirmation is pending for the dog."""

        return any(
            confirmation.get("dog_id") == dog_id
            and confirmation.get("type") == "poop_confirmation"
            for confirmation in self._pending_confirmations.values()
        )

    def get_pending_confirmations(self, dog_id: str) -> list[dict[str, Any]]:
        """Return pending confirmation requests for a dog."""

        confirmations: list[dict[str, Any]] = []
        for confirmation in self._pending_confirmations.values():
            if (
                confirmation.get("dog_id") != dog_id
                or confirmation.get("type") != "poop_confirmation"
            ):
                continue

            timestamp = confirmation.get("timestamp")
            timeout = confirmation.get("timeout")
            confirmations.append(
                {
                    "session_id": confirmation.get("session_id"),
                    "created": timestamp.isoformat() if timestamp else None,
                    "expires": timeout.isoformat() if timeout else None,
                }
            )

        return confirmations

    def build_garden_snapshot(
        self, dog_id: str, *, recent_limit: int = 50
    ) -> dict[str, Any]:
        """Build a snapshot of garden activity for sensors and diagnostics."""

        snapshot: dict[str, Any] = {
            "status": "idle",
            "sessions_today": 0,
            "time_today_minutes": 0.0,
            "poop_today": 0,
            "activities_today": 0,
            "activities_total": 0,
            "active_session": None,
            "last_session": None,
            "hours_since_last_session": None,
            "stats": {},
            "pending_confirmations": self.get_pending_confirmations(dog_id),
            "weather_summary": None,
        }

        now_local = dt_util.now()
        start_of_day = dt_util.start_of_local_day(now_local)

        sessions = self.get_recent_sessions(dog_id, limit=recent_limit)
        todays_sessions: list[GardenSession] = []

        for session in sessions:
            session_start_local = dt_util.as_local(session.start_time)
            if session_start_local >= start_of_day:
                todays_sessions.append(session)

        active_session = self.get_active_session(dog_id)
        if active_session:
            snapshot["status"] = "active"
            snapshot["active_session"] = {
                "session_id": active_session.session_id,
                "start_time": active_session.start_time.isoformat(),
                "duration_minutes": round(active_session.calculate_duration() / 60, 2),
                "activity_count": len(active_session.activities),
                "poop_count": active_session.poop_count,
            }

        stats = self.get_dog_statistics(dog_id)
        if stats:
            snapshot["stats"] = {
                "total_sessions": stats.total_sessions,
                "total_time_minutes": stats.total_time_minutes,
                "total_poop_count": stats.total_poop_count,
                "average_session_duration": stats.average_session_duration,
                "most_active_time_of_day": stats.most_active_time_of_day,
                "favorite_activities": stats.favorite_activities,
                "weekly_summary": stats.weekly_summary,
                "last_garden_visit": stats.last_garden_visit.isoformat()
                if stats.last_garden_visit
                else None,
            }
            snapshot["activities_total"] = stats.total_activities

        # Calculate today's aggregates including active session
        sessions_to_process = list(todays_sessions)
        if (
            active_session
            and dt_util.as_local(active_session.start_time) >= start_of_day
        ) and not any(
            session.session_id == active_session.session_id
            for session in sessions_to_process
        ):
            sessions_to_process.append(active_session)

        total_seconds_today = 0
        total_poop_today = 0
        total_activities_today = 0
        weather_conditions: list[str] = []
        temperatures: list[float] = []

        for session in sessions_to_process:
            duration = session.calculate_duration()
            total_seconds_today += duration
            total_poop_today += session.poop_count
            total_activities_today += len(session.activities)
            if session.weather_conditions:
                weather_conditions.append(session.weather_conditions)
            if session.temperature is not None:
                temperatures.append(session.temperature)

        snapshot["sessions_today"] = len(sessions_to_process)
        snapshot["time_today_minutes"] = round(total_seconds_today / 60, 2)
        snapshot["poop_today"] = total_poop_today
        snapshot["activities_today"] = total_activities_today

        if weather_conditions or temperatures:
            average_temperature = (
                sum(temperatures) / len(temperatures) if temperatures else None
            )
            snapshot["weather_summary"] = {
                "conditions": weather_conditions,
                "average_temperature": average_temperature,
            }

        if sessions:
            last_session = sessions[0]
            snapshot["last_session"] = {
                "session_id": last_session.session_id,
                "start_time": last_session.start_time.isoformat(),
                "end_time": last_session.end_time.isoformat()
                if last_session.end_time
                else None,
                "duration_minutes": round(last_session.calculate_duration() / 60, 2),
                "activity_count": len(last_session.activities),
                "poop_count": last_session.poop_count,
                "status": last_session.status.value,
                "weather_conditions": last_session.weather_conditions,
                "temperature": last_session.temperature,
                "notes": last_session.notes,
            }

            reference_time = last_session.end_time or last_session.start_time
            if reference_time:
                snapshot["hours_since_last_session"] = round(
                    (dt_util.utcnow() - reference_time).total_seconds() / 3600,
                    2,
                )

        return snapshot

    def is_dog_in_garden(self, dog_id: str) -> bool:
        """Check if dog is currently in garden.

        Args:
            dog_id: Dog identifier

        Returns:
            True if dog has active garden session
        """
        return dog_id in self._active_sessions

    async def async_cleanup(self) -> None:
        """Clean up garden manager."""
        # Cancel background tasks
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()

        if self._stats_update_task and not self._stats_update_task.done():
            self._stats_update_task.cancel()

        # End all active sessions
        for dog_id in list(self._active_sessions.keys()):
            await self.async_end_garden_session(dog_id, notes="System cleanup")

        # Save final data
        await self._save_data()

        _LOGGER.info("Garden manager cleanup completed")
