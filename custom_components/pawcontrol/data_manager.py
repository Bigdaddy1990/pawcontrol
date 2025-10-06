"""Data management helpers for the PawControl integration.

The previous optimisation-heavy data manager removed a number of behaviours
required by the tests in this repository.  This module intentionally favours a
clear and well documented implementation that focuses on correctness,
maintainability, and graceful error handling.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .types import DailyStats, FeedingData, GPSLocation, HealthData, WalkData

_LOGGER = logging.getLogger(__name__)

_STORAGE_FILENAME = "data.json"

if __name__ not in sys.modules and "pawcontrol_data_manager" in sys.modules:
    sys.modules[__name__] = sys.modules["pawcontrol_data_manager"]

if TYPE_CHECKING:
    from .coordinator_support import CoordinatorMetrics


class AdaptiveCache:
    """Simple asynchronous cache used by legacy tests."""

    def __init__(self, default_ttl: int = 300) -> None:
        self._default_ttl = default_ttl
        self._data: dict[str, Any] = {}
        self._metadata: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    async def get(self, key: str) -> tuple[Any | None, bool]:
        async with self._lock:
            entry = self._metadata.get(key)
            if entry is None:
                self._misses += 1
                return None, False

            if dt_util.utcnow() > entry["expiry"]:
                self._data.pop(key, None)
                self._metadata.pop(key, None)
                self._misses += 1
                return None, False

            self._hits += 1
            return self._data[key], True

    async def set(self, key: str, value: Any, base_ttl: int = 300) -> None:
        async with self._lock:
            ttl = base_ttl if base_ttl > 0 else self._default_ttl
            expiry = dt_util.utcnow() + timedelta(seconds=ttl)
            self._data[key] = value
            self._metadata[key] = {"expiry": expiry}

    async def cleanup_expired(self) -> int:
        async with self._lock:
            now = dt_util.utcnow()
            expired = [
                key for key, meta in self._metadata.items() if now > meta["expiry"]
            ]
            for key in expired:
                self._data.pop(key, None)
                self._metadata.pop(key, None)
            return len(expired)

    def get_stats(self) -> dict[str, Any]:
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total else 0
        return {
            "size": len(self._data),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 2),
            "memory_mb": 0.0,
        }


def _serialize_datetime(value: datetime | None) -> str | None:
    """Convert a datetime into ISO format."""

    if value is None:
        return None
    return dt_util.as_utc(value).isoformat()


def _deserialize_datetime(value: Any) -> datetime | None:
    """Decode ISO formatted datetimes from JSON payloads."""

    if value is None:
        return None
    if isinstance(value, datetime):
        return dt_util.as_utc(value)
    parsed = dt_util.parse_datetime(str(value))
    if parsed is None:
        return None
    return dt_util.as_utc(parsed)


@dataclass
class DogProfile:
    """Representation of all stored data for a single dog."""

    config: dict[str, Any]
    daily_stats: DailyStats
    feeding_history: list[dict[str, Any]] = field(default_factory=list)
    walk_history: list[dict[str, Any]] = field(default_factory=list)
    health_history: list[dict[str, Any]] = field(default_factory=list)
    current_walk: WalkData | None = None

    @classmethod
    def from_storage(
        cls, config: Mapping[str, Any], stored: Mapping[str, Any] | None
    ) -> DogProfile:
        """Restore a profile from persisted JSON data."""

        daily_stats_payload = stored.get("daily_stats", {}) if stored else {}
        feeding_history = list(stored.get("feeding_history", [])) if stored else []
        walk_history = list(stored.get("walk_history", [])) if stored else []
        health_history = list(stored.get("health_history", [])) if stored else []

        try:
            daily_stats = DailyStats.from_dict(daily_stats_payload)
        except Exception:  # pragma: no cover - only triggered by corrupt files
            daily_stats = DailyStats(date=dt_util.utcnow())

        return cls(
            config=dict(config),
            daily_stats=daily_stats,
            feeding_history=feeding_history,
            walk_history=walk_history,
            health_history=health_history,
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a serialisable representation of the profile."""

        data: dict[str, Any] = {
            "config": self.config,
            "daily_stats": self.daily_stats.as_dict(),
            "feeding_history": list(self.feeding_history),
            "walk_history": list(self.walk_history),
            "health_history": list(self.health_history),
        }

        if self.current_walk is not None:
            data["current_walk"] = _serialize_walk(self.current_walk)

        return data


def _serialize_walk(walk: WalkData) -> dict[str, Any]:
    """Serialise a :class:`WalkData` instance into JSON friendly data."""

    return {
        "start_time": _serialize_datetime(walk.start_time),
        "end_time": _serialize_datetime(walk.end_time),
        "duration": walk.duration,
        "distance": walk.distance,
        "route": list(walk.route),
        "label": walk.label,
        "location": walk.location,
        "notes": walk.notes,
        "rating": walk.rating,
        "started_by": walk.started_by,
        "ended_by": walk.ended_by,
        "weather": walk.weather,
        "temperature": walk.temperature,
    }


class PawControlDataManager:
    """Store and retrieve dog related data for the integration."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str | None = None,
        *,
        coordinator: Any | None = None,
        dogs_config: list[dict[str, Any]] | None = None,
    ) -> None:
        self.hass = hass
        self._coordinator = coordinator
        self._dogs_config = {cfg["dog_id"]: dict(cfg) for cfg in dogs_config or []}

        if entry_id is None and coordinator is not None:
            entry = getattr(coordinator, "config_entry", None)
            candidate = getattr(entry, "entry_id", None)
            if isinstance(candidate, str):
                entry_id = candidate

        self.entry_id = entry_id or "default"
        config_dir = Path(getattr(hass.config, "config_dir", "."))
        self._storage_dir = config_dir / DOMAIN
        self._storage_path = self._storage_dir / f"{self.entry_id}_{_STORAGE_FILENAME}"
        self._backup_path = self._storage_path.with_suffix(
            self._storage_path.suffix + ".backup"
        )

        self._dog_profiles: dict[str, DogProfile] = {}
        self._data_lock = asyncio.Lock()
        self._save_lock = asyncio.Lock()
        self._initialised = False
        self._namespace_locks: dict[str, asyncio.Lock] = {}

        self._ensure_metrics_containers()

    def _ensure_metrics_containers(self) -> None:
        """Initialise in-memory metrics containers if missing."""

        if not hasattr(self, "_metrics"):
            self._metrics: dict[str, Any] = {
                "operations": 0,
                "saves": 0,
                "errors": 0,
                "visitor_mode_last_runtime_ms": 0.0,
                "visitor_mode_avg_runtime_ms": 0.0,
            }
        if not hasattr(self, "_visitor_timings"):
            self._visitor_timings = deque(maxlen=50)
        if not hasattr(self, "_metrics_sink"):
            self._metrics_sink: CoordinatorMetrics | None = None

    async def async_initialize(self) -> None:
        """Create storage folders and load persisted data."""

        try:
            self._storage_dir.mkdir(parents=True, exist_ok=True)
        except OSError as err:
            raise HomeAssistantError(
                f"Unable to prepare PawControl storage at {self._storage_dir}: {err}"
            ) from err

        stored = await self._async_load_storage()
        for dog_id, config in self._dogs_config.items():
            self._dog_profiles[dog_id] = DogProfile.from_storage(
                config, stored.get(dog_id)
            )

        self._initialised = True

    async def async_shutdown(self) -> None:
        """Persist pending data on shutdown."""

        if not self._initialised:
            return

        for dog_id in list(self._dog_profiles):
            try:
                await self._async_save_dog_data(dog_id)
            except HomeAssistantError:
                _LOGGER.exception("Failed to persist PawControl data for %s", dog_id)

    async def async_log_feeding(self, dog_id: str, feeding: FeedingData) -> bool:
        """Record a feeding event."""

        if dog_id not in self._dog_profiles:
            return False

        async with self._data_lock:
            profile = self._dog_profiles[dog_id]
            self._maybe_roll_daily_stats(profile, feeding.timestamp)

            entry = {
                "meal_type": feeding.meal_type,
                "portion_size": feeding.portion_size,
                "food_type": feeding.food_type,
                "timestamp": feeding.timestamp.isoformat(),
                "notes": feeding.notes,
                "logged_by": feeding.logged_by,
                "calories": feeding.calories,
                "automatic": feeding.automatic,
            }
            profile.feeding_history.append(entry)
            profile.daily_stats.register_feeding(
                feeding.portion_size, feeding.timestamp
            )

        try:
            await self._async_save_dog_data(dog_id)
        except HomeAssistantError:
            return False
        except Exception as err:  # pragma: no cover - defensive guard
            _LOGGER.error("Failed to persist feeding data for %s: %s", dog_id, err)
            return False
        return True

    async def async_set_visitor_mode(
        self, dog_id: str, settings: Mapping[str, Any]
    ) -> bool:
        """Persist visitor mode configuration for ``dog_id``."""

        if not dog_id:
            raise ValueError("dog_id is required")

        payload = dict(settings)

        namespace = "visitor_mode"
        self._ensure_metrics_containers()
        locks = getattr(self, "_namespace_locks", None)
        if locks is None:
            locks = {}
            self._namespace_locks = locks
        lock = locks.setdefault(namespace, asyncio.Lock())

        started = perf_counter()
        try:
            async with lock:
                data = await self._get_namespace_data(namespace)
                existing = data.get(dog_id)
                if isinstance(existing, Mapping):
                    merged = dict(existing)
                    merged.update(payload)
                else:
                    merged = payload
                data[dog_id] = merged
                await self._save_namespace(namespace, data)
        except HomeAssistantError:
            self._metrics["errors"] += 1
            raise
        except Exception as err:  # pragma: no cover - defensive guard
            self._metrics["errors"] += 1
            raise HomeAssistantError(
                f"Failed to update visitor mode for {dog_id}: {err}"
            ) from err
        else:
            self._record_visitor_metrics(perf_counter() - started)
        return True

    def set_metrics_sink(self, metrics: CoordinatorMetrics | None) -> None:
        """Register a metrics sink used for coordinator diagnostics."""

        self._ensure_metrics_containers()
        self._metrics_sink = metrics

    def _record_visitor_metrics(self, duration: float) -> None:
        """Capture visitor-mode runtime metrics and forward to sinks."""

        self._ensure_metrics_containers()

        duration_ms = max(duration, 0.0) * 1000.0
        self._metrics["visitor_mode_last_runtime_ms"] = round(duration_ms, 3)

        self._visitor_timings.append(max(duration, 0.0))
        average_ms = (
            sum(self._visitor_timings) / len(self._visitor_timings) * 1000.0
            if self._visitor_timings
            else 0.0
        )
        self._metrics["visitor_mode_avg_runtime_ms"] = round(average_ms, 3)
        self._metrics["operations"] += 1

        sink = getattr(self, "_metrics_sink", None)
        if sink is not None:
            sink.record_visitor_timing(max(duration, 0.0))

    def get_daily_feeding_stats(self, dog_id: str) -> dict[str, Any] | None:
        """Return aggregated feeding information for today."""

        profile = self._dog_profiles.get(dog_id)
        if profile is None:
            return None

        today = profile.daily_stats.date.date()
        feedings_today = [
            entry
            for entry in profile.feeding_history
            if (timestamp := _deserialize_datetime(entry.get("timestamp")))
            and timestamp.date() == today
        ]

        total_calories = sum(
            entry["calories"]
            for entry in feedings_today
            if isinstance(entry.get("calories"), int | float)
        )

        return {
            "total_feedings": profile.daily_stats.feedings_count,
            "total_food_amount": round(profile.daily_stats.total_food_amount, 2),
            "total_calories": round(total_calories, 2),
            "feeding_times": [entry["timestamp"] for entry in feedings_today],
        }

    def get_feeding_history(
        self, dog_id: str, *, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Return historical feeding entries."""

        profile = self._dog_profiles.get(dog_id)
        if profile is None:
            return []

        history = list(profile.feeding_history)
        history.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
        if limit is not None:
            return history[:limit]
        return history

    async def async_start_walk(
        self,
        dog_id: str,
        *,
        started_by: str = "",
        location: str = "",
        label: str = "",
        notes: str = "",
    ) -> bool:
        """Begin a walk for the provided dog."""

        if dog_id not in self._dog_profiles:
            return False

        async with self._data_lock:
            profile = self._dog_profiles[dog_id]
            if profile.current_walk is not None:
                return False

            profile.current_walk = WalkData(
                start_time=dt_util.utcnow(),
                location=location,
                label=label,
                started_by=started_by,
                notes=notes,
            )

        try:
            await self._async_save_dog_data(dog_id)
        except HomeAssistantError:
            return False
        except Exception as err:  # pragma: no cover - defensive guard
            _LOGGER.error("Failed to persist walk data for %s: %s", dog_id, err)
            return False
        return True

    async def async_end_walk(
        self,
        dog_id: str,
        *,
        ended_by: str = "",
        distance: float | None = None,
        rating: int | None = None,
        notes: str = "",
    ) -> bool:
        """Complete the current walk for ``dog_id``."""

        if dog_id not in self._dog_profiles:
            return False

        async with self._data_lock:
            profile = self._dog_profiles[dog_id]
            walk = profile.current_walk
            if walk is None:
                return False

            end_time = dt_util.utcnow()
            walk.end_time = end_time
            walk.ended_by = ended_by
            walk.notes = notes
            if rating is not None:
                walk.rating = rating
            if distance is not None:
                walk.distance = distance
            if walk.duration is None:
                duration = (end_time - walk.start_time).total_seconds()
                walk.duration = max(0, round(duration))

            profile.walk_history.append(_serialize_walk(walk))
            profile.current_walk = None
            profile.daily_stats.register_walk(walk.duration, walk.distance, end_time)

        try:
            await self._async_save_dog_data(dog_id)
        except HomeAssistantError:
            return False
        except Exception as err:  # pragma: no cover - defensive guard
            _LOGGER.error("Failed to persist walk route for %s: %s", dog_id, err)
            return False
        return True

    def get_walk_history(
        self, dog_id: str, *, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Return stored walk history."""

        profile = self._dog_profiles.get(dog_id)
        if profile is None:
            return []

        history = list(profile.walk_history)
        history.sort(key=lambda item: item.get("end_time", ""), reverse=True)
        if limit is not None:
            return history[:limit]
        return history

    async def async_update_walk_route(self, dog_id: str, location: GPSLocation) -> bool:
        """Add GPS information to the active walk."""

        profile = self._dog_profiles.get(dog_id)
        if profile is None or profile.current_walk is None:
            return False

        async with self._data_lock:
            walk = profile.current_walk
            if walk is None:
                return False
            walk.route.append(
                {
                    "latitude": location.latitude,
                    "longitude": location.longitude,
                    "accuracy": location.accuracy,
                    "altitude": location.altitude,
                    "timestamp": location.timestamp.isoformat(),
                    "source": location.source,
                    "battery_level": location.battery_level,
                    "signal_strength": location.signal_strength,
                }
            )
            profile.daily_stats.register_gps_update()

        try:
            await self._async_save_dog_data(dog_id)
        except HomeAssistantError:
            return False
        except Exception as err:  # pragma: no cover - defensive guard
            _LOGGER.error("Failed to persist health data for %s: %s", dog_id, err)
            return False
        return True

    async def async_log_health_data(self, dog_id: str, health: HealthData) -> bool:
        """Record a health measurement."""

        if dog_id not in self._dog_profiles:
            return False

        async with self._data_lock:
            profile = self._dog_profiles[dog_id]
            self._maybe_roll_daily_stats(profile, health.timestamp)

            entry = {
                "timestamp": health.timestamp.isoformat(),
                "weight": health.weight,
                "temperature": health.temperature,
                "mood": health.mood,
                "activity_level": health.activity_level,
                "health_status": health.health_status,
                "symptoms": health.symptoms,
                "medication": health.medication,
                "note": health.note,
                "logged_by": health.logged_by,
                "heart_rate": health.heart_rate,
                "respiratory_rate": health.respiratory_rate,
            }
            profile.health_history.append(entry)
            profile.daily_stats.register_health_event(health.timestamp)

        try:
            await self._async_save_dog_data(dog_id)
        except HomeAssistantError:
            return False
        return True

    def get_health_history(
        self, dog_id: str, *, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Return stored health entries."""

        profile = self._dog_profiles.get(dog_id)
        if profile is None:
            return []

        history = list(profile.health_history)
        history.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
        if limit is not None:
            return history[:limit]
        return history

    def get_health_trends(self, dog_id: str, *, days: int = 7) -> dict[str, Any] | None:
        """Analyse health entries recorded within ``days``."""

        profile = self._dog_profiles.get(dog_id)
        if profile is None:
            return None

        cutoff = dt_util.utcnow() - timedelta(days=days)
        tolerance = timedelta(seconds=1)
        relevant = [
            entry
            for entry in profile.health_history
            if (timestamp := _deserialize_datetime(entry.get("timestamp")))
            and timestamp >= cutoff - tolerance
        ]

        if not relevant:
            return {
                "entries": 0,
                "weight_trend": None,
                "mood_distribution": {},
            }

        weights = [entry["weight"] for entry in relevant if entry.get("weight")]
        if weights:
            data_points = [
                {
                    "timestamp": entry.get("timestamp"),
                    "weight": entry.get("weight"),
                }
                for entry in relevant
                if entry.get("weight") is not None
            ]
            change = weights[-1] - weights[0]
            if change > 0:
                direction = "increasing"
            elif change < 0:
                direction = "decreasing"
            else:
                direction = "stable"
            weight_trend: dict[str, Any] | None = {
                "start": weights[0],
                "end": weights[-1],
                "change": round(change, 2),
                "direction": direction,
                "data_points": data_points,
            }
        else:
            weight_trend = None

        mood_distribution: dict[str, int] = {}
        for entry in relevant:
            mood = entry.get("mood") or "unknown"
            mood_distribution[mood] = mood_distribution.get(mood, 0) + 1

        status_progression = [
            entry.get("health_status", "")
            for entry in relevant
            if entry.get("health_status")
        ]

        return {
            "entries": len(relevant),
            "weight_trend": weight_trend,
            "mood_distribution": mood_distribution,
            "health_status_progression": status_progression,
        }

    def get_metrics(self) -> dict[str, Any]:
        """Expose lightweight metrics for diagnostics tests."""

        return {
            "dogs": len(self._dog_profiles),
            "storage_path": str(self._storage_path),
        }

    async def async_get_registered_dogs(self) -> list[str]:
        """Return the list of configured dog identifiers."""

        return list(self._dog_profiles)

    def _namespace_path(self, namespace: str) -> Path:
        """Return the file path used to persist a namespace payload."""

        safe_namespace = namespace.replace("/", "_")
        return self._storage_dir / f"{self.entry_id}_{safe_namespace}.json"

    async def _get_namespace_data(self, namespace: str) -> dict[str, Any]:
        """Read a JSON payload for ``namespace`` from disk."""

        path = self._namespace_path(namespace)
        try:
            if not path.exists():
                return {}
            contents = await asyncio.to_thread(path.read_text, encoding="utf-8")
        except FileNotFoundError:
            return {}
        except OSError as err:
            raise HomeAssistantError(
                f"Unable to read PawControl {namespace} data: {err}"
            ) from err

        if not contents:
            return {}

        try:
            return json.loads(contents)
        except json.JSONDecodeError:
            _LOGGER.warning(
                "Corrupted PawControl %s data detected at %s", namespace, path
            )
            return {}

    async def _save_namespace(self, namespace: str, data: dict[str, Any]) -> None:
        """Persist a JSON payload for ``namespace`` to disk."""

        path = self._namespace_path(namespace)
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        try:
            await asyncio.to_thread(path.write_text, payload, encoding="utf-8")
        except OSError as err:
            raise HomeAssistantError(
                f"Unable to persist PawControl {namespace} data: {err}"
            ) from err

        self._ensure_metrics_containers()
        self._metrics["saves"] += 1

    async def _async_load_storage(self) -> dict[str, Any]:
        """Load stored JSON data, falling back to the backup if required."""

        try:
            if Path.exists(self._storage_path):
                with open(self._storage_path, encoding="utf-8") as handle:
                    return json.load(handle)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError:
            _LOGGER.warning(
                "Corrupted PawControl data detected at %s", self._storage_path
            )
        except OSError as err:
            raise HomeAssistantError(f"Unable to read PawControl data: {err}") from err

        try:
            if Path.exists(self._backup_path):
                with open(self._backup_path, encoding="utf-8") as handle:
                    return json.load(handle)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError:
            _LOGGER.warning(
                "Backup PawControl data is corrupted at %s", self._backup_path
            )
        except OSError as err:
            raise HomeAssistantError(
                f"Unable to read PawControl backup: {err}"
            ) from err

        return {}

    async def _async_save_dog_data(self, dog_id: str) -> None:
        """Persist all dog data to disk."""

        async with self._save_lock:
            payload = {
                k: profile.as_dict() for k, profile in self._dog_profiles.items()
            }
            try:
                self._write_storage(payload)
            except OSError as err:
                raise HomeAssistantError(
                    f"Failed to persist PawControl data: {err}"
                ) from err

    def _write_storage(self, payload: dict[str, Any]) -> None:
        """Write data to the JSON storage file."""

        if self._storage_path.exists():
            self._create_backup()

        with open(self._storage_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    def _create_backup(self) -> None:
        """Create a best-effort backup copy of the current data file."""

        try:
            data = self._storage_path.read_bytes()
        except FileNotFoundError:
            return
        self._backup_path.write_bytes(data)

    @staticmethod
    def _maybe_roll_daily_stats(profile: DogProfile, timestamp: datetime) -> None:
        """Reset daily statistics when the day changes."""

        current_day = dt_util.as_utc(timestamp).date()
        if profile.daily_stats.date.date() != current_day:
            profile.daily_stats = DailyStats(date=dt_util.as_utc(timestamp))
