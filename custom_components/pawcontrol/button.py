"""Profile-optimized button platform for PawControl integration.

UPDATED: Integrates profile-based entity optimization for reduced button count.
Reduces button entities from 20+ to 3-12 per dog based on profile selection.

OPTIMIZED: Thread-safe caching, consistent runtime_data usage, improved factory pattern.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any, Protocol, TypedDict, cast, runtime_checkable

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import Context, HomeAssistant, ServiceRegistry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import compat
from .compat import bind_exception_alias, ensure_homeassistant_exception_symbols
from .const import (
    ATTR_DOG_ID,
    ATTR_DOG_NAME,
    MODULE_FEEDING,
    MODULE_GARDEN,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
    SERVICE_ADD_GARDEN_ACTIVITY,
    SERVICE_CONFIRM_GARDEN_POOP,
    SERVICE_END_GARDEN_SESSION,
    SERVICE_END_WALK,
    SERVICE_FEED_DOG,
    SERVICE_LOG_HEALTH,
    SERVICE_NOTIFY_TEST,
    SERVICE_START_GARDEN_SESSION,
    SERVICE_START_GROOMING,
    SERVICE_START_WALK,
)
from .coordinator import PawControlCoordinator
from .diagnostics import _normalise_json as _normalise_diagnostics_json
from .entity import PawControlEntity
from .exceptions import WalkAlreadyInProgressError, WalkNotInProgressError
from .grooming_translations import (
    translated_grooming_label,
    translated_grooming_template,
)
from .runtime_data import get_runtime_data
from .types import (
    DOG_ID_FIELD,
    DOG_MODULES_FIELD,
    DOG_NAME_FIELD,
    WALK_IN_PROGRESS_FIELD,
    CoordinatorDogData,
    CoordinatorModuleState,
    CoordinatorTypedModuleName,
    DogConfigData,
    GardenModulePayload,
    GPSModulePayload,
    HealthModulePayload,
    JSONMapping,
    JSONMutableMapping,
    JSONValue,
    PawControlConfigEntry,
    WalkModulePayload,
    ensure_dog_config_data,
    ensure_dog_modules_projection,
    ensure_json_mapping,
)
from .utils import async_call_add_entities

_LOGGER = logging.getLogger(__name__)


def _normalise_attributes(
    attrs: Mapping[str, JSONValue] | JSONMutableMapping,
) -> JSONMutableMapping:
    """Return JSON-serialisable attributes for button entities."""

    payload = ensure_json_mapping(attrs)
    return cast(JSONMutableMapping, _normalise_diagnostics_json(payload))


ensure_homeassistant_exception_symbols()
HomeAssistantError: type[Exception] = cast(type[Exception], compat.HomeAssistantError)
ServiceValidationError: type[Exception] = cast(
    type[Exception], compat.ServiceValidationError
)
bind_exception_alias("HomeAssistantError", combine_with_current=True)
bind_exception_alias("ServiceValidationError")

if not hasattr(HomeAssistant, "services"):
    HomeAssistant.services = None  # type: ignore[attr-defined]


@runtime_checkable
class ServiceRegistryLike(Protocol):
    """Protocol describing the Home Assistant service registry surface."""

    async def async_call(
        self,
        domain: str,
        service: str,
        service_data: JSONMapping | JSONMutableMapping | None = None,
        blocking: bool = False,
        context: Context | None = None,
    ) -> None:
        """Invoke a Home Assistant service call."""


type ServiceRegistryType = ServiceRegistry | ServiceRegistryLike


class ButtonRule(TypedDict, total=False):
    """Typed metadata describing how to build a button for a module."""

    factory: type[PawControlButtonBase]
    type: str
    priority: int
    profiles: Sequence[str]
    args: Sequence[str]


class ButtonCandidate(TypedDict):
    """Candidate button produced by a rule before profile filtering."""

    button: PawControlButtonBase
    type: str
    priority: int


class _ServiceRegistryProxy(ServiceRegistryLike):
    """Proxy around Home Assistant's service registry to allow patching."""

    def __init__(self, registry: ServiceRegistryType) -> None:
        self._registry = registry

    async def async_call(
        self,
        domain: str,
        service: str,
        service_data: JSONMapping | JSONMutableMapping | None = None,
        blocking: bool = False,
        context: Context | None = None,
    ) -> None:
        await self._registry.async_call(
            domain,
            service,
            service_data,
            blocking,
            context,
        )

    def __getattr__(self, item: str) -> Any:
        return getattr(self._registry, item)


def _prepare_service_proxy(
    hass: HomeAssistant,
) -> ServiceRegistryLike | None:
    """Ensure the hass instance exposes a patchable services object."""

    services = getattr(hass, "services", None)

    if services is None:
        return None

    if isinstance(services, _ServiceRegistryProxy):
        return services

    if isinstance(services, ServiceRegistry):
        proxy = hass.data.get("_pawcontrol_service_proxy")
        if (
            not isinstance(proxy, _ServiceRegistryProxy)
            or proxy._registry is not services
        ):
            proxy = _ServiceRegistryProxy(services)
            hass.data["_pawcontrol_service_proxy"] = proxy
        hass.services = proxy
        return proxy

    if isinstance(services, ServiceRegistryLike):
        return services

    return None


# Home Assistant platform configuration
PARALLEL_UPDATES = 0

_TRUTHY_FLAG_VALUES: set[str] = {
    "true",
    "1",
    "yes",
    "y",
    "on",
    "active",
}
_FALSY_FLAG_VALUES: set[str] = {
    "false",
    "0",
    "no",
    "n",
    "off",
    "inactive",
    "",
}

# OPTIMIZATION: Profile-based entity reduction
PROFILE_BUTTON_LIMITS = {
    "basic": 3,  # Essential buttons only: test_notification, reset_stats, mark_fed
    "standard": 8,  # Include walk controls alongside feed/data management buttons
    "advanced": 12,  # Full button set
    "gps_focus": 8,  # GPS + essential buttons
    "health_focus": 7,  # Health + essential buttons
}

# Button priorities (1=highest, 4=lowest) for profile-based selection
BUTTON_PRIORITIES = {
    # Core buttons (always included)
    "test_notification": 1,
    "reset_daily_stats": 1,
    # Essential module buttons
    "feed_now": 1,
    "mark_fed": 2,
    "refresh_data": 2,
    "sync_data": 2,
    "start_walk": 2,
    "end_walk": 2,
    "start_garden_session": 2,
    "end_garden_session": 2,
    "refresh_location": 2,
    "log_weight": 2,
    # Advanced module buttons
    "feed_breakfast": 3,
    "feed_dinner": 3,
    "quick_walk": 3,
    "log_medication": 3,
    "start_grooming": 3,
    "log_garden_activity": 3,
    "center_map": 3,
    # Detailed buttons (lowest priority)
    "feed_lunch": 4,
    "feed_snack": 4,
    "log_walk_manually": 4,
    "toggle_visitor_mode": 2,
    "log_custom_feeding": 2,
    "confirm_garden_poop": 3,
    "export_route": 4,
    "call_dog": 4,
    "schedule_vet": 4,
    "health_check": 4,
}


class ProfileAwareButtonFactory:
    """Factory for creating profile-aware buttons with optimized performance.

    OPTIMIZED: Reduced redundant calls, improved caching, thread-safe operations.
    """

    def __init__(
        self, coordinator: PawControlCoordinator, profile: str = "standard"
    ) -> None:
        """Initialize button factory with profile.

        Args:
            coordinator: Data coordinator
            profile: Entity profile for button selection
        """
        self.coordinator = coordinator
        self.profile = profile
        self.max_buttons = PROFILE_BUTTON_LIMITS.get(profile, 6)

        # OPTIMIZED: Pre-calculate button rules for performance
        self._button_rules_cache: dict[str, list[ButtonRule]] = {}
        self._initialize_button_rules()

        _LOGGER.debug(
            "Initialized ProfileAwareButtonFactory with profile '%s' (max: %d buttons)",
            profile,
            self.max_buttons,
        )

    def _initialize_button_rules(self) -> None:
        """Pre-calculate button creation rules for each module to improve performance."""
        self._button_rules_cache = {
            MODULE_FEEDING: self._get_feeding_button_rules(),
            MODULE_WALK: self._get_walk_button_rules(),
            MODULE_GPS: self._get_gps_button_rules(),
            MODULE_HEALTH: self._get_health_button_rules(),
            MODULE_GARDEN: self._get_garden_button_rules(),
        }

    def _get_feeding_button_rules(self) -> list[ButtonRule]:
        """Get feeding button creation rules based on profile."""
        rules: list[ButtonRule] = [
            {
                "factory": PawControlFeedNowButton,
                "type": "feed_now",
                "priority": BUTTON_PRIORITIES["feed_now"],
                "profiles": ["basic", "standard", "advanced", "health_focus"],
            },
            {
                "factory": PawControlMarkFedButton,
                "type": "mark_fed",
                "priority": BUTTON_PRIORITIES["mark_fed"],
                "profiles": ["basic", "standard", "advanced", "health_focus"],
            },
        ]

        if self.profile in ["standard", "advanced", "health_focus"]:
            rules.extend(
                [
                    {
                        "factory": PawControlFeedMealButton,
                        "type": "feed_breakfast",
                        "priority": BUTTON_PRIORITIES["feed_breakfast"],
                        "profiles": ["standard", "advanced", "health_focus"],
                        "args": ("breakfast",),
                    },
                    {
                        "factory": PawControlFeedMealButton,
                        "type": "feed_dinner",
                        "priority": BUTTON_PRIORITIES["feed_dinner"],
                        "profiles": ["standard", "advanced", "health_focus"],
                        "args": ("dinner",),
                    },
                ]
            )

        if self.profile == "advanced":
            rules.extend(
                [
                    {
                        "factory": PawControlFeedMealButton,
                        "type": "feed_lunch",
                        "priority": BUTTON_PRIORITIES["feed_lunch"],
                        "profiles": ["advanced"],
                        "args": ("lunch",),
                    },
                    {
                        "factory": PawControlLogCustomFeedingButton,
                        "type": "log_custom_feeding",
                        "priority": BUTTON_PRIORITIES["log_custom_feeding"],
                        "profiles": ["advanced"],
                    },
                ]
            )

        return [rule for rule in rules if self.profile in rule["profiles"]]

    def _get_walk_button_rules(self) -> list[ButtonRule]:
        """Get walk button creation rules based on profile."""
        rules: list[ButtonRule] = [
            {
                "factory": PawControlStartWalkButton,
                "type": "start_walk",
                "priority": BUTTON_PRIORITIES["start_walk"],
                "profiles": ["basic", "standard", "advanced", "gps_focus"],
            },
            {
                "factory": PawControlEndWalkButton,
                "type": "end_walk",
                "priority": BUTTON_PRIORITIES["end_walk"],
                "profiles": ["basic", "standard", "advanced", "gps_focus"],
            },
        ]

        if self.profile in ["standard", "advanced", "gps_focus"]:
            rules.append(
                {
                    "factory": PawControlQuickWalkButton,
                    "type": "quick_walk",
                    "priority": BUTTON_PRIORITIES["quick_walk"],
                    "profiles": ["standard", "advanced", "gps_focus"],
                }
            )

        if self.profile == "advanced":
            rules.append(
                {
                    "factory": PawControlLogWalkManuallyButton,
                    "type": "log_walk_manually",
                    "priority": BUTTON_PRIORITIES["log_walk_manually"],
                    "profiles": ["advanced"],
                }
            )

        return [rule for rule in rules if self.profile in rule["profiles"]]

    def _get_gps_button_rules(self) -> list[ButtonRule]:
        """Get GPS button creation rules based on profile."""
        rules: list[ButtonRule] = [
            {
                "factory": PawControlRefreshLocationButton,
                "type": "refresh_location",
                "priority": BUTTON_PRIORITIES["refresh_location"],
                "profiles": ["basic", "standard", "advanced", "gps_focus"],
            }
        ]

        if self.profile in ["standard", "advanced", "gps_focus"]:
            rules.append(
                {
                    "factory": PawControlCenterMapButton,
                    "type": "center_map",
                    "priority": BUTTON_PRIORITIES["center_map"],
                    "profiles": ["standard", "advanced", "gps_focus"],
                }
            )

        if self.profile in ["advanced", "gps_focus"]:
            rules.extend(
                [
                    {
                        "factory": PawControlExportRouteButton,
                        "type": "export_route",
                        "priority": BUTTON_PRIORITIES["export_route"],
                        "profiles": ["advanced", "gps_focus"],
                    },
                    {
                        "factory": PawControlCallDogButton,
                        "type": "call_dog",
                        "priority": BUTTON_PRIORITIES["call_dog"],
                        "profiles": ["advanced", "gps_focus"],
                    },
                ]
            )

        return [rule for rule in rules if self.profile in rule["profiles"]]

    def _get_health_button_rules(self) -> list[ButtonRule]:
        """Get health button creation rules based on profile."""
        rules: list[ButtonRule] = [
            {
                "factory": PawControlLogWeightButton,
                "type": "log_weight",
                "priority": BUTTON_PRIORITIES["log_weight"],
                "profiles": ["basic", "standard", "advanced", "health_focus"],
            }
        ]

        if self.profile in ["standard", "advanced", "health_focus"]:
            rules.append(
                {
                    "factory": PawControlLogMedicationButton,
                    "type": "log_medication",
                    "priority": BUTTON_PRIORITIES["log_medication"],
                    "profiles": ["standard", "advanced", "health_focus"],
                }
            )

        if self.profile in ["advanced", "health_focus"]:
            rules.extend(
                [
                    {
                        "factory": PawControlStartGroomingButton,
                        "type": "start_grooming",
                        "priority": BUTTON_PRIORITIES["start_grooming"],
                        "profiles": ["advanced", "health_focus"],
                    },
                    {
                        "factory": PawControlScheduleVetButton,
                        "type": "schedule_vet",
                        "priority": BUTTON_PRIORITIES["schedule_vet"],
                        "profiles": ["advanced", "health_focus"],
                    },
                ]
            )

        if self.profile == "advanced":
            rules.append(
                {
                    "factory": PawControlHealthCheckButton,
                    "type": "health_check",
                    "priority": BUTTON_PRIORITIES["health_check"],
                    "profiles": ["advanced"],
                }
            )

        return [rule for rule in rules if self.profile in rule["profiles"]]

    def _get_garden_button_rules(self) -> list[ButtonRule]:
        """Get garden button creation rules based on profile."""

        rules: list[ButtonRule] = [
            {
                "factory": PawControlStartGardenSessionButton,
                "type": "start_garden_session",
                "priority": BUTTON_PRIORITIES["start_garden_session"],
                "profiles": [
                    "basic",
                    "standard",
                    "advanced",
                    "gps_focus",
                    "health_focus",
                ],
            },
            {
                "factory": PawControlEndGardenSessionButton,
                "type": "end_garden_session",
                "priority": BUTTON_PRIORITIES["end_garden_session"],
                "profiles": [
                    "basic",
                    "standard",
                    "advanced",
                    "gps_focus",
                    "health_focus",
                ],
            },
        ]

        if self.profile in ["standard", "advanced", "gps_focus", "health_focus"]:
            rules.append(
                {
                    "factory": PawControlLogGardenActivityButton,
                    "type": "log_garden_activity",
                    "priority": BUTTON_PRIORITIES["log_garden_activity"],
                    "profiles": ["standard", "advanced", "gps_focus", "health_focus"],
                }
            )

        if self.profile in ["advanced", "health_focus"]:
            rules.append(
                {
                    "factory": PawControlConfirmGardenPoopButton,
                    "type": "confirm_garden_poop",
                    "priority": BUTTON_PRIORITIES["confirm_garden_poop"],
                    "profiles": ["advanced", "health_focus"],
                }
            )

        return [rule for rule in rules if self.profile in rule["profiles"]]

    def create_buttons_for_dog(self, dog: DogConfigData) -> list[PawControlButtonBase]:
        """Create profile-optimized buttons for ``dog`` with strict typing."""

        dog_id = dog[DOG_ID_FIELD]
        dog_name = dog[DOG_NAME_FIELD]

        modules_projection = ensure_dog_modules_projection(dog)
        modules_mapping = modules_projection.mapping

        # Create all possible button candidates using pre-calculated rules
        button_candidates: list[ButtonCandidate] = []

        # Core buttons (always created)
        button_candidates.extend(
            [
                {
                    "button": PawControlTestNotificationButton(
                        self.coordinator, dog_id, dog_name
                    ),
                    "type": "test_notification",
                    "priority": BUTTON_PRIORITIES["test_notification"],
                },
                {
                    "button": PawControlResetDailyStatsButton(
                        self.coordinator, dog_id, dog_name
                    ),
                    "type": "reset_daily_stats",
                    "priority": BUTTON_PRIORITIES["reset_daily_stats"],
                },
                {
                    "button": PawControlRefreshDataButton(
                        self.coordinator, dog_id, dog_name
                    ),
                    "type": "refresh_data",
                    "priority": BUTTON_PRIORITIES["refresh_data"],
                },
                {
                    "button": PawControlSyncDataButton(
                        self.coordinator, dog_id, dog_name
                    ),
                    "type": "sync_data",
                    "priority": BUTTON_PRIORITIES["sync_data"],
                },
            ]
        )

        # OPTIMIZED: Use pre-calculated rules instead of creating them on-demand
        for module, enabled in modules_mapping.items():
            if not enabled or module not in self._button_rules_cache:
                continue

            module_rules = self._button_rules_cache[module]
            for rule in module_rules:
                try:
                    button_class = rule["factory"]
                    args = tuple(rule.get("args", ()))

                    button = button_class(self.coordinator, dog_id, dog_name, *args)

                    button_candidates.append(
                        {
                            "button": button,
                            "type": rule["type"],
                            "priority": rule["priority"],
                        }
                    )
                except Exception as err:
                    _LOGGER.warning(
                        "Failed to create button %s for %s: %s",
                        rule["type"],
                        dog_name,
                        err,
                    )

        # Profile-specific additional buttons
        if self.profile in ["advanced", "gps_focus"]:
            button_candidates.append(
                {
                    "button": PawControlToggleVisitorModeButton(
                        self.coordinator, dog_id, dog_name
                    ),
                    "type": "toggle_visitor_mode",
                    "priority": BUTTON_PRIORITIES["toggle_visitor_mode"],
                }
            )

        # Sort by priority and apply profile limit
        button_candidates.sort(key=lambda x: x["priority"])
        selected_candidates = button_candidates[: self.max_buttons]

        # Extract button entities
        buttons = [candidate["button"] for candidate in selected_candidates]
        selected_types = [candidate["type"] for candidate in selected_candidates]

        _LOGGER.info(
            "Created %d/%d buttons for %s (profile: %s): %s",
            len(buttons),
            len(button_candidates),
            dog_name,
            self.profile,
            ", ".join(selected_types),
        )

        return buttons


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PawControlConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PawControl button platform with profile-based optimization."""

    # OPTIMIZED: Consistent runtime_data usage for Platinum readiness
    runtime_data = get_runtime_data(hass, entry)
    if runtime_data is None:
        _LOGGER.error("Runtime data missing for entry %s", entry.entry_id)
        return
    coordinator = runtime_data.coordinator
    raw_dogs = getattr(runtime_data, "dogs", [])
    dog_configs: list[DogConfigData] = []
    for raw_dog in raw_dogs:
        if not isinstance(raw_dog, Mapping):
            continue

        normalised = ensure_dog_config_data(cast(JSONMapping, raw_dog))
        if normalised is None:
            continue

        modules_projection = ensure_dog_modules_projection(normalised)
        normalised[DOG_MODULES_FIELD] = modules_projection.config
        dog_configs.append(normalised)

    if not dog_configs:
        _LOGGER.warning("No dogs configured for button platform")
        return

    # Get profile from runtime data (consistent with other platforms)
    profile = runtime_data.entity_profile

    _LOGGER.info(
        "Setting up buttons with profile '%s' for %d dogs", profile, len(dog_configs)
    )

    # Initialize profile-aware factory
    button_factory = ProfileAwareButtonFactory(coordinator, profile)

    # Create profile-optimized entities
    all_entities: list[PawControlButtonBase] = []
    total_buttons_created = 0

    for dog in dog_configs:
        dog_id = dog[DOG_ID_FIELD]
        dog_name = dog[DOG_NAME_FIELD]

        dog_buttons = button_factory.create_buttons_for_dog(dog)
        all_entities.extend(dog_buttons)
        total_buttons_created += len(dog_buttons)

        _LOGGER.info(
            "Created %d buttons for dog: %s (%s) with profile '%s'",
            len(dog_buttons),
            dog_name,
            dog_id,
            profile,
        )

    # OPTIMIZATION: Smart batching based on reduced button count
    batch_size = 15  # Increased batch size for fewer entities

    if total_buttons_created <= batch_size:
        # Small setup: Add all at once
        await async_call_add_entities(
            async_add_entities, all_entities, update_before_add=False
        )
        _LOGGER.info(
            "Created %d button entities (single batch) - profile-optimized count",
            total_buttons_created,
        )
    else:
        # Large setup: Efficient batching
        # Create and execute batches concurrently while still awaiting helpers
        batches = [
            all_entities[i : i + batch_size]
            for i in range(0, len(all_entities), batch_size)
        ]

        await asyncio.gather(
            *(
                async_call_add_entities(
                    async_add_entities, batch, update_before_add=False
                )
                for batch in batches
            )
        )

        _LOGGER.info(
            "Created %d button entities for %d dogs (profile-based batching)",
            total_buttons_created,
            len(dog_configs),
        )

    # Log profile statistics
    max_possible = PROFILE_BUTTON_LIMITS.get(profile, 6)
    efficiency = (
        (max_possible * len(dog_configs) - total_buttons_created)
        / (max_possible * len(dog_configs))
        * 100
        if max_possible * len(dog_configs) > 0
        else 0
    )

    _LOGGER.info(
        "Profile '%s': avg %.1f buttons/dog (max %d) - %.1f%% entity reduction efficiency",
        profile,
        total_buttons_created / len(dog_configs),
        max_possible,
        efficiency,
    )


class PawControlButtonBase(PawControlEntity, ButtonEntity):
    """Optimized base button class with thread-safe caching and improved performance."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
        button_type: str,
        *,
        device_class: ButtonDeviceClass | None = None,
        icon: str | None = None,
        entity_category: str | None = None,
        action_description: str | None = None,
    ) -> None:
        """Initialize optimized button entity with thread-safe caching."""
        super().__init__(coordinator, dog_id, dog_name)
        self._button_type = button_type
        self._action_description = action_description

        # Entity configuration
        self._attr_unique_id = f"pawcontrol_{dog_id}_{button_type}"
        self._apply_name_suffix(button_type.replace("_", " ").title())
        self._attr_device_class = device_class
        self._attr_icon = icon
        self._attr_entity_category = entity_category

        # Link to virtual PawControl device for the dog
        self.update_device_metadata(model="Virtual Dog", sw_version="1.0.0")

        # OPTIMIZED: Thread-safe instance-level caching
        self._dog_data_cache: dict[str, CoordinatorDogData] = {}
        self._cache_timestamp: dict[str, float] = {}
        self._cache_ttl = 2.0  # 2 second cache for button actions

    def __setattr__(self, name: str, value: Any) -> None:
        """Intercept hass assignment to prepare a patch-friendly registry."""

        if name == "hass" and value is not None and isinstance(value, HomeAssistant):
            _prepare_service_proxy(value)

        super().__setattr__(name, value)

    @property
    def extra_state_attributes(self) -> JSONMutableMapping:
        """Return attributes with optimized caching."""

        attrs = ensure_json_mapping(super().extra_state_attributes)
        attrs.setdefault(ATTR_DOG_ID, self._dog_id)
        attrs.setdefault(ATTR_DOG_NAME, self._dog_name)
        attrs["button_type"] = self._button_type
        attrs["last_pressed"] = cast(str | None, getattr(self, "_last_pressed", None))

        if self._action_description:
            attrs["action_description"] = self._action_description

        return _normalise_attributes(attrs)

    def _get_dog_data_cached(self) -> CoordinatorDogData | None:
        """Get dog data with thread-safe instance-level caching."""
        cache_key = f"{self._dog_id}_data"
        now = dt_util.utcnow().timestamp()

        # Check cache validity
        if (
            cache_key in self._dog_data_cache
            and cache_key in self._cache_timestamp
            and now - self._cache_timestamp[cache_key] < self._cache_ttl
        ):
            return self._dog_data_cache[cache_key]

        # Cache miss - fetch fresh data
        if self.coordinator.available:
            data = self.coordinator.get_dog_data(self._dog_id)
            if data is not None:
                self._dog_data_cache[cache_key] = data
                self._cache_timestamp[cache_key] = now
                return data

        return None

    def _get_module_data(
        self, module: CoordinatorTypedModuleName
    ) -> CoordinatorModuleState | None:
        """Get module data from cached dog data."""
        dog_data = self._get_dog_data_cached()
        if not dog_data:
            return None

        module_data = dog_data.get(module)
        if module_data is None:
            return None

        if isinstance(module_data, Mapping):
            return cast(CoordinatorModuleState, module_data)

        _LOGGER.warning(
            "Invalid module data for %s/%s: expected mapping, got %s",
            self._dog_id,
            module,
            type(module_data).__name__,
        )
        return None

    def _get_walk_payload(self) -> WalkModulePayload | None:
        """Return the walk module payload if available."""

        walk_data = self._get_module_data(cast(CoordinatorTypedModuleName, MODULE_WALK))
        return cast(WalkModulePayload, walk_data) if walk_data is not None else None

    def _get_gps_payload(self) -> GPSModulePayload | None:
        """Return the GPS module payload if available."""

        gps_data = self._get_module_data(cast(CoordinatorTypedModuleName, MODULE_GPS))
        return cast(GPSModulePayload, gps_data) if gps_data is not None else None

    def _get_garden_payload(self) -> GardenModulePayload | None:
        """Return the garden module payload if available."""

        garden_data = self._get_module_data(
            cast(CoordinatorTypedModuleName, MODULE_GARDEN)
        )
        return (
            cast(GardenModulePayload, garden_data) if garden_data is not None else None
        )

    @staticmethod
    def _normalize_module_flag(value: Any, field: str) -> bool:
        """Normalise boolean-like flags reported by module payloads."""

        if isinstance(value, bool):
            return value

        if isinstance(value, (int, float)) and value in {0, 1}:
            return bool(value)

        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in _TRUTHY_FLAG_VALUES:
                return True
            if normalized in _FALSY_FLAG_VALUES:
                return False

        if value is not None:
            _LOGGER.debug(
                "Unhandled boolean flag for %s: %r (%s); treating as False",
                field,
                value,
                type(value).__name__,
            )

        return False

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        """Parse ISO-formatted datetime strings into aware datetimes."""

        if isinstance(value, datetime):
            return value

        if isinstance(value, str):
            parsed = dt_util.parse_datetime(value)
            if parsed is not None:
                return parsed

        return None

    @property
    def available(self) -> bool:
        """Check availability with optimized cache."""
        return self.coordinator.available and self._get_dog_data_cached() is not None

    def _ensure_patchable_services(
        self,
    ) -> ServiceRegistryLike | None:
        """Return a service registry object that supports attribute patching."""

        if self.hass is None:
            services = getattr(HomeAssistant, "services", None)
            if isinstance(services, ServiceRegistryLike):
                return services
            return None

        proxy = _prepare_service_proxy(self.hass)
        if proxy is not None:
            return proxy

        services = getattr(self.hass, "services", None)
        if isinstance(services, ServiceRegistryLike):
            return services
        return None

    async def _async_service_call(
        self,
        domain: str,
        service: str,
        data: Mapping[str, JSONValue] | JSONMutableMapping,
        **kwargs: Any,
    ) -> None:
        """Call a Home Assistant service via a patch-friendly proxy."""

        registry = self._ensure_patchable_services()
        if registry is None:
            _LOGGER.debug(
                "Service registry unavailable; skipping %s.%s call for %s",
                domain,
                service,
                self._dog_id,
            )
            return

        payload = _normalise_attributes(data)
        await registry.async_call(domain, service, payload, **kwargs)

    async def async_press(self) -> None:
        """Handle button press with timestamp tracking."""
        self._last_pressed = dt_util.utcnow().isoformat()
        _LOGGER.debug("Button pressed: %s for %s", self._button_type, self._dog_name)


# Core button implementations


class PawControlTestNotificationButton(PawControlButtonBase):
    """Button to send test notification."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialise the test-notification button."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "test_notification",
            icon="mdi:message-alert",
            action_description="Send a test notification",
        )

    async def async_press(self) -> None:
        """Send test notification."""
        await super().async_press()

        try:
            await self._async_service_call(
                "pawcontrol",
                SERVICE_NOTIFY_TEST,
                {
                    ATTR_DOG_ID: self._dog_id,
                    "message": f"Test notification for {self._dog_name}",
                },
                blocking=False,
            )
        except Exception as err:
            _LOGGER.error("Failed to send test notification: %s", err)
            raise HomeAssistantError(f"Failed to send notification: {err}") from err


class PawControlResetDailyStatsButton(PawControlButtonBase):
    """Button to reset daily statistics."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialise the daily statistics reset control."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "reset_daily_stats",
            device_class=ButtonDeviceClass.RESTART,
            icon="mdi:refresh",
            action_description="Reset daily statistics",
        )

    async def async_press(self) -> None:
        """Reset daily stats."""
        await super().async_press()

        try:
            runtime_data = get_runtime_data(self.hass, self.coordinator.config_entry)
            if runtime_data is None:
                raise HomeAssistantError("Runtime data not available")

            managers = runtime_data.runtime_managers
            data_manager = managers.data_manager or getattr(
                runtime_data, "data_manager", None
            )
            if data_manager is None:
                raise HomeAssistantError("Data manager not available")

            await data_manager.async_reset_dog_daily_stats(self._dog_id)
            await self.coordinator.async_request_selective_refresh(
                [self._dog_id], priority=8
            )

        except Exception as err:
            _LOGGER.error("Failed to reset daily stats: %s", err)
            raise HomeAssistantError(f"Failed to reset statistics: {err}") from err


class PawControlRefreshDataButton(PawControlButtonBase):
    """Button to trigger a coordinator refresh."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the manual refresh control."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "refresh_data",
            device_class=ButtonDeviceClass.UPDATE,
            icon="mdi:database-refresh",
            action_description="Refresh integration data",
        )

    async def async_press(self) -> None:
        """Request a full coordinator refresh."""
        await super().async_press()

        try:
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Failed to refresh coordinator data: %s", err)
            raise HomeAssistantError(f"Failed to refresh data: {err}") from err


class PawControlSyncDataButton(PawControlButtonBase):
    """Button to request a high-priority selective refresh."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the high-priority sync control."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "sync_data",
            device_class=ButtonDeviceClass.UPDATE,
            icon="mdi:database-sync",
            action_description="Synchronize dog data",
        )

    async def async_press(self) -> None:
        """Trigger a selective refresh with elevated priority."""
        await super().async_press()

        try:
            await self.coordinator.async_request_selective_refresh(
                [self._dog_id], priority=10
            )
        except Exception as err:
            _LOGGER.error("Failed to sync data: %s", err)
            raise HomeAssistantError(f"Failed to sync data: {err}") from err


class PawControlToggleVisitorModeButton(PawControlButtonBase):
    """Button to toggle visitor mode."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialise the visitor mode toggle control."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "toggle_visitor_mode",
            icon="mdi:account-switch",
            action_description="Toggle visitor mode",
        )

    async def async_press(self) -> None:
        """Toggle visitor mode."""
        await super().async_press()

        try:
            dog_data = self._get_dog_data_cached()
            current_mode = (
                dog_data.get("visitor_mode_active", False) if dog_data else False
            )

            await self._async_service_call(
                "pawcontrol",
                "set_visitor_mode",
                {
                    ATTR_DOG_ID: self._dog_id,
                    "enabled": not current_mode,
                    "visitor_name": "Manual Toggle",
                },
                blocking=False,
            )

        except Exception as err:
            _LOGGER.error("Failed to toggle visitor mode: %s", err)
            raise HomeAssistantError(f"Failed to toggle visitor mode: {err}") from err


class PawControlMarkFedButton(PawControlButtonBase):
    """Button to mark dog as fed with optimized meal type detection."""

    # OPTIMIZATION: Pre-calculated meal schedule lookup table
    _meal_schedule = {  # noqa: RUF012
        range(5, 11): "breakfast",
        range(11, 16): "lunch",
        range(16, 22): "dinner",
    }

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialise the smart feeding acknowledgement control."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "mark_fed",
            icon="mdi:food-drumstick",
            action_description="Mark dog as fed",
        )

    async def async_press(self) -> None:
        """Mark as fed with optimized meal type detection."""
        await super().async_press()

        try:
            # OPTIMIZATION: Faster meal type lookup using pre-calculated ranges
            hour = dt_util.now().hour
            meal_type = "snack"  # Default

            for time_range, meal in self._meal_schedule.items():
                if hour in time_range:
                    meal_type = meal
                    break

            await self._async_service_call(
                "pawcontrol",
                SERVICE_FEED_DOG,
                {
                    ATTR_DOG_ID: self._dog_id,
                    "meal_type": meal_type,
                    "portion_size": 0,
                },
                blocking=False,
            )

        except Exception as err:
            _LOGGER.error("Failed to mark as fed: %s", err)
            raise HomeAssistantError(f"Failed to log feeding: {err}") from err


class PawControlFeedNowButton(PawControlButtonBase):
    """Immediate feeding button for quick manual feedings."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialise the immediate feeding control."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "feed_now",
            icon="mdi:food-turkey",
            action_description="Feed dog immediately",
        )
        self._attr_name = f"{dog_name} Feed Now"
        self._attr_device_class = ButtonDeviceClass.IDENTIFY

    async def async_press(self) -> None:
        """Trigger an immediate feeding service call."""

        await super().async_press()

        try:
            await self._async_service_call(
                "pawcontrol",
                SERVICE_FEED_DOG,
                {
                    ATTR_DOG_ID: self._dog_id,
                    "meal_type": "immediate",
                    "portion_size": 1,
                },
                blocking=False,
            )
        except Exception as err:
            _LOGGER.error("Failed to feed now: %s", err)
            raise HomeAssistantError(f"Failed to feed now: {err}") from err


class PawControlFeedMealButton(PawControlButtonBase):
    """Button for specific meal type."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
        meal_type: str,
    ) -> None:
        """Initialise a shortcut button for a specific meal."""
        self._meal_type = meal_type
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            f"feed_{meal_type}",
            icon="mdi:food",
            action_description=f"Log {meal_type} feeding",
        )
        self._attr_name = f"{dog_name} Feed {meal_type.title()}"

    async def async_press(self) -> None:
        """Feed specific meal."""
        await super().async_press()

        try:
            await self._async_service_call(
                "pawcontrol",
                SERVICE_FEED_DOG,
                {
                    ATTR_DOG_ID: self._dog_id,
                    "meal_type": self._meal_type,
                    "portion_size": 0,
                },
                blocking=False,
            )

        except Exception as err:
            _LOGGER.error("Failed to feed %s: %s", self._meal_type, err)
            raise HomeAssistantError(f"Failed to log {self._meal_type}: {err}") from err


class PawControlLogCustomFeedingButton(PawControlButtonBase):
    """Button for custom feeding."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialise the custom feeding logging control."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "log_custom_feeding",
            icon="mdi:food-variant",
            action_description="Log custom feeding",
        )

    async def async_press(self) -> None:
        """Log custom feeding."""
        await super().async_press()

        try:
            await self._async_service_call(
                "pawcontrol",
                SERVICE_FEED_DOG,
                {
                    ATTR_DOG_ID: self._dog_id,
                    "meal_type": "snack",
                    "portion_size": 75,
                    "food_type": "dry_food",
                    "notes": "Custom feeding via button",
                },
                blocking=False,
            )

        except Exception as err:
            _LOGGER.error("Failed to log custom feeding: %s", err)
            raise HomeAssistantError(f"Failed to log custom feeding: {err}") from err


class PawControlStartWalkButton(PawControlButtonBase):
    """Button to start walk with enhanced error handling."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialise the walk start control with validation hooks."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "start_walk",
            icon="mdi:walk",
            action_description="Start tracking a walk",
        )
        self._attr_device_class = ButtonDeviceClass.IDENTIFY

    async def async_press(self) -> None:
        """Start walk with validation."""
        await super().async_press()

        try:
            walk_data = self._get_walk_payload()
            if walk_data and self._normalize_module_flag(
                walk_data.get(WALK_IN_PROGRESS_FIELD), WALK_IN_PROGRESS_FIELD
            ):
                walk_id = walk_data.get("current_walk_id", STATE_UNKNOWN)
                if not isinstance(walk_id, str):
                    walk_id = STATE_UNKNOWN
                start_time = self._parse_datetime(walk_data.get("current_walk_start"))
                raise WalkAlreadyInProgressError(
                    dog_id=self._dog_id,
                    walk_id=walk_id,
                    start_time=start_time,
                )

            await self._async_service_call(
                "pawcontrol",
                SERVICE_START_WALK,
                {
                    ATTR_DOG_ID: self._dog_id,
                    "label": "Manual walk",
                },
                blocking=False,
            )

        except ServiceValidationError as err:
            raise HomeAssistantError(str(err)) from err
        except Exception as err:
            _LOGGER.error("Failed to start walk: %s", err)
            raise HomeAssistantError(f"Failed to start walk: {err}") from err

    @property
    def available(self) -> bool:
        """Available if no walk in progress."""
        if not super().available:
            return False

        walk_data = self._get_walk_payload()
        if walk_data is None:
            return True

        return not self._normalize_module_flag(
            walk_data.get(WALK_IN_PROGRESS_FIELD), WALK_IN_PROGRESS_FIELD
        )


class PawControlEndWalkButton(PawControlButtonBase):
    """Button to end walk with enhanced validation."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialise the walk completion control."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "end_walk",
            icon="mdi:stop",
            action_description="End current walk",
        )
        self._attr_device_class = ButtonDeviceClass.IDENTIFY

    async def async_press(self) -> None:
        """End walk with validation."""
        await super().async_press()

        try:
            walk_data = self._get_walk_payload()
            if not walk_data or not self._normalize_module_flag(
                walk_data.get(WALK_IN_PROGRESS_FIELD), WALK_IN_PROGRESS_FIELD
            ):
                last_walk_time = (
                    self._parse_datetime(walk_data.get("last_walk"))
                    if walk_data
                    else None
                )
                raise WalkNotInProgressError(
                    dog_id=self._dog_id,
                    last_walk_time=last_walk_time,
                )

            await self._async_service_call(
                "pawcontrol",
                SERVICE_END_WALK,
                {ATTR_DOG_ID: self._dog_id},
                blocking=False,
            )

        except ServiceValidationError as err:
            raise HomeAssistantError(str(err)) from err
        except Exception as err:
            _LOGGER.error("Failed to end walk: %s", err)
            raise HomeAssistantError(f"Failed to end walk: {err}") from err

    @property
    def available(self) -> bool:
        """Available if walk in progress."""
        if not super().available:
            return False

        walk_data = self._get_walk_payload()
        if walk_data is None:
            return False

        return self._normalize_module_flag(
            walk_data.get(WALK_IN_PROGRESS_FIELD), WALK_IN_PROGRESS_FIELD
        )


class PawControlQuickWalkButton(PawControlButtonBase):
    """Button for quick walk with atomic operation."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialise the quick-walk logging control."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "quick_walk",
            icon="mdi:run-fast",
            action_description="Log quick 10-minute walk",
        )
        self._attr_device_class = ButtonDeviceClass.IDENTIFY

    async def async_press(self) -> None:
        """Log quick walk as atomic operation."""
        await super().async_press()

        try:
            # Start and immediately end walk atomically
            await self._async_service_call(
                "pawcontrol",
                SERVICE_START_WALK,
                data={
                    ATTR_DOG_ID: self._dog_id,
                    "label": "Quick walk",
                },
                blocking=True,
            )

            await self._async_service_call(
                "pawcontrol",
                SERVICE_END_WALK,
                data={
                    ATTR_DOG_ID: self._dog_id,
                    "duration": 10,
                    "distance": 800,
                    "notes": "Quick walk",
                },
                blocking=True,
            )

        except Exception as err:
            _LOGGER.error("Failed to log quick walk: %s", err)
            raise HomeAssistantError(f"Failed to log quick walk: {err}") from err


class PawControlLogWalkManuallyButton(PawControlButtonBase):
    """Button for manual walk logging."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialise the manual walk logging control."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "log_walk_manually",
            icon="mdi:pencil",
            action_description="Manually log a walk",
        )
        self._attr_device_class = ButtonDeviceClass.IDENTIFY

    async def async_press(self) -> None:
        """Log manual walk."""
        await super().async_press()

        try:
            await self._async_service_call(
                "pawcontrol",
                SERVICE_START_WALK,
                {
                    ATTR_DOG_ID: self._dog_id,
                    "label": "Manual entry",
                },
                blocking=True,
            )

            await self._async_service_call(
                "pawcontrol",
                SERVICE_END_WALK,
                {
                    ATTR_DOG_ID: self._dog_id,
                    "duration": 30,
                    "distance": 1500,
                    "notes": "Manually logged walk",
                },
                blocking=True,
            )

        except Exception as err:
            _LOGGER.error("Failed to log manual walk: %s", err)
            raise HomeAssistantError(f"Failed to log walk: {err}") from err


class PawControlRefreshLocationButton(PawControlButtonBase):
    """Button to refresh GPS location."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialise the GPS refresh control."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "refresh_location",
            device_class=ButtonDeviceClass.UPDATE,
            icon="mdi:crosshairs-gps",
            action_description="Request GPS update",
        )

    async def async_press(self) -> None:
        """Refresh location with high priority."""
        await super().async_press()

        try:
            await self.coordinator.async_request_selective_refresh(
                [self._dog_id], priority=9
            )
        except Exception as err:
            _LOGGER.error("Failed to refresh location: %s", err)
            raise HomeAssistantError(f"Failed to refresh location: {err}") from err


class PawControlUpdateLocationButton(PawControlRefreshLocationButton):
    """Alias button for update location functionality used in tests."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialise the update-location alias control for tests."""
        super().__init__(coordinator, dog_id, dog_name)
        self._button_type = "update_location"
        self._attr_unique_id = f"pawcontrol_{dog_id}_update_location"
        self._attr_name = f"{dog_name} Update Location"


class PawControlExportRouteButton(PawControlButtonBase):
    """Button to export route data."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialise the route export control."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "export_route",
            icon="mdi:export",
            action_description="Export walk route as GPX",
        )

    async def async_press(self) -> None:
        """Export route data."""
        await super().async_press()

        try:
            await self._async_service_call(
                "pawcontrol",
                "export_data",
                {
                    ATTR_DOG_ID: self._dog_id,
                    "data_type": "gps",
                    "format": "gpx",
                    "start_date": (dt_util.now() - timedelta(days=1))
                    .date()
                    .isoformat(),
                },
                blocking=False,
            )
        except Exception as err:
            _LOGGER.error("Failed to export route: %s", err)
            raise HomeAssistantError(f"Failed to export route: {err}") from err


class PawControlCenterMapButton(PawControlButtonBase):
    """Button to center map on dog location."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialise the map centring control."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "center_map",
            icon="mdi:map-marker",
            action_description="Center map on dog",
        )

    async def async_press(self) -> None:
        """Center map on dog."""
        await super().async_press()

        gps_data = self._get_gps_payload()
        if not gps_data:
            raise HomeAssistantError("No GPS data available")

        _LOGGER.info("Map centering requested for %s", self._dog_name)


class PawControlCallDogButton(PawControlButtonBase):
    """Button to call GPS tracker."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialise the tracker call control."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "call_dog",
            icon="mdi:volume-high",
            action_description="Activate tracker sound",
        )

    async def async_press(self) -> None:
        """Call GPS tracker."""
        await super().async_press()

        try:
            gps_data = self._get_gps_payload()
            if not gps_data or gps_data.get("source") in ["none", "manual"]:
                raise HomeAssistantError(
                    f"GPS tracker not available for {self._dog_id}"
                )

            # Log call request
            _LOGGER.info("GPS tracker call requested for %s", self._dog_name)

        except Exception as err:
            _LOGGER.error("Failed to call tracker: %s", err)
            raise HomeAssistantError(f"Failed to call tracker: {err}") from err


class PawControlLogWeightButton(PawControlButtonBase):
    """Button to log weight measurement."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialise the quick weight logging control."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "log_weight",
            icon="mdi:scale",
            action_description="Log weight measurement",
        )

    async def async_press(self) -> None:
        """Log weight measurement."""
        await super().async_press()

        try:
            await self._async_service_call(
                "pawcontrol",
                SERVICE_LOG_HEALTH,
                {
                    ATTR_DOG_ID: self._dog_id,
                    "note": "Weight logged via button",
                },
                blocking=False,
            )
        except Exception as err:
            _LOGGER.error("Failed to log weight: %s", err)
            raise HomeAssistantError(f"Failed to log weight: {err}") from err


class PawControlLogMedicationButton(PawControlButtonBase):
    """Button to log medication administration."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialise the medication logging shortcut."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "log_medication",
            icon="mdi:pill",
            action_description="Log medication",
        )

    async def async_press(self) -> None:
        """Log medication administration."""
        await super().async_press()
        _LOGGER.info("Medication logging initiated for %s", self._dog_name)


class PawControlStartGroomingButton(PawControlButtonBase):
    """Button to start grooming session."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialise the grooming session starter."""
        hass_obj = getattr(coordinator, "hass", None)
        language_config = getattr(hass_obj, "config", None) if hass_obj else None
        hass_language: str | None = None
        if language_config is not None:
            hass_language = getattr(language_config, "language", None)
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "start_grooming",
            icon="mdi:content-cut",
            action_description=translated_grooming_label(
                hass_language, "button_action"
            ),
        )

    async def async_press(self) -> None:
        """Start grooming session."""
        await super().async_press()

        config_obj = getattr(self.hass, "config", None)
        hass_language: str | None = None
        if config_obj is not None:
            hass_language = getattr(config_obj, "language", None)

        try:
            await self._async_service_call(
                "pawcontrol",
                SERVICE_START_GROOMING,
                {
                    ATTR_DOG_ID: self._dog_id,
                    "type": "general",
                    "notes": translated_grooming_label(hass_language, "button_notes"),
                },
                blocking=False,
            )
        except Exception as err:
            _LOGGER.error("Failed to start grooming: %s", err)
            error_message = translated_grooming_template(
                hass_language, "button_error", error=str(err)
            )
            raise HomeAssistantError(error_message) from err


class PawControlScheduleVetButton(PawControlButtonBase):
    """Button to schedule veterinary appointment."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialise the vet scheduling shortcut."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "schedule_vet",
            icon="mdi:calendar-plus",
            action_description="Schedule vet appointment",
        )

    async def async_press(self) -> None:
        """Schedule veterinary appointment."""
        await super().async_press()
        _LOGGER.info("Vet scheduling initiated for %s", self._dog_name)


class PawControlHealthCheckButton(PawControlButtonBase):
    """Button for comprehensive health check."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialise the comprehensive health check control."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "health_check",
            device_class=ButtonDeviceClass.UPDATE,
            icon="mdi:heart-pulse",
            action_description="Perform health check",
        )

    async def async_press(self) -> None:
        """Perform comprehensive health check."""
        await super().async_press()

        health_data_raw = self._get_module_data(
            cast(CoordinatorTypedModuleName, MODULE_HEALTH)
        )
        health_data = (
            cast(HealthModulePayload, health_data_raw)
            if health_data_raw is not None
            else None
        )
        if health_data:
            status = health_data.get("health_status", STATE_UNKNOWN)
            alerts = health_data.get("health_alerts", [])
            alert_count = len(alerts) if isinstance(alerts, Sequence) else 0
            _LOGGER.info(
                "Health check for %s: Status=%s, Alerts=%d",
                self._dog_name,
                status,
                alert_count,
            )


class PawControlStartGardenSessionButton(PawControlButtonBase):
    """Button to start a garden session."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialise the garden session start control."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "start_garden_session",
            icon="mdi:flower",
            action_description="Start a garden session",
        )

    async def async_press(self) -> None:
        """Start a new garden session via the service layer."""
        await super().async_press()

        garden_data = self._get_garden_payload()
        if garden_data and garden_data.get("status") == "active":
            raise HomeAssistantError("Garden session is already active")

        try:
            await self._async_service_call(
                "pawcontrol",
                SERVICE_START_GARDEN_SESSION,
                {ATTR_DOG_ID: self._dog_id, "detection_method": "manual"},
                blocking=False,
            )
        except ServiceValidationError as err:
            raise HomeAssistantError(str(err)) from err
        except Exception as err:  # pragma: no cover - defensive logging
            _LOGGER.error("Failed to start garden session: %s", err)
            raise HomeAssistantError(f"Failed to start garden session: {err}") from err

    @property
    def available(self) -> bool:
        """Return True when a garden session can be started."""
        if not super().available:
            return False
        garden_data = self._get_garden_payload()
        return garden_data is None or garden_data.get("status") != "active"


class PawControlEndGardenSessionButton(PawControlButtonBase):
    """Button to end a garden session."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the end-garden-session control."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "end_garden_session",
            icon="mdi:flower-off",
            action_description="End the active garden session",
        )

    async def async_press(self) -> None:
        """Trigger the integration service to end the active session."""
        await super().async_press()

        garden_data = self._get_garden_payload()
        if not garden_data or garden_data.get("status") != "active":
            raise HomeAssistantError("No active garden session to end")

        try:
            await self._async_service_call(
                "pawcontrol",
                SERVICE_END_GARDEN_SESSION,
                {ATTR_DOG_ID: self._dog_id},
                blocking=False,
            )
        except ServiceValidationError as err:
            raise HomeAssistantError(str(err)) from err
        except Exception as err:  # pragma: no cover - defensive logging
            _LOGGER.error("Failed to end garden session: %s", err)
            raise HomeAssistantError(f"Failed to end garden session: {err}") from err

    @property
    def available(self) -> bool:
        """Return True only while a session is active."""
        if not super().available:
            return False
        garden_data = self._get_garden_payload()
        return bool(garden_data and garden_data.get("status") == "active")


class PawControlLogGardenActivityButton(PawControlButtonBase):
    """Button to log a general garden activity."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the generic garden activity logger button."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "log_garden_activity",
            icon="mdi:leaf",
            action_description="Log garden activity",
        )

    async def async_press(self) -> None:
        """Log a generic garden activity via the integration service."""
        await super().async_press()

        garden_data = self._get_garden_payload()
        if not garden_data or garden_data.get("status") != "active":
            raise HomeAssistantError("Start a garden session before logging activity")

        try:
            await self._async_service_call(
                "pawcontrol",
                SERVICE_ADD_GARDEN_ACTIVITY,
                {
                    ATTR_DOG_ID: self._dog_id,
                    "activity_type": "general",
                    "notes": "Logged via garden activity button",
                    "confirmed": True,
                },
                blocking=False,
            )
        except ServiceValidationError as err:
            raise HomeAssistantError(str(err)) from err
        except Exception as err:  # pragma: no cover - defensive logging
            _LOGGER.error("Failed to log garden activity: %s", err)
            raise HomeAssistantError(f"Failed to log garden activity: {err}") from err

    @property
    def available(self) -> bool:
        """Return True while a garden session is running."""
        if not super().available:
            return False
        garden_data = self._get_garden_payload()
        return bool(garden_data and garden_data.get("status") == "active")


class PawControlConfirmGardenPoopButton(PawControlButtonBase):
    """Button to confirm a garden poop event."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the confirmation control for garden poop events."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "confirm_garden_poop",
            icon="mdi:emoticon-poop",
            action_description="Confirm garden poop",
        )

    async def async_press(self) -> None:
        """Mark the most recent garden poop confirmation as complete."""
        await super().async_press()

        try:
            if not await self._async_call_hass_service(
                "pawcontrol",
                SERVICE_CONFIRM_GARDEN_POOP,
                {
                    ATTR_DOG_ID: self._dog_id,
                    "confirmed": True,
                    "quality": "normal",
                    "size": "normal",
                },
                blocking=False,
            ):
                return
        except ServiceValidationError as err:
            raise HomeAssistantError(str(err)) from err
        except Exception as err:  # pragma: no cover - defensive logging
            _LOGGER.error("Failed to confirm garden poop: %s", err)
            raise HomeAssistantError(f"Failed to confirm garden poop: {err}") from err

    @property
    def available(self) -> bool:
        """Return True when pending garden poop confirmations exist."""
        if not super().available:
            return False
        garden_data = self._get_garden_payload()
        pending = garden_data.get("pending_confirmations") if garden_data else None
        return bool(pending)
