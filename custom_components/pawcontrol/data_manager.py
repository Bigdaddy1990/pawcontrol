"""Data management helpers for the PawControl integration.

The previous optimisation-heavy data manager removed a number of behaviours
required by the tests in this repository.  This module intentionally favours a
clear and well documented implementation that focuses on correctness,
maintainability, and graceful error handling.
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import sys
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from itertools import islice
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


def _serialize_timestamp(value: Any | None) -> str:
    """Return an ISO timestamp for ``value`` or ``utcnow`` when missing."""

    if isinstance(value, datetime):
        return dt_util.as_utc(value).isoformat()
    if value:
        parsed = _deserialize_datetime(value)
        if parsed:
            return parsed.isoformat()
    return dt_util.utcnow().isoformat()


def _coerce_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a shallow copy of ``value`` ensuring a mutable mapping."""

    return dict(value) if isinstance(value, Mapping) else {}


def _merge_dicts(base: Mapping[str, Any], updates: Mapping[str, Any]) -> dict[str, Any]:
    """Deep merge ``updates`` into ``base`` using Home Assistant semantics."""

    merged = dict(base) if isinstance(base, Mapping) else {}
    for key, value in (updates or {}).items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _limit_entries(
    entries: list[dict[str, Any]], *, limit: int | None
) -> list[dict[str, Any]]:
    """Return ``entries`` optionally constrained to the most recent ``limit``."""

    if limit is None or limit <= 0:
        return entries
    return list(islice(entries, max(len(entries) - limit, 0), None))


def _coerce_health_payload(data: HealthData | Mapping[str, Any]) -> dict[str, Any]:
    """Return a dict payload from ``data`` regardless of the input type."""

    if isinstance(data, HealthData):
        payload = {
            "timestamp": data.timestamp,
            "weight": data.weight,
            "temperature": data.temperature,
            "mood": data.mood,
            "activity_level": data.activity_level,
            "health_status": data.health_status,
            "symptoms": data.symptoms,
            "medication": data.medication,
            "note": data.note,
            "logged_by": data.logged_by,
            "heart_rate": data.heart_rate,
            "respiratory_rate": data.respiratory_rate,
        }
    elif isinstance(data, Mapping):
        payload = dict(data)
    else:  # pragma: no cover - guard for unexpected input
        raise TypeError("health data must be a mapping or HealthData instance")

    payload["timestamp"] = _serialize_timestamp(payload.get("timestamp"))
    return payload


def _coerce_medication_payload(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return normalised medication data for persistence."""

    payload = dict(data)
    payload["administration_time"] = _serialize_timestamp(
        payload.get("administration_time")
    )
    payload.setdefault("logged_at", dt_util.utcnow().isoformat())
    return payload


def _default_session_id_generator() -> str:
    """Generate a unique identifier for grooming sessions."""

    from uuid import uuid4

    return uuid4().hex


@dataclass
class DogProfile:
    """Representation of all stored data for a single dog."""

    config: dict[str, Any]
    daily_stats: DailyStats
    feeding_history: list[dict[str, Any]] = field(default_factory=list)
    walk_history: list[dict[str, Any]] = field(default_factory=list)
    health_history: list[dict[str, Any]] = field(default_factory=list)
    medication_history: list[dict[str, Any]] = field(default_factory=list)
    poop_history: list[dict[str, Any]] = field(default_factory=list)
    grooming_sessions: list[dict[str, Any]] = field(default_factory=list)
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
        medication_history = (
            list(stored.get("medication_history", [])) if stored else []
        )
        poop_history = list(stored.get("poop_history", [])) if stored else []
        grooming_sessions = list(stored.get("grooming_sessions", [])) if stored else []

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
            medication_history=medication_history,
            poop_history=poop_history,
            grooming_sessions=grooming_sessions,
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a serialisable representation of the profile."""

        data: dict[str, Any] = {
            "config": self.config,
            "daily_stats": self.daily_stats.as_dict(),
            "feeding_history": list(self.feeding_history),
            "walk_history": list(self.walk_history),
            "health_history": list(self.health_history),
            "medication_history": list(self.medication_history),
            "poop_history": list(self.poop_history),
            "grooming_sessions": list(self.grooming_sessions),
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
        self._session_id_factory: Callable[[], str] = _default_session_id_generator

        self._ensure_metrics_containers()

    def _get_runtime_data(self) -> Any | None:
        """Return the runtime data container when available."""

        entry_id = getattr(self, "entry_id", None)
        if not entry_id:
            return None
        try:
            from .runtime_data import get_runtime_data
        except ImportError:  # pragma: no cover - defensive
            return None

        try:
            return get_runtime_data(self.hass, entry_id)
        except Exception:  # pragma: no cover - runtime retrieval errors
            return None

    def _get_namespace_lock(self, namespace: str) -> asyncio.Lock:
        """Return a lock used to guard namespace updates."""

        lock = self._namespace_locks.get(namespace)
        if lock is None:
            lock = asyncio.Lock()
            self._namespace_locks[namespace] = lock
        return lock

    async def _update_namespace_for_dog(
        self,
        namespace: str,
        dog_id: str,
        updater: Callable[[Any | None], Any | None],
    ) -> Any | None:
        """Update ``namespace`` payload for ``dog_id`` using ``updater``."""

        lock = self._get_namespace_lock(namespace)
        async with lock:
            data = await self._get_namespace_data(namespace)
            current = data.get(dog_id)
            updated = updater(current)
            if updated is None:
                data.pop(dog_id, None)
            else:
                data[dog_id] = updated
            await self._save_namespace(namespace, data)
            return updated

    def _ensure_profile(self, dog_id: str) -> DogProfile:
        """Return the profile for ``dog_id`` or raise ``HomeAssistantError``."""

        profile = self._dog_profiles.get(dog_id)
        if profile is None:
            raise HomeAssistantError(f"Unknown PawControl dog: {dog_id}")
        return profile

    async def _async_save_profile(self, dog_id: str, profile: DogProfile) -> None:
        """Persist ``profile`` for ``dog_id`` and update cached config."""

        self._dog_profiles[dog_id] = profile
        self._dogs_config[dog_id] = dict(profile.config)
        await self._async_save_dog_data(dog_id)

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
        self,
        dog_id: str,
        settings: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> bool:
        """Persist visitor mode configuration for ``dog_id``."""

        if not dog_id:
            raise ValueError("dog_id is required")

        payload: Mapping[str, Any] | None = settings
        if payload is None and "visitor_data" in kwargs:
            payload = kwargs["visitor_data"]
        elif payload is None and kwargs:
            payload = kwargs

        if payload is None:
            raise ValueError("Visitor mode payload is required")

        payload = dict(payload)
        payload.setdefault("timestamp", dt_util.utcnow())
        payload["timestamp"] = _serialize_timestamp(payload.get("timestamp"))

        namespace = "visitor_mode"
        self._ensure_metrics_containers()
        started = perf_counter()
        try:
            await self._update_namespace_for_dog(
                namespace,
                dog_id,
                lambda current: _merge_dicts(
                    _coerce_mapping(current if isinstance(current, Mapping) else {}),
                    payload,
                ),
            )
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

    async def async_get_visitor_mode_status(self, dog_id: str) -> dict[str, Any]:
        """Return the visitor mode status for ``dog_id``."""

        namespace = "visitor_mode"
        data = await self._get_namespace_data(namespace)
        entry = data.get(dog_id)
        if isinstance(entry, Mapping):
            return dict(entry)
        return {"enabled": False}

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

    async def async_reset_dog_daily_stats(self, dog_id: str) -> None:
        """Reset the daily statistics for ``dog_id``."""

        profile = self._ensure_profile(dog_id)
        async with self._data_lock:
            profile.daily_stats = DailyStats(date=dt_util.utcnow())
        await self._async_save_profile(dog_id, profile)

    async def async_get_module_data(self, dog_id: str) -> dict[str, Any]:
        """Return merged module configuration for ``dog_id``."""

        profile = self._ensure_profile(dog_id)
        namespace = await self._get_namespace_data("module_state")
        overrides = _coerce_mapping(namespace.get(dog_id))
        modules = _coerce_mapping(profile.config.get("modules"))
        return _merge_dicts(modules, overrides)

    async def async_set_dog_power_state(self, dog_id: str, enabled: bool) -> None:
        """Persist the main power state for ``dog_id``."""

        async def updater(current: Any | None) -> dict[str, Any]:
            payload = _coerce_mapping(current)
            payload["main_power"] = bool(enabled)
            payload.setdefault("updated_at", dt_util.utcnow().isoformat())
            return payload

        await self._update_namespace_for_dog("module_state", dog_id, updater)

    async def async_set_gps_tracking(self, dog_id: str, enabled: bool) -> None:
        """Persist GPS tracking preference for ``dog_id``."""

        async def updater(current: Any | None) -> dict[str, Any]:
            payload = _coerce_mapping(current)
            gps_state = _coerce_mapping(payload.get("gps"))
            gps_state["enabled"] = bool(enabled)
            gps_state["updated_at"] = dt_util.utcnow().isoformat()
            payload["gps"] = gps_state
            return payload

        await self._update_namespace_for_dog("module_state", dog_id, updater)

    async def async_log_poop_data(
        self, dog_id: str, poop_data: Mapping[str, Any], *, limit: int = 100
    ) -> bool:
        """Store poop events for ``dog_id`` with optional history limit."""

        if dog_id not in self._dog_profiles:
            return False

        payload = dict(poop_data)
        payload.setdefault("timestamp", dt_util.utcnow())
        payload["timestamp"] = _serialize_timestamp(payload.get("timestamp"))

        async with self._data_lock:
            profile = self._dog_profiles[dog_id]
            profile.poop_history.append(payload)
            profile.poop_history[:] = _limit_entries(profile.poop_history, limit=limit)

        try:
            await self._async_save_profile(dog_id, profile)
        except HomeAssistantError:
            return False
        return True

    async def async_start_grooming_session(
        self,
        dog_id: str,
        session_data: Mapping[str, Any],
        *,
        session_id: str | None = None,
    ) -> str:
        """Record the start of a grooming session and return the session id."""

        profile = self._ensure_profile(dog_id)
        payload = dict(session_data)
        session_identifier = session_id or self._session_id_factory()
        payload.setdefault("session_id", session_identifier)
        payload.setdefault("started_at", dt_util.utcnow())
        payload["started_at"] = _serialize_timestamp(payload.get("started_at"))

        async with self._data_lock:
            profile.grooming_sessions.append(payload)
            profile.grooming_sessions[:] = _limit_entries(
                profile.grooming_sessions, limit=50
            )

        await self._async_save_profile(dog_id, profile)
        return session_identifier

    async def async_analyze_patterns(
        self,
        dog_id: str,
        analysis_type: str,
        *,
        days: int = 30,
    ) -> dict[str, Any]:
        """Analyze historic data for ``dog_id``."""

        profile = self._ensure_profile(dog_id)
        now = dt_util.utcnow()
        cutoff = now - timedelta(days=max(days, 1))
        tolerance = timedelta(seconds=1)

        def _filter_entries(
            entries: list[dict[str, Any]], timestamp_key: str = "timestamp"
        ) -> list[tuple[datetime, dict[str, Any]]]:
            filtered: list[tuple[datetime, dict[str, Any]]] = []
            for item in entries:
                ts = _deserialize_datetime(item.get(timestamp_key))
                if ts and ts >= cutoff - tolerance:
                    filtered.append((ts, dict(item)))
            return filtered

        result: dict[str, Any] = {
            "dog_id": dog_id,
            "analysis_type": analysis_type,
            "days": days,
            "generated_at": now.isoformat(),
        }

        if analysis_type in {"feeding", "comprehensive"}:
            feedings = _filter_entries(profile.feeding_history)
            total = sum(entry.get("portion_size", 0) or 0 for _, entry in feedings)
            result["feeding"] = {
                "entries": len(feedings),
                "total_portion_size": round(total, 2),
                "first_entry": feedings[0][1] if feedings else None,
                "last_entry": feedings[-1][1] if feedings else None,
            }

        if analysis_type in {"walking", "comprehensive"}:
            walks = _filter_entries(profile.walk_history, "end_time")
            total_distance = sum(entry.get("distance", 0) or 0 for _, entry in walks)
            result["walking"] = {
                "entries": len(walks),
                "total_distance": round(total_distance, 2),
            }

        if analysis_type in {"health", "comprehensive"}:
            health_entries = _filter_entries(profile.health_history)
            result["health"] = {
                "entries": len(health_entries),
                "latest": health_entries[-1][1] if health_entries else None,
            }

        await self._update_namespace_for_dog(
            "analysis_cache",
            dog_id,
            lambda current: _merge_dicts(
                _coerce_mapping(current if isinstance(current, Mapping) else {}),
                {analysis_type: result},
            ),
        )

        runtime = self._get_runtime_data()
        feeding_manager = getattr(runtime, "feeding_manager", None)
        if (
            feeding_manager
            and analysis_type in {"feeding", "comprehensive"}
            and hasattr(feeding_manager, "async_analyze_feeding_health")
        ):
            try:
                advanced = await feeding_manager.async_analyze_feeding_health(
                    dog_id, days
                )
            except Exception:  # pragma: no cover - non-critical fallback
                advanced = None
            if advanced:
                result.setdefault("feeding", {})["health_analysis"] = advanced

        return result

    async def async_generate_report(
        self,
        dog_id: str,
        report_type: str,
        *,
        include_recommendations: bool = True,
        days: int = 30,
        start_date: datetime | str | None = None,
        end_date: datetime | str | None = None,
        include_sections: list[str] | None = None,
        format: str = "json",
        send_notification: bool | None = None,
    ) -> dict[str, Any]:
        """Generate a summary report for ``dog_id``."""

        profile = self._ensure_profile(dog_id)
        now = dt_util.utcnow()
        report_window_start = _deserialize_datetime(start_date) if start_date else None
        report_window_end = _deserialize_datetime(end_date) if end_date else None
        if report_window_start is None:
            report_window_start = now - timedelta(days=max(days, 1))
        if report_window_end is None:
            report_window_end = now

        sections = set(include_sections or [])
        if not sections:
            sections = {"feeding", "walks", "health"}

        report: dict[str, Any] = {
            "dog_id": dog_id,
            "report_type": report_type,
            "generated_at": now.isoformat(),
            "range": {
                "start": report_window_start.isoformat(),
                "end": report_window_end.isoformat(),
            },
            "sections": sorted(sections),
        }

        def _within_window(timestamp: Any) -> bool:
            ts = _deserialize_datetime(timestamp)
            if ts is None:
                return False
            return report_window_start <= ts <= report_window_end

        if "feeding" in sections:
            feedings = [
                entry
                for entry in profile.feeding_history
                if _within_window(entry.get("timestamp"))
            ]
            total_portion = sum(entry.get("portion_size", 0) or 0 for entry in feedings)
            report["feeding"] = {
                "entries": len(feedings),
                "total_portion_size": round(total_portion, 2),
            }

        if "walks" in sections:
            walks = [
                entry
                for entry in profile.walk_history
                if _within_window(entry.get("end_time"))
            ]
            total_distance = sum(entry.get("distance", 0) or 0 for entry in walks)
            report["walks"] = {
                "entries": len(walks),
                "total_distance": round(total_distance, 2),
            }

        if "health" in sections:
            health_entries = [
                entry
                for entry in profile.health_history
                if _within_window(entry.get("timestamp"))
            ]
            report["health"] = {
                "entries": len(health_entries),
                "latest": health_entries[-1] if health_entries else None,
            }

        if include_recommendations:
            recommendations: list[str] = []
            if report.get("feeding", {}).get("entries") == 0:
                recommendations.append(
                    "Log feeding events to improve analysis accuracy."
                )
            if report.get("walks", {}).get("entries") == 0:
                recommendations.append(
                    "Schedule regular walks to maintain activity levels."
                )
            report["recommendations"] = recommendations

        runtime = self._get_runtime_data()
        feeding_manager = getattr(runtime, "feeding_manager", None)
        if feeding_manager and hasattr(feeding_manager, "async_generate_health_report"):
            try:
                health_report = await feeding_manager.async_generate_health_report(
                    dog_id
                )
            except Exception:  # pragma: no cover - optional enhancement
                health_report = None
            if health_report:
                report.setdefault("health", {})["detailed_report"] = health_report

        await self._update_namespace_for_dog(
            "reports",
            dog_id,
            lambda current: _merge_dicts(
                _coerce_mapping(current if isinstance(current, Mapping) else {}),
                {report_type: report},
            ),
        )

        if send_notification:
            runtime = runtime or self._get_runtime_data()
            notification_manager = getattr(runtime, "notification_manager", None)
            if notification_manager and hasattr(
                notification_manager, "async_send_notification"
            ):
                try:
                    await notification_manager.async_send_notification(
                        notification_type="report_ready",
                        title=f"{profile.config.get('dog_name', dog_id)} {report_type} report",
                        message="Your PawControl report is ready for review.",
                        priority="normal",
                    )
                except Exception:  # pragma: no cover - notification best-effort
                    _LOGGER.debug(
                        "Notification dispatch for report failed", exc_info=True
                    )

        return report

    async def async_generate_weekly_health_report(
        self, dog_id: str, *, include_medication: bool = True
    ) -> dict[str, Any]:
        """Generate a weekly health overview for ``dog_id``."""

        profile = self._ensure_profile(dog_id)
        now = dt_util.utcnow()
        cutoff = now - timedelta(days=7)

        health_entries = [
            entry
            for entry in profile.health_history
            if (timestamp := _deserialize_datetime(entry.get("timestamp")))
            and timestamp >= cutoff
        ]

        report: dict[str, Any] = {
            "dog_id": dog_id,
            "generated_at": now.isoformat(),
            "entries": len(health_entries),
            "recent_weights": [entry.get("weight") for entry in health_entries],
            "recent_temperatures": [
                entry.get("temperature")
                for entry in health_entries
                if entry.get("temperature")
            ],
        }

        if include_medication:
            medications = [
                entry
                for entry in profile.medication_history
                if (
                    timestamp := _deserialize_datetime(entry.get("administration_time"))
                )
                and timestamp >= cutoff
            ]
            report["medication"] = {
                "entries": len(medications),
                "latest": medications[-1] if medications else None,
            }

        await self._update_namespace_for_dog(
            "health_reports",
            dog_id,
            lambda current: _merge_dicts(
                _coerce_mapping(current if isinstance(current, Mapping) else {}),
                {"weekly": report},
            ),
        )

        return report

    async def async_export_data(
        self,
        dog_id: str,
        data_type: str,
        *,
        format: str = "json",
        days: int | None = None,
        date_from: datetime | str | None = None,
        date_to: datetime | str | None = None,
    ) -> Path:
        """Export stored data for ``dog_id`` and return the export path."""

        profile = self._ensure_profile(dog_id)

        dataset: list[dict[str, Any]]
        timestamp_key = "timestamp"
        match data_type:
            case "feeding":
                dataset = profile.feeding_history
                timestamp_key = "timestamp"
            case "walks" | "walking":
                dataset = profile.walk_history
                timestamp_key = "end_time"
            case "health":
                dataset = profile.health_history
                timestamp_key = "timestamp"
            case "medication":
                dataset = profile.medication_history
                timestamp_key = "administration_time"
            case _:
                raise HomeAssistantError(f"Unsupported export data type: {data_type}")

        start = _deserialize_datetime(date_from) if date_from else None
        end = _deserialize_datetime(date_to) if date_to else None
        if start is None and days is not None:
            start = dt_util.utcnow() - timedelta(days=max(days, 0))
        if end is None:
            end = dt_util.utcnow()

        def _in_window(entry: Mapping[str, Any]) -> bool:
            ts = _deserialize_datetime(entry.get(timestamp_key))
            if ts is None:
                return False
            if start and ts < start:
                return False
            return not (end and ts > end)

        entries = [dict(item) for item in dataset if _in_window(item)]

        export_dir = self._storage_dir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        timestamp = dt_util.utcnow().strftime("%Y%m%d%H%M%S")
        normalized_format = format.lower()
        if normalized_format not in {"json", "csv", "markdown", "md", "txt"}:
            normalized_format = "json"

        extension = "md" if normalized_format == "markdown" else normalized_format
        filename = (
            f"{self.entry_id}_{dog_id}_{data_type}_{timestamp}.{extension}".replace(
                " ", "_"
            )
        )
        export_path = export_dir / filename

        if normalized_format == "csv":
            if entries:
                fieldnames = sorted({key for entry in entries for key in entry})
            else:
                fieldnames = []

            def _write_csv() -> None:
                with open(export_path, "w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fieldnames)
                    if fieldnames:
                        writer.writeheader()
                    writer.writerows(entries)

            await asyncio.to_thread(_write_csv)
        elif normalized_format in {"markdown", "md", "txt"}:

            def _write_markdown() -> None:
                lines = [f"# {data_type.title()} export for {dog_id}", ""]
                for entry in entries:
                    lines.append(
                        "- " + ", ".join(f"{k}: {v}" for k, v in entry.items())
                    )
                export_path.write_text("\n".join(lines), encoding="utf-8")

            await asyncio.to_thread(_write_markdown)
        else:

            def _write_json() -> None:
                payload = {
                    "dog_id": dog_id,
                    "data_type": data_type,
                    "generated_at": dt_util.utcnow().isoformat(),
                    "entries": entries,
                }
                export_path.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
                )

            await asyncio.to_thread(_write_json)

        return export_path

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

    async def async_log_health_data(
        self, dog_id: str, health: HealthData | Mapping[str, Any]
    ) -> bool:
        """Record a health measurement."""

        if dog_id not in self._dog_profiles:
            return False

        payload = _coerce_health_payload(health)
        timestamp = _deserialize_datetime(payload.get("timestamp")) or dt_util.utcnow()

        async with self._data_lock:
            profile = self._dog_profiles[dog_id]
            self._maybe_roll_daily_stats(profile, timestamp)

            entry = dict(payload)
            entry["timestamp"] = _serialize_timestamp(timestamp)

            profile.health_history.append(entry)
            profile.daily_stats.register_health_event(timestamp)

        try:
            await self._async_save_dog_data(dog_id)
        except HomeAssistantError:
            return False
        return True

    async def async_log_medication(
        self, dog_id: str, medication_data: Mapping[str, Any]
    ) -> bool:
        """Persist medication information for ``dog_id``."""

        if dog_id not in self._dog_profiles:
            return False

        payload = _coerce_medication_payload(medication_data)

        async with self._data_lock:
            profile = self._dog_profiles[dog_id]
            profile.medication_history.append(payload)

        try:
            await self._async_save_dog_data(dog_id)
        except HomeAssistantError:
            return False
        return True

    async def async_update_dog_data(
        self, dog_id: str, updates: Mapping[str, Any], *, persist: bool = True
    ) -> bool:
        """Merge ``updates`` into the stored dog configuration."""

        if dog_id not in self._dog_profiles:
            return False

        if not isinstance(updates, Mapping):
            raise ValueError("updates must be a mapping")

        async with self._data_lock:
            profile = self._dog_profiles[dog_id]
            config = dict(profile.config)
            for section, payload in updates.items():
                if isinstance(payload, Mapping):
                    current = _coerce_mapping(config.get(section))
                    config[section] = _merge_dicts(current, payload)
                else:
                    config[section] = payload
            profile.config = config

        if persist:
            try:
                await self._async_save_profile(dog_id, profile)
            except HomeAssistantError:
                return False
        else:
            self._dog_profiles[dog_id] = profile
            self._dogs_config[dog_id] = dict(profile.config)

        return True

    async def async_update_dog_profile(
        self, dog_id: str, profile_updates: Mapping[str, Any], *, persist: bool = True
    ) -> bool:
        """Persist profile-specific updates for ``dog_id``."""

        return await self.async_update_dog_data(
            dog_id, {"profile": profile_updates}, persist=persist
        )

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
