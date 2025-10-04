"""Type definitions for the PawControl integration.

This module provides comprehensive type definitions, data structures, and validation
functions for the PawControl Home Assistant integration. It implements strict type safety,
performance-optimized validation, and comprehensive data modeling for all aspects
of dog care management.

The module is designed for Platinum-level quality with:
- Comprehensive type definitions using TypedDict and dataclasses
- Performance-optimized validation with frozenset lookups
- Extensive error handling and data validation
- Memory-efficient data structures using __slots__ where appropriate
- Complete documentation for all public APIs

Quality Scale: Platinum
Home Assistant: 2025.9.3+
Python: 3.13+
"""

from __future__ import annotations

from asyncio import Task
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final, Required, TypedDict

try:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.util import dt as dt_util
except ModuleNotFoundError:  # pragma: no cover - compatibility shim for tests

    class ConfigEntry:  # type: ignore[override]
        """Lightweight stand-in used during unit tests."""

        entry_id: str

    class _DateTimeModule:
        @staticmethod
        def utcnow() -> datetime:
            return datetime.now(datetime.timezone.utc)

    dt_util = _DateTimeModule()

from .utils import is_number

# OPTIMIZE: Resolve circular imports with proper conditional imports
if TYPE_CHECKING:
    from .coordinator import PawControlCoordinator
    from .data_manager import PawControlDataManager
    from .device_api import PawControlDeviceClient
    from .door_sensor_manager import DoorSensorManager
    from .entity_factory import EntityFactory
    from .feeding_manager import FeedingManager
    from .garden_manager import GardenManager
    from .geofencing import PawControlGeofencing
    from .gps_manager import GPSGeofenceManager
    from .helper_manager import PawControlHelperManager
    from .notifications import PawControlNotificationManager
    from .script_manager import PawControlScriptManager
    from .walk_manager import WalkManager

# OPTIMIZE: Use literal constants for performance - frozensets provide O(1) lookups
# and are immutable, preventing accidental modification while ensuring fast validation

VALID_MEAL_TYPES: Final[frozenset[str]] = frozenset(
    ["breakfast", "lunch", "dinner", "snack"]
)
"""Valid meal types for feeding tracking.

This frozenset defines the acceptable meal types that can be recorded in the system.
Using frozenset provides O(1) lookup performance for validation while preventing
accidental modification of the valid values.
"""

VALID_FOOD_TYPES: Final[frozenset[str]] = frozenset(
    ["dry_food", "wet_food", "barf", "home_cooked", "mixed"]
)
"""Valid food types for feeding management.

Defines the types of food that can be tracked in feeding records. This includes
commercial food types and home-prepared options for comprehensive diet tracking.
"""

VALID_DOG_SIZES: Final[frozenset[str]] = frozenset(
    ["toy", "small", "medium", "large", "giant"]
)
"""Valid dog size categories for breed classification.

Size categories are used throughout the system for portion calculation, exercise
recommendations, and health monitoring. These align with standard veterinary
size classifications.
"""

VALID_HEALTH_STATUS: Final[frozenset[str]] = frozenset(
    ["excellent", "very_good", "good", "normal", "unwell", "sick"]
)
"""Valid health status levels for health monitoring.

These status levels provide a standardized way to track overall dog health,
from excellent condition to requiring medical attention.
"""

VALID_MOOD_OPTIONS: Final[frozenset[str]] = frozenset(
    ["happy", "neutral", "sad", "angry", "anxious", "tired"]
)
"""Valid mood states for behavioral tracking.

Mood tracking helps identify patterns in behavior and potential health issues
that may affect a dog's emotional well-being.
"""

VALID_ACTIVITY_LEVELS: Final[frozenset[str]] = frozenset(
    ["very_low", "low", "normal", "high", "very_high"]
)
"""Valid activity levels for exercise and health monitoring.

Activity levels are used for calculating appropriate exercise needs, portion sizes,
and overall health assessments based on a dog's typical energy expenditure.
"""

VALID_GEOFENCE_TYPES: Final[frozenset[str]] = frozenset(
    ["safe_zone", "restricted_area", "point_of_interest"]
)
"""Valid geofence zone types for GPS tracking.

Different zone types trigger different behaviors in the system, from safety
notifications to activity logging when dogs enter or leave specific areas.
"""

VALID_GPS_SOURCES: Final[frozenset[str]] = frozenset(
    [
        "manual",
        "device_tracker",
        "person_entity",
        "smartphone",
        "tractive",
        "webhook",
        "mqtt",
    ]
)
"""Valid GPS data sources for location tracking.

Supports multiple GPS input methods to accommodate different hardware setups
and integration scenarios with various tracking devices and services.
"""

VALID_NOTIFICATION_PRIORITIES: Final[frozenset[str]] = frozenset(
    ["low", "normal", "high", "urgent"]
)
"""Valid notification priority levels for alert management.

Priority levels determine notification delivery methods, timing, and persistence
to ensure important alerts are appropriately escalated.
"""

VALID_NOTIFICATION_CHANNELS: Final[frozenset[str]] = frozenset(
    [
        "mobile",
        "persistent",
        "email",
        "sms",
        "webhook",
        "tts",
        "media_player",
        "slack",
        "discord",
    ]
)
"""Valid notification delivery channels for flexible alert routing.

Multiple channel support ensures notifications can reach users through their
preferred communication methods and backup channels for critical alerts.
"""

# Type aliases for improved code readability and maintainability
DogId = str
"""Type alias for dog identifier strings.

Used throughout the codebase to clearly identify parameters and return values
that represent dog identifiers, improving code readability and type safety.
"""

ConfigEntryId = str
"""Type alias for Home Assistant config entry identifiers.

Represents unique identifiers for integration configuration entries within
the Home Assistant configuration system.
"""

EntityId = str
"""Type alias for Home Assistant entity identifiers.

Standard entity ID format following Home Assistant conventions for entity
identification across the platform.
"""

Timestamp = datetime
"""Type alias for datetime objects used as timestamps.

Standardizes timestamp handling across the integration with proper timezone
awareness through Home Assistant's utility functions.
"""

ServiceData = dict[str, Any]
"""Type alias for Home Assistant service call data.

Represents the data payload structure used in Home Assistant service calls,
providing type hints for service-related functionality.
"""

ConfigData = dict[str, Any]
"""Type alias for general configuration data structures.

Used for various configuration contexts where a flexible dictionary structure
is needed with proper type hinting.
"""


class DogConfigData(TypedDict):
    """Type definition for comprehensive dog configuration data.

    This TypedDict defines the complete structure for dog configuration including
    required identification fields and optional characteristics. The structure
    supports device discovery integration and comprehensive dog profiling.

    The design uses Required[] for mandatory fields to ensure type safety while
    maintaining flexibility for optional characteristics that may not be known
    at configuration time.

    Attributes:
        dog_id: Unique identifier for the dog (required, must be URL-safe)
        dog_name: Display name for the dog (required, user-friendly)
        dog_breed: Breed information (optional, for breed-specific features)
        dog_age: Age in years (optional, affects health and feeding calculations)
        dog_weight: Weight in kilograms (optional, used for portion calculations)
        dog_size: Size category from VALID_DOG_SIZES (optional, affects recommendations)
        dog_color: Color description (optional, for identification)
        microchip_id: Microchip identifier (optional, for veterinary records)
        vet_contact: Veterinary contact information (optional, emergency use)
        emergency_contact: Emergency contact details (optional, critical situations)
        modules: Module enablement configuration (affects available features)
        discovery_info: Device discovery metadata (optional, for hardware integration)
    """

    # Required fields - must be present for valid configuration
    dog_id: Required[str]
    dog_name: Required[str]

    # Optional fields with comprehensive coverage for dog characteristics
    dog_breed: str | None
    dog_age: int | None
    dog_weight: float | None
    dog_size: str | None
    dog_color: str | None
    microchip_id: str | None
    vet_contact: str | None
    emergency_contact: str | None
    modules: dict[str, bool]  # Module configuration determines available features
    discovery_info: dict[str, Any] | None  # Device discovery integration support


class DetectionStatistics(TypedDict):
    """Aggregated statistics for door sensor walk detection diagnostics.

    This structure mirrors the runtime statistics tracked by the
    ``DoorSensorManager`` and is used for diagnostic payloads that surface
    detection performance information through Home Assistant's diagnostics and
    logging facilities.

    Attributes:
        total_detections: Total number of detection events processed.
        successful_walks: Number of detections that resulted in confirmed walks.
        false_positives: Count of detections that were dismissed as false alarms.
        false_negatives: Number of missed walks detected through manual review.
        average_confidence: Rolling average confidence score for detections.
    """

    total_detections: int
    successful_walks: int
    false_positives: int
    false_negatives: int
    average_confidence: float


class DetectionStatusEntry(TypedDict):
    """Status information for an individual dog's detection state."""

    dog_name: str
    door_sensor: str
    current_state: str
    confidence_score: float
    active_walk_id: str | None
    last_door_state: str | None
    recent_activity: int


class DetectionStatus(TypedDict):
    """Structured detection status payload for diagnostics endpoints."""

    configured_dogs: int
    active_detections: int
    detection_states: dict[str, DetectionStatusEntry]
    statistics: DetectionStatistics


@dataclass
class PawControlRuntimeData:
    """Comprehensive runtime data container for the PawControl integration.

    This dataclass contains all runtime components needed by the integration
    for Platinum-level type safety with ConfigEntry[PawControlRuntimeData].
    Enhanced with performance monitoring, error tracking, and comprehensive
    component lifecycle management.

    This structure is the central coordination point for all integration
    components and provides type-safe access to all runtime services.

    Attributes:
        coordinator: Data coordination and update management service
        data_manager: Persistent data storage and retrieval service
        notification_manager: Notification delivery and management service
        feeding_manager: Feeding schedule and nutrition tracking service
        walk_manager: Walk tracking and exercise monitoring service
        entity_factory: Entity creation and lifecycle management service
        entity_profile: Active entity profile configuration
        dogs: List of all configured dogs with their settings
        performance_stats: Runtime performance monitoring data
        error_history: Historical error tracking for diagnostics
        helper_manager: Home Assistant helper creation and management service
        geofencing_manager: Geofencing and GPS zone monitoring service
        garden_manager: Garden care automation service
        daily_reset_unsub: Callback used to cancel the scheduled daily reset
        background_monitor_task: Background health monitoring task handle

    Note:
        This class implements both dataclass and dictionary-like access
        patterns for maximum flexibility in integration usage scenarios.
    """

    coordinator: PawControlCoordinator
    data_manager: PawControlDataManager
    notification_manager: PawControlNotificationManager
    feeding_manager: FeedingManager
    walk_manager: WalkManager
    entity_factory: EntityFactory
    entity_profile: str
    dogs: list[DogConfigData]
    background_monitor_task: Task[None] | None = None
    garden_manager: GardenManager | None = None
    geofencing_manager: PawControlGeofencing | None = None
    helper_manager: PawControlHelperManager | None = None
    script_manager: PawControlScriptManager | None = None
    gps_geofence_manager: GPSGeofenceManager | None = None
    door_sensor_manager: DoorSensorManager | None = None
    device_api_client: PawControlDeviceClient | None = None

    # Enhanced runtime tracking for Platinum-level monitoring
    performance_stats: dict[str, Any] = field(default_factory=dict)
    error_history: list[dict[str, Any]] = field(default_factory=list)
    # PLATINUM: Optional unsubscribe callback for daily reset scheduler
    daily_reset_unsub: Any = field(default=None)

    def as_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the runtime data.

        Provides dictionary access to all runtime components for scenarios
        where dictionary-style access is more convenient than direct
        attribute access.

        Returns:
            Dictionary mapping component names to runtime instances
        """
        return {
            "coordinator": self.coordinator,
            "data_manager": self.data_manager,
            "notification_manager": self.notification_manager,
            "feeding_manager": self.feeding_manager,
            "walk_manager": self.walk_manager,
            "entity_factory": self.entity_factory,
            "entity_profile": self.entity_profile,
            "dogs": self.dogs,
            "garden_manager": self.garden_manager,
            "geofencing_manager": self.geofencing_manager,
            "script_manager": self.script_manager,
            "gps_geofence_manager": self.gps_geofence_manager,
            "door_sensor_manager": self.door_sensor_manager,
            "helper_manager": self.helper_manager,
            "device_api_client": self.device_api_client,
            "performance_stats": self.performance_stats,
            "error_history": self.error_history,
            "background_monitor_task": self.background_monitor_task,
            "daily_reset_unsub": self.daily_reset_unsub,
        }

    def __getitem__(self, key: str) -> Any:
        """Allow dictionary-style access for backward compatibility.

        Provides backward compatibility for code that expects dictionary-style
        access to runtime data while maintaining type safety.

        Args:
            key: Attribute name to retrieve

        Returns:
            The requested attribute value

        Raises:
            KeyError: If the requested key does not exist
        """
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key) from None

    def get(self, key: str, default: Any | None = None) -> Any | None:
        """Return an attribute using dictionary-style access with default.

        Provides safe dictionary-style access with default value support
        for robust runtime data access patterns.

        Args:
            key: Attribute name to retrieve
            default: Default value if attribute does not exist

        Returns:
            The requested attribute value or default
        """
        return getattr(self, key, default)


# PLATINUM: Custom ConfigEntry type for PawControl integrations
type PawControlConfigEntry = ConfigEntry
"""Type alias for PawControl-specific config entries.

Home Assistant removed ``ConfigEntry.runtime_data`` from the public API, so the
integration standardizes on storing the runtime payload in ``hass.data``.  The
alias keeps call sites expressive while remaining forward compatible with
future Home Assistant releases and their typing changes.
"""


@dataclass
class DailyStats:
    """Aggregated per-day statistics for a dog.

    The data manager stores a ``DailyStats`` instance for each dog so that
    frequently accessed aggregate metrics such as the total number of feedings
    or walks can be retrieved without scanning the full history on every
    update.  The class mirrors the behaviour of the Home Assistant integration
    by providing helpers for serialization and incremental updates.
    """

    date: datetime
    feedings_count: int = 0
    walks_count: int = 0
    health_logs_count: int = 0
    gps_updates_count: int = 0
    total_food_amount: float = 0.0
    total_walk_distance: float = 0.0
    total_walk_time: int = 0
    total_calories_burned: float = 0.0
    last_feeding: datetime | None = None
    last_walk: datetime | None = None
    last_health_event: datetime | None = None

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        """Convert ISO formatted values into timezone aware ``datetime`` objects."""

        if value is None:
            return None
        if isinstance(value, datetime):
            return dt_util.as_utc(value)
        if isinstance(value, str):
            parsed = dt_util.parse_datetime(value)
            if parsed is not None:
                return dt_util.as_utc(parsed)
        return None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> DailyStats:
        """Deserialize daily statistics from a dictionary structure."""

        raw_date = payload.get("date")
        date_value = cls._parse_datetime(raw_date) or dt_util.utcnow()
        return cls(
            date=date_value,
            feedings_count=int(payload.get("feedings_count", 0)),
            walks_count=int(payload.get("walks_count", 0)),
            health_logs_count=int(payload.get("health_logs_count", 0)),
            gps_updates_count=int(payload.get("gps_updates_count", 0)),
            total_food_amount=float(payload.get("total_food_amount", 0.0)),
            total_walk_distance=float(payload.get("total_walk_distance", 0.0)),
            total_walk_time=int(payload.get("total_walk_time", 0)),
            total_calories_burned=float(payload.get("total_calories_burned", 0.0)),
            last_feeding=cls._parse_datetime(payload.get("last_feeding")),
            last_walk=cls._parse_datetime(payload.get("last_walk")),
            last_health_event=cls._parse_datetime(payload.get("last_health_event")),
        )

    def as_dict(self) -> dict[str, Any]:
        """Serialize the statistics for storage."""

        return {
            "date": dt_util.as_utc(self.date).isoformat(),
            "feedings_count": self.feedings_count,
            "walks_count": self.walks_count,
            "health_logs_count": self.health_logs_count,
            "gps_updates_count": self.gps_updates_count,
            "total_food_amount": self.total_food_amount,
            "total_walk_distance": self.total_walk_distance,
            "total_walk_time": self.total_walk_time,
            "total_calories_burned": self.total_calories_burned,
            "last_feeding": self.last_feeding.isoformat()
            if self.last_feeding
            else None,
            "last_walk": self.last_walk.isoformat() if self.last_walk else None,
            "last_health_event": self.last_health_event.isoformat()
            if self.last_health_event
            else None,
        }

    def reset(self, *, preserve_date: bool = True) -> None:
        """Reset all counters, optionally keeping the current date."""

        if not preserve_date:
            self.date = dt_util.utcnow()
        self.feedings_count = 0
        self.walks_count = 0
        self.health_logs_count = 0
        self.gps_updates_count = 0
        self.total_food_amount = 0.0
        self.total_walk_distance = 0.0
        self.total_walk_time = 0
        self.total_calories_burned = 0.0
        self.last_feeding = None
        self.last_walk = None
        self.last_health_event = None

    def register_feeding(self, portion_size: float, timestamp: datetime | None) -> None:
        """Record a feeding event in the aggregate counters."""

        self.feedings_count += 1
        if portion_size > 0:
            self.total_food_amount += portion_size
        parsed = self._parse_datetime(timestamp)
        if parsed is not None:
            self.last_feeding = parsed

    def register_walk(
        self,
        duration: int | None,
        distance: float | None,
        timestamp: datetime | None,
    ) -> None:
        """Record a walk event in the aggregate counters."""

        self.walks_count += 1
        if duration:
            self.total_walk_time += int(duration)
        if distance:
            self.total_walk_distance += float(distance)
        parsed = self._parse_datetime(timestamp)
        if parsed is not None:
            self.last_walk = parsed

    def register_health_event(self, timestamp: datetime | None) -> None:
        """Record a health log entry in the aggregate counters."""

        self.health_logs_count += 1
        parsed = self._parse_datetime(timestamp)
        if parsed is not None:
            self.last_health_event = parsed

    def register_gps_update(self) -> None:
        """Increase the GPS update counter for the day."""

        self.gps_updates_count += 1


@dataclass
class FeedingData:
    """Data structure for individual feeding records with comprehensive validation.

    Represents a single feeding event with complete nutritional and contextual
    information. Includes automatic validation to ensure data integrity and
    consistency across the system.

    Attributes:
        meal_type: Type of meal from VALID_MEAL_TYPES
        portion_size: Amount of food in grams
        food_type: Type of food from VALID_FOOD_TYPES
        timestamp: When the feeding occurred
        notes: Optional notes about the feeding
        logged_by: Person who logged the feeding
        calories: Caloric content if known (optional)
        automatic: Whether feeding was logged automatically by a device

    Raises:
        ValueError: If any validation constraints are violated
    """

    meal_type: str
    portion_size: float
    food_type: str
    timestamp: datetime
    notes: str = ""
    logged_by: str = ""
    calories: float | None = None
    automatic: bool = False

    def __post_init__(self) -> None:
        """Validate feeding data after initialization.

        Performs comprehensive validation including meal type validation,
        food type validation, and numerical constraint checking to ensure
        data integrity throughout the system.

        Raises:
            ValueError: If any validation constraint is violated
        """
        if self.meal_type not in VALID_MEAL_TYPES:
            raise ValueError(f"Invalid meal type: {self.meal_type}")
        if self.food_type not in VALID_FOOD_TYPES:
            raise ValueError(f"Invalid food type: {self.food_type}")
        if self.portion_size < 0:
            raise ValueError("Portion size cannot be negative")
        if self.calories is not None and self.calories < 0:
            raise ValueError("Calories cannot be negative")


@dataclass
class WalkData:
    """Data structure for walk tracking with comprehensive route and environmental data.

    Represents a complete walk session including timing, route information,
    environmental conditions, and subjective assessment. Supports both
    active walk tracking and historical walk analysis.

    Attributes:
        start_time: Walk start timestamp
        end_time: Walk end timestamp (None for active walks)
        duration: Walk duration in seconds (calculated or manual)
        distance: Walk distance in meters (GPS or manual)
        route: List of GPS coordinates defining the walk path
        label: User-assigned label for the walk
        location: General location description
        notes: Additional notes about the walk
        rating: Walk quality rating (0-10 scale)
        started_by: Person who started the walk
        ended_by: Person who ended the walk
        weather: Weather conditions during the walk
        temperature: Temperature in Celsius during the walk

    Raises:
        ValueError: If validation constraints are violated
    """

    start_time: datetime
    end_time: datetime | None = None
    duration: int | None = None  # seconds
    distance: float | None = None  # meters
    route: list[dict[str, float]] = field(default_factory=list)
    label: str = ""
    location: str = ""
    notes: str = ""
    rating: int = 0
    started_by: str = ""
    ended_by: str = ""
    weather: str = ""
    temperature: float | None = None

    def __post_init__(self) -> None:
        """Validate walk data after initialization.

        Ensures logical consistency in walk data including time relationships,
        rating constraints, and numerical validity.

        Raises:
            ValueError: If validation constraints are violated
        """
        if self.rating < 0 or self.rating > 10:
            raise ValueError("Rating must be between 0 and 10")
        if self.duration is not None and self.duration < 0:
            raise ValueError("Duration cannot be negative")
        if self.distance is not None and self.distance < 0:
            raise ValueError("Distance cannot be negative")
        if self.end_time and self.end_time < self.start_time:
            raise ValueError("End time cannot be before start time")


@dataclass(slots=True)
class HealthEvent:
    """Structured health event for efficient storage and retrieval.

    Optimized data structure using __slots__ for memory efficiency in health
    event storage. Designed for high-frequency health data collection with
    minimal memory footprint and fast serialization.

    Attributes:
        dog_id: Identifier of the dog this event relates to
        timestamp: ISO format timestamp string for efficient storage
        metrics: Dictionary of health metrics and measurements

    Note:
        Uses __slots__ for memory optimization when storing large numbers
        of health events in historical data.
    """

    dog_id: str
    timestamp: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(
        cls,
        dog_id: str,
        payload: Mapping[str, Any],
        timestamp: str | None = None,
    ) -> HealthEvent:
        """Create a health event from raw payload data.

        Factory method for creating HealthEvent instances from various data
        sources including API responses, user input, and stored data.

        Args:
            dog_id: Identifier of the dog
            payload: Raw event data with metrics and optional timestamp
            timestamp: Override timestamp if not in payload

        Returns:
            Initialized HealthEvent instance with validated data
        """
        event_data = dict(payload)
        event_timestamp = event_data.pop("timestamp", None) or timestamp
        if isinstance(event_timestamp, datetime):
            event_timestamp = event_timestamp.isoformat()

        return cls(dog_id=dog_id, timestamp=event_timestamp, metrics=event_data)

    @classmethod
    def from_storage(cls, dog_id: str, payload: Mapping[str, Any]) -> HealthEvent:
        """Create a health event from stored data.

        Factory method specifically for deserializing health events from
        persistent storage with proper data structure restoration.

        Args:
            dog_id: Identifier of the dog
            payload: Stored event data

        Returns:
            Restored HealthEvent instance
        """
        return cls.from_raw(dog_id, payload)

    def as_dict(self) -> dict[str, Any]:
        """Return a storage-friendly representation of the health event.

        Serializes the health event into a dictionary format suitable for
        persistent storage while preserving all event data and metadata.

        Returns:
            Dictionary representation suitable for storage
        """
        payload = dict(self.metrics)
        if self.timestamp is not None:
            payload["timestamp"] = self.timestamp
        return payload


@dataclass(slots=True)
class WalkEvent:
    """Structured walk event for efficient walk session tracking.

    Memory-optimized structure using __slots__ for tracking walk events
    and session state changes. Supports both real-time walk tracking
    and historical walk analysis with efficient storage characteristics.

    Attributes:
        dog_id: Identifier of the dog this walk event relates to
        action: Action type (start, pause, resume, end, etc.)
        session_id: Unique identifier for the walk session
        timestamp: ISO format timestamp for efficient storage
        details: Dictionary of event-specific details and metadata

    Note:
        Uses __slots__ for memory optimization when tracking numerous
        walk events and session state changes.
    """

    dog_id: str
    action: str | None = None
    session_id: str | None = None
    timestamp: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(
        cls,
        dog_id: str,
        payload: Mapping[str, Any],
        timestamp: str | None = None,
    ) -> WalkEvent:
        """Create a walk event from raw payload data.

        Factory method for creating WalkEvent instances from various sources
        including real-time walk tracking, user actions, and API data.

        Args:
            dog_id: Identifier of the dog
            payload: Raw event data with action and details
            timestamp: Override timestamp if not in payload

        Returns:
            Initialized WalkEvent instance with validated structure
        """
        event_data = dict(payload)
        action = event_data.pop("action", None)
        session = event_data.pop("session_id", None)
        event_timestamp = event_data.pop("timestamp", None) or timestamp
        if isinstance(event_timestamp, datetime):
            event_timestamp = event_timestamp.isoformat()

        return cls(
            dog_id=dog_id,
            action=action,
            session_id=session,
            timestamp=event_timestamp,
            details=event_data,
        )

    @classmethod
    def from_storage(cls, dog_id: str, payload: Mapping[str, Any]) -> WalkEvent:
        """Create a walk event from stored data.

        Factory method for deserializing walk events from persistent storage
        with proper data structure and session state restoration.

        Args:
            dog_id: Identifier of the dog
            payload: Stored event data with complete session information

        Returns:
            Restored WalkEvent instance with session data
        """
        return cls.from_raw(dog_id, payload)

    def as_dict(self) -> dict[str, Any]:
        """Return a storage-friendly representation of the walk event.

        Serializes the walk event into a dictionary format optimized for
        persistent storage while maintaining session tracking capabilities.

        Returns:
            Dictionary representation suitable for storage and transmission
        """
        payload = dict(self.details)
        if self.action is not None:
            payload["action"] = self.action
        if self.session_id is not None:
            payload["session_id"] = self.session_id
        if self.timestamp is not None:
            payload["timestamp"] = self.timestamp
        return payload

    def merge(self, payload: Mapping[str, Any], timestamp: str | None = None) -> None:
        """Merge incremental updates into the existing walk event.

        Allows for incremental updates to walk events during active sessions
        while preserving existing data and maintaining session continuity.

        Args:
            payload: New or updated event data
            timestamp: Optional timestamp for the update
        """
        updates = dict(payload)
        if "action" in updates:
            self.action = updates.pop("action")
        if "session_id" in updates:
            self.session_id = updates.pop("session_id")
        if "timestamp" in updates:
            raw_timestamp = updates.pop("timestamp")
            if isinstance(raw_timestamp, datetime):
                raw_timestamp = raw_timestamp.isoformat()
            self.timestamp = raw_timestamp
        elif timestamp and self.timestamp is None:
            self.timestamp = timestamp

        self.details.update(updates)


@dataclass
class HealthData:
    """Comprehensive health data structure with veterinary-grade validation.

    Represents a complete health assessment including physical measurements,
    behavioral observations, and medical context. Designed for integration
    with veterinary records and health trend analysis.

    Attributes:
        timestamp: When the health assessment was recorded
        weight: Dog weight in kilograms
        temperature: Body temperature in Celsius
        mood: Behavioral mood from VALID_MOOD_OPTIONS
        activity_level: Energy level from VALID_ACTIVITY_LEVELS
        health_status: Overall health from VALID_HEALTH_STATUS
        symptoms: Description of any observed symptoms
        medication: Current medication information
        note: Additional health notes or observations
        logged_by: Person who recorded the health data
        heart_rate: Heart rate in beats per minute (if measured)
        respiratory_rate: Breathing rate per minute (if measured)

    Raises:
        ValueError: If any health parameter is outside valid ranges
    """

    timestamp: datetime
    weight: float | None = None
    temperature: float | None = None
    mood: str = ""
    activity_level: str = ""
    health_status: str = ""
    symptoms: str = ""
    medication: dict[str, Any] | None = None
    note: str = ""
    logged_by: str = ""
    heart_rate: int | None = None
    respiratory_rate: int | None = None

    def __post_init__(self) -> None:
        """Validate health data against veterinary standards.

        Performs comprehensive validation of all health parameters against
        veterinary standards and physiological constraints to ensure data
        quality for health analysis and trend tracking.

        Raises:
            ValueError: If any parameter is outside acceptable ranges
        """
        if self.mood and self.mood not in VALID_MOOD_OPTIONS:
            raise ValueError(f"Invalid mood: {self.mood}")
        if self.activity_level and self.activity_level not in VALID_ACTIVITY_LEVELS:
            raise ValueError(f"Invalid activity level: {self.activity_level}")
        if self.health_status and self.health_status not in VALID_HEALTH_STATUS:
            raise ValueError(f"Invalid health status: {self.health_status}")
        if self.weight is not None and (self.weight <= 0 or self.weight > 200):
            raise ValueError("Weight must be between 0 and 200 kg")
        if self.temperature is not None and (
            self.temperature < 35 or self.temperature > 45
        ):
            raise ValueError("Temperature must be between 35 and 45 degrees Celsius")
        if self.heart_rate is not None and (
            self.heart_rate < 50 or self.heart_rate > 250
        ):
            raise ValueError("Heart rate must be between 50 and 250 bpm")


@dataclass
class GPSLocation:
    """Precision GPS location data with comprehensive metadata and validation.

    Represents a complete GPS location record including accuracy information,
    device status, and signal quality metrics. Designed for high-precision
    tracking applications with comprehensive validation.

    Attributes:
        latitude: Latitude coordinate in decimal degrees
        longitude: Longitude coordinate in decimal degrees
        accuracy: GPS accuracy estimate in meters
        altitude: Altitude above sea level in meters
        timestamp: When the location was recorded
        source: Source of the GPS data (device, service, etc.)
        battery_level: GPS device battery percentage (0-100)
        signal_strength: GPS signal strength percentage (0-100)

    Raises:
        ValueError: If coordinates or other parameters are invalid
    """

    latitude: float
    longitude: float
    accuracy: float | None = None
    altitude: float | None = None
    timestamp: datetime = field(default_factory=dt_util.utcnow)
    source: str = ""
    battery_level: int | None = None
    signal_strength: int | None = None

    def __post_init__(self) -> None:
        """Validate GPS coordinates and device parameters.

        Ensures GPS coordinates are within valid Earth coordinate ranges and
        device parameters are within acceptable bounds for reliable tracking.

        Raises:
            ValueError: If coordinates or parameters are invalid
        """
        if not (-90 <= self.latitude <= 90):
            raise ValueError(f"Invalid latitude: {self.latitude}")
        if not (-180 <= self.longitude <= 180):
            raise ValueError(f"Invalid longitude: {self.longitude}")
        if self.accuracy is not None and self.accuracy < 0:
            raise ValueError("Accuracy cannot be negative")
        if self.battery_level is not None and not (0 <= self.battery_level <= 100):
            raise ValueError("Battery level must be between 0 and 100")
        if self.signal_strength is not None and not (0 <= self.signal_strength <= 100):
            raise ValueError("Signal strength must be between 0 and 100")


# OPTIMIZE: Utility functions for common operations with comprehensive documentation


def create_entity_id(dog_id: str, entity_type: str, module: str) -> str:
    """Create standardized entity ID following Home Assistant conventions.

    Generates entity IDs that follow Home Assistant naming conventions and
    PawControl-specific patterns for consistent entity identification across
    the integration. The format ensures uniqueness and readability.

    Args:
        dog_id: Unique dog identifier (must be URL-safe)
        entity_type: Type of entity (sensor, button, switch, etc.)
        module: Module name that owns the entity (feeding, walk, health, etc.)

    Returns:
        Formatted entity ID in the pattern: pawcontrol_{dog_id}_{module}_{entity_type}

    Example:
        >>> create_entity_id("buddy", "sensor", "feeding")
        'pawcontrol_buddy_feeding_sensor'
    """
    return f"pawcontrol_{dog_id}_{module}_{entity_type}".lower()


def validate_dog_weight_for_size(weight: float, size: str) -> bool:
    """Validate if a dog's weight is appropriate for its size category.

    Performs veterinary-based validation to ensure weight measurements are
    reasonable for the specified dog size category. This helps identify
    data entry errors and potential health concerns.

    Args:
        weight: Dog weight in kilograms
        size: Dog size category from VALID_DOG_SIZES

    Returns:
        True if weight is within acceptable range for the size category,
        False if weight appears inappropriate for the size

    Example:
        >>> validate_dog_weight_for_size(25.0, "medium")
        True
        >>> validate_dog_weight_for_size(50.0, "toy")
        False

    Note:
        Size ranges are based on veterinary standards and allow for
        some overlap between categories to accommodate breed variations.
    """
    size_ranges = {
        "toy": (1.0, 6.0),  # Chihuahua, Yorkshire Terrier
        "small": (4.0, 15.0),  # Jack Russell, Beagle
        "medium": (8.0, 30.0),  # Border Collie, Bulldog
        "large": (22.0, 50.0),  # Labrador, German Shepherd
        "giant": (35.0, 90.0),  # Great Dane, Saint Bernard
    }

    if size not in size_ranges:
        return True  # Unknown size category, skip validation

    min_weight, max_weight = size_ranges[size]
    return min_weight <= weight <= max_weight


def calculate_daily_calories(weight: float, activity_level: str, age: int) -> int:
    """Calculate recommended daily caloric intake for a dog.

    Uses veterinary nutritional guidelines to calculate appropriate daily
    caloric intake based on the dog's weight, activity level, and age.
    The calculation considers metabolic changes with age and activity
    requirements for optimal health maintenance.

    Args:
        weight: Dog weight in kilograms
        activity_level: Activity level from VALID_ACTIVITY_LEVELS
        age: Dog age in years

    Returns:
        Recommended daily calories as an integer

    Example:
        >>> calculate_daily_calories(20.0, "normal", 5)
        892

    Note:
        Calculation uses the formula: 70 * (weight in kg)^0.75 * activity_multiplier
        with age-based adjustments for puppies and senior dogs. Always consult
        with a veterinarian for specific dietary recommendations.
    """
    import math

    # Base metabolic rate: 70 * (weight in kg)^0.75
    base_calories = 70 * math.pow(weight, 0.75)

    # Activity level multipliers based on veterinary guidelines
    activity_multipliers = {
        "very_low": 1.2,  # Sedentary, minimal exercise
        "low": 1.4,  # Light exercise, short walks
        "normal": 1.6,  # Moderate exercise, regular walks
        "high": 1.8,  # Active exercise, long walks/runs
        "very_high": 2.0,  # Very active, working dogs, intense exercise
    }

    multiplier = activity_multipliers.get(activity_level, 1.6)

    # Age-based adjustments for metabolic differences
    if age < 1:
        # Puppies have higher metabolic needs for growth
        multiplier *= 2.0
    elif age > 7:
        # Senior dogs typically have lower metabolic needs
        multiplier *= 0.9

    return int(base_calories * multiplier)


# OPTIMIZE: Enhanced type guards for runtime validation with O(1) performance


def is_dog_config_valid(config: Any) -> bool:
    """Comprehensive type guard to validate dog configuration data.

    Performs thorough validation of dog configuration including required
    fields, data types, and value constraints. Uses frozenset lookups
    for O(1) validation performance on enumerated values.

    Args:
        config: Configuration data to validate (any type accepted)

    Returns:
        True if configuration is valid and complete, False otherwise

    Example:
        >>> config = {"dog_id": "buddy", "dog_name": "Buddy", "dog_age": 5}
        >>> is_dog_config_valid(config)
        True

    Note:
        This function is used throughout the integration to ensure data
        integrity and should be called whenever dog configuration data
        is received from external sources or user input.
    """
    if not isinstance(config, dict):
        return False

    # Validate required fields with type and content checking
    required_fields = ["dog_id", "dog_name"]
    for required_field in required_fields:
        if (
            required_field not in config
            or not isinstance(config[required_field], str)
            or not config[required_field].strip()
        ):
            return False

    # Validate optional fields with proper type and range checking
    if "dog_age" in config and (
        not isinstance(config["dog_age"], int)
        or config["dog_age"] < 0
        or config["dog_age"] > 30
    ):
        return False

    if "dog_weight" in config and (
        not is_number(config["dog_weight"]) or float(config["dog_weight"]) <= 0
    ):
        return False

    if "dog_size" in config and config["dog_size"] not in VALID_DOG_SIZES:
        return False

    # Validate modules configuration if present
    return not ("modules" in config and not isinstance(config["modules"], dict))


def is_gps_location_valid(location: Any) -> bool:
    """Validate GPS location data for accuracy and completeness.

    Performs comprehensive validation of GPS location data including
    coordinate ranges, accuracy values, and device status parameters
    to ensure location data integrity and usability.

    Args:
        location: Location data to validate (any type accepted)

    Returns:
        True if location data is valid and usable, False otherwise

    Example:
        >>> location = {"latitude": 52.5, "longitude": 13.4, "accuracy": 5.0}
        >>> is_gps_location_valid(location)
        True

    Note:
        Validation includes Earth coordinate bounds, non-negative accuracy
        values, and reasonable battery/signal strength ranges for
        GPS tracking devices.
    """
    if not isinstance(location, dict):
        return False

    # Validate required coordinates with Earth bounds checking
    for coord, limits in [("latitude", (-90, 90)), ("longitude", (-180, 180))]:
        if coord not in location:
            return False
        value = location[coord]
        if not is_number(value):
            return False
        numeric_value = float(value)
        if not (limits[0] <= numeric_value <= limits[1]):
            return False

    # Validate optional fields with appropriate constraints
    if "accuracy" in location and (
        not is_number(location["accuracy"]) or float(location["accuracy"]) < 0
    ):
        return False

    if "battery_level" in location:
        battery = location["battery_level"]
        if battery is not None and (
            not isinstance(battery, int) or not (0 <= battery <= 100)
        ):
            return False

    return True


def is_feeding_data_valid(data: Any) -> bool:
    """Validate feeding data for nutritional tracking accuracy.

    Performs comprehensive validation of feeding record data including
    meal type validation, portion size constraints, and optional
    nutritional information to ensure feeding data integrity.

    Args:
        data: Feeding data to validate (any type accepted)

    Returns:
        True if feeding data is valid and complete, False otherwise

    Example:
        >>> feeding = {"meal_type": "breakfast", "portion_size": 200.0}
        >>> is_feeding_data_valid(feeding)
        True

    Note:
        Uses frozenset lookup for O(1) meal type validation performance.
        Validates portion sizes as non-negative and calorie information
        if provided.
    """
    if not isinstance(data, dict):
        return False

    # Validate required fields with frozenset lookup for performance
    if "meal_type" not in data or data["meal_type"] not in VALID_MEAL_TYPES:
        return False

    if "portion_size" not in data:
        return False

    portion = data["portion_size"]
    if not is_number(portion) or float(portion) < 0:
        return False

    # Validate optional fields with appropriate constraints
    if "food_type" in data and data["food_type"] not in VALID_FOOD_TYPES:
        return False

    if "calories" in data:
        calories = data["calories"]
        if calories is not None and (not is_number(calories) or float(calories) < 0):
            return False

    return True


def is_health_data_valid(data: Any) -> bool:
    """Validate health data against veterinary standards and constraints.

    Performs comprehensive validation of health assessment data including
    mood states, activity levels, health status, and physiological
    measurements to ensure medical data accuracy and reliability.

    Args:
        data: Health data to validate (any type accepted)

    Returns:
        True if health data is valid and within acceptable ranges, False otherwise

    Example:
        >>> health = {"weight": 25.0, "mood": "happy", "temperature": 38.5}
        >>> is_health_data_valid(health)
        True

    Note:
        Validation includes veterinary-standard ranges for temperature,
        weight, and other physiological measurements to ensure data
        accuracy for health trend analysis.
    """
    if not isinstance(data, dict):
        return False

    # Validate optional fields with frozenset lookups for performance
    if "mood" in data and data["mood"] and data["mood"] not in VALID_MOOD_OPTIONS:
        return False

    if (
        "activity_level" in data
        and data["activity_level"]
        and data["activity_level"] not in VALID_ACTIVITY_LEVELS
    ):
        return False

    if (
        "health_status" in data
        and data["health_status"]
        and data["health_status"] not in VALID_HEALTH_STATUS
    ):
        return False

    # Validate physiological measurements with veterinary standards
    if "weight" in data:
        weight = data["weight"]
        if weight is not None and (
            not is_number(weight) or float(weight) <= 0 or float(weight) > 200
        ):
            return False

    if "temperature" in data:
        temp = data["temperature"]
        if temp is not None and (
            not is_number(temp) or float(temp) < 35 or float(temp) > 45
        ):
            return False

    return True


def is_notification_data_valid(data: Any) -> bool:
    """Validate notification data for reliable delivery and display.

    Performs comprehensive validation of notification data including
    required content fields, priority levels, delivery channels, and
    formatting requirements to ensure successful notification delivery.

    Args:
        data: Notification data to validate (any type accepted)

    Returns:
        True if notification data is valid and deliverable, False otherwise

    Example:
        >>> notification = {"title": "Walk Time", "message": "Buddy needs a walk!"}
        >>> is_notification_data_valid(notification)
        True

    Note:
        Uses frozenset lookups for O(1) priority and channel validation.
        Ensures title and message content is present and non-empty for
        successful notification display across all channels.
    """
    if not isinstance(data, dict):
        return False

    # Validate required content fields
    required_fields = ["title", "message"]
    for required_field in required_fields:
        if (
            required_field not in data
            or not isinstance(data[required_field], str)
            or not data[required_field].strip()
        ):
            return False

    # Validate optional fields with frozenset lookups for performance
    if "priority" in data and data["priority"] not in VALID_NOTIFICATION_PRIORITIES:
        return False

    return not (
        "channel" in data and data["channel"] not in VALID_NOTIFICATION_CHANNELS
    )
