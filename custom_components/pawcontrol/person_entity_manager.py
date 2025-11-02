"""Person entity integration for targeted notifications.

Automatically discovers person.* entities and provides dynamic notification
targeting based on home/away status for enhanced user experience.

Quality Scale: Platinum target
Home Assistant: 2025.9.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol, cast

from homeassistant.const import STATE_HOME
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .coordinator_support import CacheMonitorRegistrar
from .types import (
    CacheDiagnosticsSnapshot,
    JSONMutableMapping,
    PersonEntityAttributePayload,
    PersonEntityCounters,
    PersonEntityDiagnostics,
    PersonEntitySnapshot,
    PersonEntitySnapshotEntry,
    PersonEntityStats,
    PersonEntityStorageEntry,
    PersonNotificationCacheEntry,
    PersonNotificationContext,
)
from .utils import ensure_utc_datetime

_LOGGER = logging.getLogger(__name__)

# Configuration constants
DEFAULT_DISCOVERY_INTERVAL = 300  # 5 minutes
DEFAULT_CACHE_TTL = 180  # 3 minutes
MIN_DISCOVERY_INTERVAL = 60  # 1 minute
MAX_DISCOVERY_INTERVAL = 3600  # 1 hour


@dataclass
class _PersonNotificationCachePayload:
    """Internal cache payload storing canonical targets and timestamps."""

    targets: tuple[str, ...]
    generated_at: datetime


class PersonNotificationCache[EntryT: PersonNotificationCacheEntry]:
    """Typed notification target cache with diagnostics helpers."""

    __slots__ = ("_entries",)

    def __init__(self) -> None:
        """Initialize the notification target cache container."""
        self._entries: dict[str, _PersonNotificationCachePayload] = {}

    def clear(self) -> None:
        """Remove all cached entries."""

        self._entries.clear()

    def store(
        self, key: str, targets: Sequence[str], generated_at: datetime
    ) -> tuple[str, ...]:
        """Store ``targets`` under ``key`` and return a deduplicated tuple."""

        seen: set[str] = set()
        canonical: list[str] = []
        for target in targets:
            if target in seen:
                continue
            seen.add(target)
            canonical.append(target)

        payload = _PersonNotificationCachePayload(tuple(canonical), generated_at)
        self._entries[key] = payload
        return payload.targets

    def try_get(self, key: str, *, now: datetime, ttl: int) -> tuple[str, ...] | None:
        """Return cached targets when still valid, otherwise ``None``."""

        payload = self._entries.get(key)
        if payload is None:
            return None

        age_seconds = (now - payload.generated_at).total_seconds()
        if age_seconds < ttl:
            return payload.targets
        return None

    def snapshot(self, *, now: datetime, ttl: int) -> dict[str, EntryT]:
        """Return a diagnostics snapshot of cached entries."""

        entries: dict[str, EntryT] = {}
        for key, payload in self._entries.items():
            age_seconds = max((now - payload.generated_at).total_seconds(), 0.0)
            entries[key] = cast(
                EntryT,
                {
                    "targets": payload.targets,
                    "generated_at": payload.generated_at.isoformat(),
                    "age_seconds": age_seconds,
                    "stale": age_seconds > ttl,
                },
            )
        return entries

    def __len__(self) -> int:
        """Return the number of cached entries."""

        return len(self._entries)


def _empty_person_attributes() -> PersonEntityAttributePayload:
    """Return an empty attribute payload for person entities."""

    return {}


@dataclass
class PersonEntityInfo:
    """Information about a discovered person entity."""

    entity_id: str
    name: str
    friendly_name: str
    state: str
    is_home: bool
    last_updated: datetime
    mobile_device_id: str | None = None
    notification_service: str | None = None
    attributes: PersonEntityAttributePayload = field(
        default_factory=_empty_person_attributes
    )

    def __post_init__(self) -> None:
        """Post initialization to ensure data consistency."""
        self.is_home = self.state == STATE_HOME

    def to_dict(self) -> PersonEntityStorageEntry:
        """Convert to dictionary for storage/serialization."""
        payload: PersonEntityStorageEntry = {
            "entity_id": self.entity_id,
            "name": self.name,
            "friendly_name": self.friendly_name,
            "state": self.state,
            "is_home": self.is_home,
            "last_updated": self.last_updated.isoformat(),
            "mobile_device_id": self.mobile_device_id,
            "notification_service": self.notification_service,
            "attributes": self.attributes,
        }
        return payload

    @classmethod
    def from_dict(cls, data: PersonEntityStorageEntry) -> PersonEntityInfo:
        """Create from dictionary."""
        last_updated = ensure_utc_datetime(data["last_updated"])
        if last_updated is None:
            last_updated = dt_util.utcnow()

        return cls(
            entity_id=data["entity_id"],
            name=data["name"],
            friendly_name=data["friendly_name"],
            state=data["state"],
            is_home=data["is_home"],
            last_updated=last_updated,
            mobile_device_id=data.get("mobile_device_id"),
            notification_service=data.get("notification_service"),
            attributes=cast(
                PersonEntityAttributePayload,
                data.get("attributes", {}),
            ),
        )


@dataclass
class PersonEntityConfig:
    """Configuration for person entity integration."""

    enabled: bool = True
    auto_discovery: bool = True
    discovery_interval: int = DEFAULT_DISCOVERY_INTERVAL
    cache_ttl: int = DEFAULT_CACHE_TTL
    include_away_persons: bool = False
    fallback_to_static: bool = True
    static_notification_targets: list[str] = field(default_factory=list)
    excluded_entities: list[str] = field(default_factory=list)
    notification_mapping: dict[str, str] = field(
        default_factory=dict
    )  # entity_id -> service
    priority_persons: list[str] = field(default_factory=list)  # High priority persons


class SupportsCoordinatorSnapshot(Protocol):
    """Protocol describing the cache snapshot contract."""

    def coordinator_snapshot(self) -> Mapping[str, Any]:
        """Return a diagnostics payload for coordinator consumption."""


class PersonEntityManager(SupportsCoordinatorSnapshot):
    """Manager for person entity discovery and notification targeting."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize person entity manager.

        Args:
            hass: Home Assistant instance
            entry_id: Configuration entry ID
        """
        self.hass = hass
        self.entry_id = entry_id

        # Configuration and state
        self._config = PersonEntityConfig()
        self._persons: dict[str, PersonEntityInfo] = {}
        self._state_listeners: list[Callable] = []
        self._discovery_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._cache_registrar: CacheMonitorRegistrar | None = None

        # Performance tracking
        self._last_discovery = dt_util.now()
        self._discovery_count = 0
        self._targets_cache: PersonNotificationCache[PersonNotificationCacheEntry] = (
            PersonNotificationCache()
        )

        # Statistics
        self._stats: PersonEntityCounters = {
            "persons_discovered": 0,
            "notifications_targeted": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "discovery_runs": 0,
        }

    async def async_initialize(self, config: dict[str, Any] | None = None) -> None:
        """Initialize person entity manager with configuration.

        Args:
            config: Optional configuration override
        """
        async with self._lock:
            # Update configuration
            if config:
                self._config = PersonEntityConfig(
                    enabled=config.get("enabled", True),
                    auto_discovery=config.get("auto_discovery", True),
                    discovery_interval=max(
                        MIN_DISCOVERY_INTERVAL,
                        min(
                            MAX_DISCOVERY_INTERVAL,
                            config.get(
                                "discovery_interval", DEFAULT_DISCOVERY_INTERVAL
                            ),
                        ),
                    ),
                    cache_ttl=config.get("cache_ttl", DEFAULT_CACHE_TTL),
                    include_away_persons=config.get("include_away_persons", False),
                    fallback_to_static=config.get("fallback_to_static", True),
                    static_notification_targets=config.get(
                        "static_notification_targets", []
                    ),
                    excluded_entities=config.get("excluded_entities", []),
                    notification_mapping=config.get("notification_mapping", {}),
                    priority_persons=config.get("priority_persons", []),
                )

            if not self._config.enabled:
                _LOGGER.debug("Person entity integration disabled")
                return

            # Initial discovery
            await self._discover_person_entities()

            # Set up state tracking
            await self._setup_state_tracking()

            # Start discovery task if auto-discovery enabled
            if self._config.auto_discovery:
                await self._start_discovery_task()

            _LOGGER.info(
                "Person entity manager initialized: %d persons discovered",
                len(self._persons),
            )

        if self._cache_registrar is not None:
            self.register_cache_monitors(self._cache_registrar)

    async def _discover_person_entities(self) -> None:
        """Discover all person entities in Home Assistant."""
        try:
            entity_registry = er.async_get(self.hass)
            discovered_count = 0

            # Get all person domain entities from registry
            person_entities = [
                entry
                for entry in entity_registry.entities.values()
                if entry.domain == "person" and not entry.disabled_by
            ]

            new_persons: dict[str, PersonEntityInfo] = {}

            for entity_entry in person_entities:
                entity_id = entity_entry.entity_id

                # Skip excluded entities
                if entity_id in self._config.excluded_entities:
                    continue

                # Get current state
                state = self.hass.states.get(entity_id)
                if state is None:
                    continue

                # Extract person information
                friendly_name = state.attributes.get(
                    "friendly_name", entity_entry.name or entity_id
                )
                name = entity_entry.name or friendly_name.replace(" ", "_").lower()

                # Try to find associated mobile device
                mobile_device_id = await self._find_mobile_device_for_person(
                    entity_id, state
                )
                notification_service = self._config.notification_mapping.get(entity_id)

                # Create person info
                person_info = PersonEntityInfo(
                    entity_id=entity_id,
                    name=name,
                    friendly_name=friendly_name,
                    state=state.state,
                    is_home=(state.state == STATE_HOME),
                    last_updated=state.last_updated,
                    mobile_device_id=mobile_device_id,
                    notification_service=notification_service,
                    attributes=dict(state.attributes),
                )

                new_persons[entity_id] = person_info
                discovered_count += 1

            # Update persons dictionary
            self._persons = new_persons
            self._stats["persons_discovered"] = len(self._persons)
            self._stats["discovery_runs"] += 1
            self._last_discovery = dt_util.now()

            # Clear cache since persons may have changed
            self._targets_cache.clear()

            _LOGGER.debug(
                "Discovery completed: %d person entities found, %d home",
                discovered_count,
                len(self.get_home_persons()),
            )

        except Exception as err:
            _LOGGER.error("Failed to discover person entities: %s", err)

    async def _find_mobile_device_for_person(
        self, person_entity_id: str, person_state: State
    ) -> str | None:
        """Find mobile device associated with person entity.

        Args:
            person_entity_id: Person entity ID
            person_state: Person state object

        Returns:
            Mobile device ID if found
        """
        try:
            # Check if person has source attribute pointing to device tracker
            source = person_state.attributes.get("source")
            if source and source.startswith("device_tracker."):
                # Try to map device tracker to mobile device
                source.replace("device_tracker.", "").replace("_", " ").title()

                # Common mobile app service patterns
                mobile_patterns = [
                    f"mobile_app_{source.split('.')[-1]}",
                    f"mobile_app_{person_state.attributes.get('friendly_name', '').replace(' ', '_').lower()}",
                    f"mobile_app_{person_entity_id.split('.')[-1]}",
                ]

                # Check if any of these services exist
                for pattern in mobile_patterns:
                    if self.hass.services.has_service("notify", pattern):
                        return pattern

            # Check user_id attribute for Home Assistant user mapping
            user_id = person_state.attributes.get("user_id")
            if user_id:
                # This would require access to user registry which needs caution
                # For now, we'll use a simplified approach
                pass

            return None

        except Exception as err:
            _LOGGER.debug(
                "Failed to find mobile device for %s: %s", person_entity_id, err
            )
            return None

    async def _setup_state_tracking(self) -> None:
        """Set up state change tracking for person entities."""
        if not self._persons:
            return

        person_entity_ids = list(self._persons.keys())

        async def handle_person_state_change(
            event: Event[EventStateChangedData],
        ) -> None:
            await self._handle_person_state_change(event)

        # Track state changes for all person entities
        listener = async_track_state_change_event(
            self.hass, person_entity_ids, handle_person_state_change
        )

        self._state_listeners.append(listener)

        _LOGGER.debug(
            "Set up state tracking for %d person entities", len(person_entity_ids)
        )

    async def _handle_person_state_change(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle person entity state changes.

        Args:
            event: State change event
        """
        entity_id = event.data["entity_id"]
        new_state = event.data["new_state"]

        if not new_state or entity_id not in self._persons:
            return

        # Update person info
        person_info = self._persons[entity_id]
        old_is_home = person_info.is_home

        person_info.state = new_state.state
        person_info.is_home = new_state.state == STATE_HOME
        person_info.last_updated = new_state.last_updated
        person_info.attributes = dict(new_state.attributes)

        # Clear cache if home status changed
        if old_is_home != person_info.is_home:
            self._targets_cache.clear()

            _LOGGER.debug(
                "Person %s status changed: %s -> %s",
                person_info.friendly_name,
                "home" if old_is_home else "away",
                "home" if person_info.is_home else "away",
            )

    async def _start_discovery_task(self) -> None:
        """Start periodic discovery task."""
        if self._discovery_task is not None:
            return

        async def discovery_loop() -> None:
            while True:
                try:
                    await asyncio.sleep(self._config.discovery_interval)
                    await self._discover_person_entities()
                except asyncio.CancelledError:
                    break
                except Exception as err:
                    _LOGGER.error("Discovery task error: %s", err)

        self._discovery_task = asyncio.create_task(discovery_loop())

        _LOGGER.debug(
            "Started discovery task with %d second interval",
            self._config.discovery_interval,
        )

    def get_home_persons(self) -> list[PersonEntityInfo]:
        """Get all persons currently at home.

        Returns:
            List of person entities at home
        """
        return [person for person in self._persons.values() if person.is_home]

    def get_away_persons(self) -> list[PersonEntityInfo]:
        """Get all persons currently away.

        Returns:
            List of person entities away from home
        """
        return [person for person in self._persons.values() if not person.is_home]

    def get_all_persons(self) -> list[PersonEntityInfo]:
        """Get all discovered person entities.

        Returns:
            List of all person entities
        """
        return list(self._persons.values())

    def get_person_by_entity_id(self, entity_id: str) -> PersonEntityInfo | None:
        """Get person info by entity ID.

        Args:
            entity_id: Person entity ID

        Returns:
            Person info if found
        """
        return self._persons.get(entity_id)

    def get_notification_targets(
        self,
        include_away: bool | None = None,
        priority_only: bool = False,
        cache_key: str | None = None,
    ) -> list[str]:
        """Get list of notification targets based on current person states.

        Args:
            include_away: Whether to include away persons (overrides config)
            priority_only: Only return priority persons
            cache_key: Optional cache key for performance

        Returns:
            List of notification service names
        """
        # Use provided setting or config default
        if include_away is None:
            include_away = self._config.include_away_persons

        # Create cache key
        if cache_key is None:
            cache_key = f"targets_{include_away}_{priority_only}"

        # Check cache
        now = dt_util.now()
        cached_targets = self._targets_cache.try_get(
            cache_key, now=now, ttl=self._config.cache_ttl
        )
        if cached_targets is not None:
            self._stats["cache_hits"] += 1
            return list(cached_targets)

        self._stats["cache_misses"] += 1

        # Build targets list
        targets = []

        # Get persons to consider
        persons = self.get_all_persons() if include_away else self.get_home_persons()

        # Filter by priority if requested
        if priority_only:
            persons = [
                p for p in persons if p.entity_id in self._config.priority_persons
            ]

        # Extract notification services
        for person in persons:
            # Use explicit mapping first
            if person.notification_service:
                targets.append(person.notification_service)
            # Try auto-detected mobile device
            elif person.mobile_device_id:
                targets.append(person.mobile_device_id)
            # Fallback to generic mobile app pattern
            else:
                mobile_service = f"mobile_app_{person.name}"
                if self.hass.services.has_service("notify", mobile_service):
                    targets.append(mobile_service)

        # Add static fallback targets if configured and no persons found
        if not targets and self._config.fallback_to_static:
            targets.extend(self._config.static_notification_targets)

        stored_targets = self._targets_cache.store(cache_key, targets, now)

        self._stats["notifications_targeted"] += 1

        return list(stored_targets)

    def get_notification_context(self) -> PersonNotificationContext:
        """Get notification context for personalized messages.

        Returns:
            Context dictionary with person information
        """
        home_persons = self.get_home_persons()
        away_persons = self.get_away_persons()

        return {
            "persons_home": len(home_persons),
            "persons_away": len(away_persons),
            "home_person_names": [p.friendly_name for p in home_persons],
            "away_person_names": [p.friendly_name for p in away_persons],
            "total_persons": len(self._persons),
            "has_anyone_home": len(home_persons) > 0,
            "everyone_away": len(home_persons) == 0 and len(away_persons) > 0,
        }

    async def async_force_discovery(self) -> dict[str, Any]:
        """Force immediate person discovery.

        Returns:
            Discovery results
        """
        async with self._lock:
            old_count = len(self._persons)
            await self._discover_person_entities()
            new_count = len(self._persons)

            return {
                "previous_count": old_count,
                "current_count": new_count,
                "persons_added": max(0, new_count - old_count),
                "persons_removed": max(0, old_count - new_count),
                "home_persons": len(self.get_home_persons()),
                "away_persons": len(self.get_away_persons()),
                "discovery_time": self._last_discovery.isoformat(),
            }

    async def async_update_config(self, new_config: dict[str, Any]) -> bool:
        """Update person entity configuration.

        Args:
            new_config: New configuration dictionary

        Returns:
            True if configuration was updated
        """
        async with self._lock:
            try:
                old_enabled = self._config.enabled

                # Update configuration
                await self.async_initialize(new_config)

                # Handle enable/disable state changes
                if old_enabled != self._config.enabled:
                    if self._config.enabled:
                        _LOGGER.info("Person entity integration enabled")
                    else:
                        _LOGGER.info("Person entity integration disabled")
                        await self.async_shutdown()

                return True

            except Exception as err:
                _LOGGER.error("Failed to update person entity config: %s", err)
                return False

    def get_statistics(self) -> PersonEntityStats:
        """Get comprehensive statistics.

        Returns:
            Statistics dictionary
        """
        now = dt_util.now()
        uptime = (now - self._last_discovery).total_seconds()

        cache_hits = self._stats["cache_hits"]
        cache_misses = self._stats["cache_misses"]
        total_events = max(1, cache_hits + cache_misses)

        return {
            **self._stats,
            "config": {
                "enabled": self._config.enabled,
                "auto_discovery": self._config.auto_discovery,
                "discovery_interval": self._config.discovery_interval,
                "include_away_persons": self._config.include_away_persons,
                "fallback_to_static": self._config.fallback_to_static,
            },
            "current_state": {
                "total_persons": len(self._persons),
                "home_persons": len(self.get_home_persons()),
                "away_persons": len(self.get_away_persons()),
                "last_discovery": self._last_discovery.isoformat(),
                "uptime_seconds": uptime,
            },
            "cache": {
                "cache_entries": len(self._targets_cache),
                "hit_rate": (cache_hits / total_events) * 100.0,
            },
        }

    async def async_validate_configuration(self) -> dict[str, Any]:
        """Validate person entity configuration.

        Returns:
            Validation results
        """
        issues = []
        recommendations = []

        # Check if any persons were discovered
        if not self._persons:
            issues.append("No person entities discovered")
            recommendations.append(
                "Create person entities in Home Assistant for better targeting"
            )

        # Check static fallback configuration
        if (
            self._config.fallback_to_static
            and not self._config.static_notification_targets
        ):
            issues.append("Fallback to static enabled but no static targets configured")
            recommendations.append("Configure static notification targets as fallback")

        # Check notification mappings
        unmapped_persons = []
        for person in self._persons.values():
            if not person.notification_service and not person.mobile_device_id:
                unmapped_persons.append(person.friendly_name)  # noqa: PERF401

        if unmapped_persons:
            issues.append(
                f"Persons without notification mapping: {', '.join(unmapped_persons)}"
            )
            recommendations.append("Configure notification services for all persons")

        # Check excluded entities
        for excluded in self._config.excluded_entities:
            if excluded not in [p.entity_id for p in self._persons.values()]:
                issues.append(f"Excluded entity {excluded} not found")  # noqa: PERF401

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "recommendations": recommendations,
            "persons_configured": len(self._persons),
            "notification_targets_available": len(self.get_notification_targets()),
        }

    async def async_shutdown(self) -> None:
        """Shutdown person entity manager."""
        # Cancel discovery task
        if self._discovery_task and not self._discovery_task.done():
            self._discovery_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._discovery_task

        # Remove state listeners
        for listener in self._state_listeners:
            if callable(listener):
                listener()
        self._state_listeners.clear()

        # Clear data
        self._persons.clear()
        self._targets_cache.clear()

        _LOGGER.info("Person entity manager shutdown complete")

    def get_diagnostics(self) -> PersonEntityDiagnostics:
        """Return diagnostic metadata used by coordinator cache monitors."""

        now = dt_util.now()
        cache_entries = self._targets_cache.snapshot(
            now=now, ttl=self._config.cache_ttl
        )

        discovery_task_state: Literal[
            "not_started", "cancelled", "completed", "running"
        ]
        if self._discovery_task is None:
            discovery_task_state = "not_started"
        elif self._discovery_task.cancelled():
            discovery_task_state = "cancelled"
        elif self._discovery_task.done():
            discovery_task_state = "completed"
        else:
            discovery_task_state = "running"

        diagnostics: PersonEntityDiagnostics = {
            "cache_entries": cache_entries,
            "discovery_task_state": discovery_task_state,
            "listener_count": len(self._state_listeners),
            "manager_last_activity": self._last_discovery.isoformat(),
            "manager_last_activity_age_seconds": max(
                (now - self._last_discovery).total_seconds(), 0.0
            ),
            "summary": cast(JSONMutableMapping, dict(self.get_notification_context())),
        }

        return diagnostics

    def _build_person_snapshot(self) -> PersonEntitySnapshot:
        """Return a typed snapshot of discovered person entities."""

        persons: dict[str, PersonEntitySnapshotEntry] = {}
        for entity_id, info in self._persons.items():
            persons[entity_id] = {
                "entity_id": info.entity_id,
                "name": info.name,
                "friendly_name": info.friendly_name,
                "state": info.state,
                "is_home": info.is_home,
                "last_updated": info.last_updated.isoformat(),
                "mobile_device_id": info.mobile_device_id,
                "notification_service": info.notification_service,
            }

        return {
            "persons": persons,
            "notification_context": self.get_notification_context(),
        }

    def coordinator_snapshot(self) -> CacheDiagnosticsSnapshot:
        """Return a coordinator-friendly snapshot of statistics and diagnostics."""

        stats = self.get_statistics()
        diagnostics = self.get_diagnostics()
        snapshot = self._build_person_snapshot()

        return CacheDiagnosticsSnapshot(
            stats=cast(JSONMutableMapping, dict(stats)),
            diagnostics=diagnostics,
            snapshot=cast(JSONMutableMapping, dict(snapshot)),
        )

    def register_cache_monitors(
        self, registrar: CacheMonitorRegistrar, *, prefix: str = "person_entity"
    ) -> None:
        """Register the person targeting cache with the data manager registrar."""

        self._cache_registrar = registrar
        registrar.register_cache_monitor(f"{prefix}_targets", self)
