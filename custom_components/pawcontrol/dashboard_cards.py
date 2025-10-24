"""Specialized card generators for Paw Control dashboards.

This module provides high-performance, specialized card generators for different
dashboard components. Each generator is optimized for its specific use case
with lazy loading, validation, and async operations.

OPTIMIZED: Enhanced with batch processing, parallel card generation,
advanced caching, and comprehensive type safety for maximum performance.

Quality Scale: Bronze target
Home Assistant: 2025.9.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Final, TypeVar

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.util import slugify

from .const import (
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_VISITOR,
    MODULE_WALK,
)
from .dashboard_shared import (
    CardCollection,
    CardConfig,
    coerce_dog_config,
    coerce_dog_configs,
    unwrap_async_result,
)
from .dashboard_templates import (
    MAP_OPTION_KEYS,
    DashboardTemplates,
    MapCardOptions,
    MapOptionsInput,
)
from .language import normalize_language
from .types import (
    DOG_ID_FIELD,
    DOG_IMAGE_FIELD,
    DOG_MODULES_FIELD,
    DOG_NAME_FIELD,
    CoordinatorStatisticsPayload,
    DogConfigData,
    DogModulesConfig,
    RawDogConfig,
    coerce_dog_modules_config,
)

if TYPE_CHECKING:
    from .dashboard_templates import DashboardTemplates

_LOGGER = logging.getLogger(__name__)
_TEMPLATE_LOGGER = logging.getLogger("custom_components.pawcontrol.dashboard_templates")

# OPTIMIZED: Performance constants for batch processing
MAX_CONCURRENT_VALIDATIONS: Final[int] = 10
ENTITY_VALIDATION_TIMEOUT: Final[float] = 5.0
CARD_GENERATION_TIMEOUT: Final[float] = 15.0
VALIDATION_CACHE_SIZE: Final[int] = 200

# OPTIMIZED: Type definitions for better performance
CardConfigType = CardConfig
EntityListType = list[str]
ModulesConfigType = DogModulesConfig
DogConfigType = DogConfigData
ThemeConfigType = dict[str, str]
OptionsConfigType = dict[str, Any]

# OPTIMIZED: Generic type for card generators
T = TypeVar("T", bound="BaseCardGenerator")

# OPTIMIZED: Entity validation cache for performance
_entity_validation_cache: dict[str, tuple[float, bool]] = {}
_cache_cleanup_threshold = 300  # 5 minutes


_VISITOR_LABEL_TRANSLATIONS: Final[Mapping[str, Mapping[str, str]]] = {
    "entities_title": {
        "en": "Visitor mode controls",
        "de": "Steuerungen für den Besuchermodus",
    },
    "status_heading": {
        "en": "Visitor mode status",
        "de": "Status des Besuchermodus",
    },
    "active": {"en": "Active", "de": "Aktiv"},
    "visitor": {"en": "Visitor", "de": "Besucher"},
    "started": {"en": "Started", "de": "Gestartet"},
    "alerts_reduced": {
        "en": "Alerts reduced",
        "de": "Warnungen reduziert",
    },
}

_VISITOR_TEMPLATE_TRANSLATIONS: Final[Mapping[str, Mapping[str, str]]] = {
    "insights_title": {
        "en": "{dog_name} visitor insights",
        "de": "{dog_name} Besuchereinblicke",
    },
}

_VISITOR_VALUE_TRANSLATIONS: Final[Mapping[str, Mapping[str, str]]] = {
    "yes": {"en": "Yes", "de": "Ja"},
    "no": {"en": "No", "de": "Nein"},
    "none": {"en": "None", "de": "Keine"},
    "unknown": {"en": "Unknown", "de": "Unbekannt"},
}

_QUICK_ACTION_TRANSLATIONS: Final[Mapping[str, Mapping[str, str]]] = {
    "feed_all": {"en": "Feed All", "de": "Alle füttern"},
    "daily_reset": {"en": "Daily Reset", "de": "Täglicher Reset"},
}

_WALK_LABEL_TRANSLATIONS: Final[Mapping[str, Mapping[str, str]]] = {
    "status": {"en": "Walk Status", "de": "Spazierstatus"},
    "start": {"en": "Start Walk", "de": "Spaziergang starten"},
    "end": {"en": "End Walk", "de": "Spaziergang beenden"},
    "next_good_time": {
        "en": "Next Good Walk Time",
        "de": "Nächster guter Spaziergangszeitpunkt",
    },
}

_WALK_TEMPLATE_TRANSLATIONS: Final[Mapping[str, Mapping[str, str]]] = {
    "history_title": {
        "en": "Walk History ({days} days)",
        "de": "Spazierverlauf ({days} Tage)",
    },
    "statistics_title": {
        "en": "Walk Statistics ({days} days)",
        "de": "Spazierstatistiken ({days} Tage)",
    },
}


_HEALTH_LABEL_TRANSLATIONS: Final[Mapping[str, Mapping[str, str]]] = {
    "health_status": {"en": "Health Status", "de": "Gesundheitsstatus"},
    "calorie_target": {"en": "Calorie Target", "de": "Kalorienziel"},
    "calories_today": {"en": "Calories Today", "de": "Kalorien heute"},
    "portion_adjustment": {
        "en": "Portion Adjustment",
        "de": "Portionsanpassung",
    },
    "calorie_tracking_title": {
        "en": "📊 Calorie Tracking",
        "de": "📊 Kalorienverlauf",
    },
    "weight_management_title": {
        "en": "⚖️ Weight Management",
        "de": "⚖️ Gewichtsmanagement",
    },
    "current_weight": {"en": "Current Weight", "de": "Aktuelles Gewicht"},
    "ideal_weight": {"en": "Ideal Weight", "de": "Idealgewicht"},
    "body_condition": {
        "en": "Body Condition (1-9)",
        "de": "Körperkondition (1-9)",
    },
    "weight_goal_progress": {
        "en": "Weight Goal Progress",
        "de": "Fortschritt des Gewichtsziels",
    },
    "recalculate": {"en": "Recalculate", "de": "Neu berechnen"},
    "update_health": {
        "en": "Update Health",
        "de": "Gesundheitsdaten aktualisieren",
    },
    "smart_breakfast": {
        "en": "Smart Breakfast",
        "de": "Smartes Frühstück",
    },
    "smart_dinner": {
        "en": "Smart Dinner",
        "de": "Smartes Abendessen",
    },
    "log_health": {"en": "Log Health", "de": "Gesundheit protokollieren"},
    "log_medication": {
        "en": "Log Medication",
        "de": "Medikation protokollieren",
    },
    "health_metrics_title": {
        "en": "Health Metrics",
        "de": "Gesundheitsmetriken",
    },
    "health_schedule_title": {
        "en": "Health Schedule",
        "de": "Gesundheitsplan",
    },
}

_HEALTH_TEMPLATE_TRANSLATIONS: Final[Mapping[str, Mapping[str, str]]] = {
    "health_feeding_title": {
        "en": "🔬 {dog_name} Health Feeding",
        "de": "🔬 {dog_name} Gesundheitsfütterung",
    },
    "portion_calculator": {
        "en": """## 🧮 Health-Aware Portion Calculator

**Current Recommendations:**
- **Breakfast**: {{{{ states('sensor.{dog_id}_breakfast_portion_size') }}}}g
- **Lunch**: {{{{ states('sensor.{dog_id}_lunch_portion_size') }}}}g
- **Dinner**: {{{{ states('sensor.{dog_id}_dinner_portion_size') }}}}g
- **Daily Total**: {{{{ states('sensor.{dog_id}_daily_food_target') }}}}g

**Health Adjustments:**
- Body Condition Factor: {{{{ states('sensor.{dog_id}_bcs_adjustment_factor') }}}}
- Activity Factor: {{{{ states('sensor.{dog_id}_activity_adjustment_factor') }}}}
- Overall Adjustment: {{{{ states('sensor.{dog_id}_portion_adjustment_factor') }}}}x
""",
        "de": """## 🧮 Gesundheitsbasierter Portionsrechner

**Aktuelle Empfehlungen:**
- **Frühstück**: {{{{ states('sensor.{dog_id}_breakfast_portion_size') }}}}g
- **Mittagessen**: {{{{ states('sensor.{dog_id}_lunch_portion_size') }}}}g
- **Abendessen**: {{{{ states('sensor.{dog_id}_dinner_portion_size') }}}}g
- **Tagesgesamtmenge**: {{{{ states('sensor.{dog_id}_daily_food_target') }}}}g

**Gesundheitsanpassungen:**
- Körperkonditionsfaktor: {{{{ states('sensor.{dog_id}_bcs_adjustment_factor') }}}}
- Aktivitätsfaktor: {{{{ states('sensor.{dog_id}_activity_adjustment_factor') }}}}
- Gesamtanpassung: {{{{ states('sensor.{dog_id}_portion_adjustment_factor') }}}}x
""",
    },
    "weight_history_title": {
        "en": "Weight Tracking ({days} days)",
        "de": "Gewichtsverlauf ({days} Tage)",
    },
}


def _translated_visitor_label(language: str | None, label: str) -> str:
    """Return a localized visitor dashboard label."""

    translations = _VISITOR_LABEL_TRANSLATIONS.get(label)
    if translations is None:
        return label

    normalized_language = normalize_language(language)
    if normalized_language in translations:
        return translations[normalized_language]

    return translations.get("en", label)


def _translated_visitor_template(
    language: str | None, template: str, **values: str
) -> str:
    """Return a formatted visitor dashboard template string."""

    translations = _VISITOR_TEMPLATE_TRANSLATIONS.get(template)
    if translations is None:
        return template.format(**values)

    normalized_language = normalize_language(language)
    template_value = translations.get(normalized_language)
    if template_value is None:
        template_value = translations.get("en", template)

    return template_value.format(**values)


def _translated_visitor_value(language: str | None, value: str) -> str:
    """Return a localized value string for visitor dashboards."""

    translations = _VISITOR_VALUE_TRANSLATIONS.get(value)
    if translations is None:
        return value

    normalized_language = normalize_language(language)
    if normalized_language in translations:
        return translations[normalized_language]

    return translations.get("en", value)


def _translated_quick_action_label(language: str | None, label: str) -> str:
    """Return a localized quick action label."""

    translations = _QUICK_ACTION_TRANSLATIONS.get(label)
    if translations is None:
        return label

    normalized_language = normalize_language(language)
    if normalized_language in translations:
        return translations[normalized_language]

    return translations.get("en", label)


def _translated_walk_label(language: str | None, label: str) -> str:
    """Return a localized label for walk dashboards."""

    translations = _WALK_LABEL_TRANSLATIONS.get(label)
    if translations is None:
        return label

    normalized_language = normalize_language(language)
    if normalized_language in translations:
        return translations[normalized_language]

    return translations.get("en", label)


def _translated_walk_template(
    language: str | None, template: str, **values: object
) -> str:
    """Return a localized walk dashboard template string."""

    translations = _WALK_TEMPLATE_TRANSLATIONS.get(template)
    if translations is None:
        return template.format(**values)

    normalized_language = normalize_language(language)
    template_value = translations.get(normalized_language)
    if template_value is None:
        template_value = translations.get("en", template)

    return template_value.format(**values)


def _translated_health_label(language: str | None, label: str) -> str:
    """Return a localized label for health dashboards."""

    translations = _HEALTH_LABEL_TRANSLATIONS.get(label)
    if translations is None:
        return label

    normalized_language = normalize_language(language)
    if normalized_language in translations:
        return translations[normalized_language]

    return translations.get("en", label)


def _translated_health_template(
    language: str | None, template: str, **values: object
) -> str:
    """Return a localized health dashboard template string."""

    translations = _HEALTH_TEMPLATE_TRANSLATIONS.get(template)
    if translations is None:
        return template.format(**values)

    normalized_language = normalize_language(language)
    template_value = translations.get(normalized_language)
    if template_value is None:
        template_value = translations.get("en", template)

    return template_value.format(**values)


def _coerce_map_options(options: MapOptionsInput) -> MapCardOptions:
    """Extract typed map options from the generic options payload."""

    if not isinstance(options, Mapping):
        return DashboardTemplates._normalise_map_options(options)

    nested_entries: list[tuple[str, object]] = []
    for candidate_key in ("map_options", "map", "map_card"):
        nested = options.get(candidate_key)
        if nested is None:
            continue

        if isinstance(nested, Mapping):
            nested_entries.extend(
                (key, value) for key, value in nested.items() if isinstance(key, str)
            )
            continue

        if isinstance(nested, Iterable) and not isinstance(nested, str | bytes):
            nested_entries.extend(nested)  # validation occurs in the normaliser
            continue

        _TEMPLATE_LOGGER.debug(
            "Ignoring map options alias '%s' with unsupported type: %s",
            candidate_key,
            type(nested).__name__,
        )

    top_level_entries: list[tuple[str, object]] = []
    for key, value in options.items():
        if not isinstance(key, str):
            _TEMPLATE_LOGGER.debug(
                "Skipping map option entry with non-string key from mapping: %r",
                key,
            )
            continue

        if key in {"map_options", "map", "map_card"}:
            continue

        if key not in MAP_OPTION_KEYS:
            _TEMPLATE_LOGGER.debug(
                "Ignoring unsupported map option key '%s' from mapping payload",
                key,
            )
            continue

        top_level_entries.append((key, value))

    if nested_entries:
        return DashboardTemplates._normalise_map_options(
            [*nested_entries, *top_level_entries]
        )

    if top_level_entries:
        return DashboardTemplates._normalise_map_options(top_level_entries)

    return DashboardTemplates._normalise_map_options(options)


class BaseCardGenerator:
    """Base class for card generators with enhanced performance optimization.

    OPTIMIZED: Enhanced with batch processing, async caching, memory management,
    and comprehensive error isolation for maximum performance.
    """

    def __init__(self, hass: HomeAssistant, templates: DashboardTemplates) -> None:
        """Initialize optimized card generator.

        Args:
            hass: Home Assistant instance
            templates: Template manager with caching
        """
        self.hass = hass
        self.templates = templates

        # OPTIMIZED: Performance tracking and validation semaphore
        self._validation_semaphore = asyncio.Semaphore(MAX_CONCURRENT_VALIDATIONS)
        self._performance_stats = {
            "validations_count": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "generation_time_total": 0.0,
            "errors_handled": 0,
        }

    @staticmethod
    def _ensure_dog_config(dog_config: RawDogConfig) -> DogConfigData | None:
        """Return a typed dog configuration extracted from ``dog_config``."""

        return coerce_dog_config(dog_config)

    def _ensure_dog_configs(
        self, dogs_config: Sequence[RawDogConfig]
    ) -> list[DogConfigData]:
        """Return typed dog configurations for downstream processing."""

        return coerce_dog_configs(dogs_config)

    async def _collect_single_card(
        self, card_coro: Awaitable[CardConfigType | None]
    ) -> CardCollection:
        """Resolve ``card_coro`` and wrap the payload in a list for gather usage."""

        card = await card_coro
        return [card] if card is not None else []

    async def _validate_entities_batch(
        self, entities: EntityListType, use_cache: bool = True
    ) -> EntityListType:
        """Validate entities in optimized batches with caching.

        OPTIMIZED: Batch processing with cache, timeout protection, and memory management.

        Args:
            entities: List of entity IDs to validate
            use_cache: Whether to use validation cache

        Returns:
            List of valid entity IDs
        """
        if not entities:
            return []

        start_time = asyncio.get_event_loop().time()
        valid_entities: list[str] = []

        # OPTIMIZED: Clean cache if needed
        await self._cleanup_validation_cache()

        # OPTIMIZED: Separate cached and uncached entities
        cached_results: dict[str, bool] = {}
        uncached_entities: list[str] = []

        if use_cache:
            current_time = asyncio.get_event_loop().time()
            for entity_id in entities:
                cache_entry = _entity_validation_cache.get(entity_id)
                if (
                    cache_entry
                    and (current_time - cache_entry[0]) < _cache_cleanup_threshold
                ):
                    cached_results[entity_id] = cache_entry[1]
                    self._performance_stats["cache_hits"] += 1
                else:
                    uncached_entities.append(entity_id)
                    self._performance_stats["cache_misses"] += 1
        else:
            uncached_entities = entities.copy()

        # OPTIMIZED: Process uncached entities in controlled batches
        batch_size = min(MAX_CONCURRENT_VALIDATIONS, len(uncached_entities))
        for i in range(0, len(uncached_entities), batch_size):
            batch = uncached_entities[i : i + batch_size]

            async with self._validation_semaphore:
                try:
                    # OPTIMIZED: Parallel validation with timeout
                    batch_tasks = [
                        asyncio.create_task(self._validate_single_entity(entity_id))
                        for entity_id in batch
                    ]

                    batch_results = await asyncio.wait_for(
                        asyncio.gather(*batch_tasks, return_exceptions=True),
                        timeout=ENTITY_VALIDATION_TIMEOUT,
                    )

                    # Process batch results
                    for entity_id, result in zip(batch, batch_results, strict=False):
                        validation_result = _unwrap_async_result(
                            result,
                            context=f"Entity validation error for {entity_id}",
                            logger=_LOGGER,
                            level=logging.DEBUG,
                        )
                        cached_results[entity_id] = bool(validation_result)

                        # Update cache
                        if use_cache:
                            _entity_validation_cache[entity_id] = (
                                asyncio.get_event_loop().time(),
                                cached_results[entity_id],
                            )

                except TimeoutError:
                    _LOGGER.warning("Entity validation timeout for batch: %s", batch)
                    for entity_id in batch:
                        cached_results[entity_id] = False

                except Exception as err:
                    _LOGGER.error("Batch validation error: %s", err)
                    for entity_id in batch:
                        cached_results[entity_id] = False
                    self._performance_stats["errors_handled"] += 1

        # OPTIMIZED: Collect all valid entities
        for entity_id in entities:
            if cached_results.get(entity_id, False):
                valid_entities.append(entity_id)  # noqa: PERF401

        # Update performance stats
        validation_time = asyncio.get_event_loop().time() - start_time
        self._performance_stats["validations_count"] += len(entities)
        self._performance_stats["generation_time_total"] += validation_time

        if validation_time > 1.0:  # Log slow validations
            _LOGGER.debug(
                "Slow entity validation: %.2fs for %d entities (%d valid)",
                validation_time,
                len(entities),
                len(valid_entities),
            )

        return valid_entities

    async def _validate_single_entity(self, entity_id: str) -> bool:
        """Validate single entity with optimized state checking.

        Args:
            entity_id: Entity ID to validate

        Returns:
            True if entity is valid and available
        """
        try:
            state = self.hass.states.get(entity_id)
            return state is not None and state.state not in (
                STATE_UNKNOWN,
                STATE_UNAVAILABLE,
            )
        except Exception as err:
            _LOGGER.debug("Entity validation error for %s: %s", entity_id, err)
            return False

    async def _entity_exists_cached(self, entity_id: str) -> bool:
        """Check if entity exists with caching for performance.

        Args:
            entity_id: Entity ID to check

        Returns:
            True if entity exists and is available
        """
        results = await self._validate_entities_batch([entity_id], use_cache=True)
        return len(results) > 0

    async def _cleanup_validation_cache(self) -> None:
        """Cleanup old entries from validation cache."""
        if len(_entity_validation_cache) <= VALIDATION_CACHE_SIZE:
            return

        current_time = asyncio.get_event_loop().time()
        expired_keys = [
            entity_id
            for entity_id, (timestamp, _) in _entity_validation_cache.items()
            if current_time - timestamp > _cache_cleanup_threshold
        ]

        for key in expired_keys:
            _entity_validation_cache.pop(key, None)

        # If still too large, remove oldest entries
        if len(_entity_validation_cache) > VALIDATION_CACHE_SIZE:
            sorted_items = sorted(
                _entity_validation_cache.items(),
                key=lambda x: x[1][0],  # Sort by timestamp
            )
            remove_count = len(_entity_validation_cache) - VALIDATION_CACHE_SIZE
            for entity_id, _ in sorted_items[:remove_count]:
                _entity_validation_cache.pop(entity_id, None)

    @property
    def performance_stats(self) -> dict[str, Any]:
        """Get performance statistics for monitoring."""
        return self._performance_stats.copy()


class OverviewCardGenerator(BaseCardGenerator):
    """Generator for overview dashboard cards with enhanced performance."""

    async def generate_welcome_card(
        self, dogs_config: Sequence[RawDogConfig], options: OptionsConfigType
    ) -> CardConfigType:
        """Generate optimized welcome/summary card.

        Args:
            dogs_config: List of dog configurations
            options: Dashboard options

        Returns:
            Welcome card configuration
        """
        typed_dogs = self._ensure_dog_configs(dogs_config)
        dog_count = len(typed_dogs)
        title = options.get("title", "Paw Control")

        # OPTIMIZED: Async active dog counting with timeout
        try:
            active_dogs = await asyncio.wait_for(
                self._count_active_dogs(typed_dogs), timeout=3.0
            )
        except TimeoutError:
            _LOGGER.debug("Active dog counting timeout, using total count")
            active_dogs = dog_count

        # Generate dynamic content based on current status
        content_parts = [
            f"# {title}",
            f"Managing **{dog_count}** {'dog' if dog_count == 1 else 'dogs'} with Paw Control",
        ]

        # Add quick stats if available
        if active_dogs != dog_count:
            content_parts.append(f"**{active_dogs}** currently active")

        content_parts.extend(
            [
                "",
                "Last updated: {{ now().strftime('%H:%M') }}",
            ]
        )

        return {
            "type": "markdown",
            "content": "\n".join(content_parts),
        }

    async def _count_active_dogs(self, dogs_config: Sequence[DogConfigData]) -> int:
        """Count dogs that are currently active with optimized batch processing.

        Args:
            dogs_config: List of dog configurations

        Returns:
            Number of active dogs
        """
        if not dogs_config:
            return 0

        # OPTIMIZED: Collect all status entities for batch validation
        status_entities = []
        dog_id_mapping = {}

        for dog in dogs_config:
            dog_id = dog[DOG_ID_FIELD]
            if dog_id:
                entity_id = f"sensor.{dog_id}_status"
                status_entities.append(entity_id)
                dog_id_mapping[entity_id] = dog_id

        # OPTIMIZED: Batch validate all status entities
        valid_entities = await self._validate_entities_batch(status_entities)
        return len(valid_entities)

    async def generate_dogs_grid(
        self, dogs_config: Sequence[RawDogConfig], dashboard_url: str
    ) -> CardConfigType | None:
        """Generate optimized grid of dog navigation buttons.

        Args:
            dogs_config: List of dog configurations
            dashboard_url: Base dashboard URL for navigation

        Returns:
            Dog grid card or None if no valid dogs
        """
        typed_dogs = self._ensure_dog_configs(dogs_config)
        if not typed_dogs:
            return None

        # OPTIMIZED: Pre-filter dogs and prepare entities for batch validation
        dog_candidates: list[tuple[str, str, str]] = []  # (dog_id, dog_name, entity_id)

        for dog in typed_dogs:
            dog_id = dog[DOG_ID_FIELD]
            dog_name = dog[DOG_NAME_FIELD]

            if dog_id and dog_name:
                entity_id = f"sensor.{dog_id}_status"
                dog_candidates.append((dog_id, dog_name, entity_id))

        if not dog_candidates:
            return None

        # OPTIMIZED: Batch validate all status entities
        status_entities = [entity_id for _, _, entity_id in dog_candidates]
        valid_entities = await self._validate_entities_batch(status_entities)
        valid_entity_set = set(valid_entities)

        # OPTIMIZED: Build cards only for validated entities
        dog_cards = []
        for dog_id, dog_name, entity_id in dog_candidates:
            if entity_id in valid_entity_set:
                dog_cards.append(
                    {
                        "type": "button",
                        "entity": entity_id,
                        "name": dog_name,
                        "icon": "mdi:dog",
                        "show_state": True,
                        "tap_action": {
                            "action": "navigate",
                            "navigation_path": f"{dashboard_url}/{slugify(dog_id)}",
                        },
                    }
                )

        if not dog_cards:
            return None

        # Optimize grid columns based on number of dogs
        columns = min(3, max(1, len(dog_cards)))

        return {
            "type": "grid",
            "columns": columns,
            "cards": dog_cards,
        }

    async def generate_quick_actions(
        self, dogs_config: Sequence[RawDogConfig]
    ) -> CardConfigType | None:
        """Generate quick action buttons with optimized module detection.

        Args:
            dogs_config: List of dog configurations

        Returns:
            Quick actions card or None if no actions available
        """
        typed_dogs = self._ensure_dog_configs(dogs_config)
        if not typed_dogs:
            return None

        language: str | None = getattr(self.hass.config, "language", None)

        # OPTIMIZED: Single-pass module detection
        has_feeding = False
        has_walking = False

        for dog in typed_dogs:
            modules = coerce_dog_modules_config(dog.get(DOG_MODULES_FIELD))
            if not has_feeding and modules.get(MODULE_FEEDING):
                has_feeding = True
            if not has_walking and modules.get(MODULE_WALK):
                has_walking = True
            # Early exit if both found
            if has_feeding and has_walking:
                break

        # OPTIMIZED: Batch validate action entities
        validation_entities = []
        if has_feeding:
            validation_entities.append(f"button.{DOMAIN}_feed_all_dogs")
        if has_walking:
            validation_entities.append(f"sensor.{DOMAIN}_dogs_walking")

        valid_entities = await self._validate_entities_batch(validation_entities)
        valid_entity_set = set(valid_entities)

        actions = []

        # Build action buttons based on validated entities
        if has_feeding and f"button.{DOMAIN}_feed_all_dogs" in valid_entity_set:
            actions.append(
                {
                    "type": "button",
                    "name": _translated_quick_action_label(language, "feed_all"),
                    "icon": "mdi:food-drumstick",
                    "tap_action": {
                        "action": "more-info",
                        "entity": f"button.{DOMAIN}_feed_all_dogs",
                    },
                }
            )

        if has_walking and f"sensor.{DOMAIN}_dogs_walking" in valid_entity_set:
            actions.append(
                {
                    "type": "button",
                    "name": _translated_walk_label(language, "status"),
                    "icon": "mdi:walk",
                    "tap_action": {
                        "action": "more-info",
                        "entity": f"sensor.{DOMAIN}_dogs_walking",
                    },
                }
            )

        # Daily reset button (always available)
        actions.append(
            {
                "type": "button",
                "name": _translated_quick_action_label(language, "daily_reset"),
                "icon": "mdi:refresh",
                "tap_action": {
                    "action": "call-service",
                    "service": f"{DOMAIN}.daily_reset",
                },
            }
        )

        return (
            {
                "type": "horizontal-stack",
                "cards": actions,
            }
            if actions
            else None
        )


class DogCardGenerator(BaseCardGenerator):
    """Generator for individual dog dashboard cards with performance optimization."""

    async def generate_dog_overview_cards(
        self,
        dog_config: RawDogConfig,
        theme: ThemeConfigType,
        options: OptionsConfigType,
    ) -> list[CardConfigType]:
        """Generate optimized overview cards for a specific dog.

        Args:
            dog_config: Dog configuration
            theme: Theme colors
            options: Display options

        Returns:
            List of overview cards
        """
        typed_dog = self._ensure_dog_config(dog_config)
        if typed_dog is None:
            return []

        dog_config = typed_dog
        dog_id = dog_config[DOG_ID_FIELD]
        dog_name = dog_config[DOG_NAME_FIELD]
        modules = coerce_dog_modules_config(dog_config.get(DOG_MODULES_FIELD))

        start_time = asyncio.get_event_loop().time()
        cards: list[CardConfigType] = []

        # OPTIMIZED: Generate cards in parallel for better performance
        card_tasks: list[tuple[str, asyncio.Task[CardCollection]]] = []

        # Dog header card
        card_tasks.append(
            (
                "header",
                asyncio.create_task(
                    self._collect_single_card(
                        self._generate_dog_header_card(dog_config, options)
                    )
                ),
            )
        )

        # Status card
        card_tasks.append(
            (
                "status",
                asyncio.create_task(
                    self._collect_single_card(
                        self.templates.get_dog_status_card_template(
                            dog_id, dog_name, modules
                        )
                    )
                ),
            )
        )

        # Action buttons
        card_tasks.append(
            (
                "actions",
                asyncio.create_task(self._collect_action_buttons(dog_id, modules)),
            )
        )

        # Conditional cards
        if modules.get(MODULE_GPS):
            card_tasks.append(
                (
                    "gps_map",
                    asyncio.create_task(
                        self._collect_single_card(
                            self._generate_gps_map_card(dog_id, options)
                        )
                    ),
                )
            )

        if options.get("show_activity_graph", True):
            card_tasks.append(
                (
                    "activity",
                    asyncio.create_task(
                        self._collect_single_card(
                            self._generate_activity_graph_card(dog_config, options)
                        )
                    ),
                )
            )

        # OPTIMIZED: Execute card generation concurrently with timeout
        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    *(task for _, task in card_tasks), return_exceptions=True
                ),
                timeout=CARD_GENERATION_TIMEOUT,
            )

            # Process results in order
            for (card_type, _), result in zip(card_tasks, results, strict=False):
                card_payloads = _unwrap_async_result(
                    result,
                    context=f"Card generation failed for {card_type}",
                    logger=_LOGGER,
                )
                if card_payloads is None:
                    self._performance_stats["errors_handled"] += 1
                    continue
                cards.extend(card_payloads)

        except TimeoutError:
            for _, task in card_tasks:
                task.cancel()
            _LOGGER.error("Dog overview card generation timeout for %s", dog_name)
            self._performance_stats["errors_handled"] += 1
            # Return minimal cards on timeout
            return [
                {
                    "type": "markdown",
                    "content": f"## {dog_name}\n\nTimeout generating dashboard cards. Please refresh.",
                }
            ]

        generation_time = asyncio.get_event_loop().time() - start_time
        self._performance_stats["generation_time_total"] += generation_time

        if generation_time > 2.0:
            _LOGGER.info(
                "Slow dog card generation: %.2fs for %s", generation_time, dog_name
            )

        return cards

    async def _collect_action_buttons(
        self, dog_id: str, modules: ModulesConfigType
    ) -> CardCollection:
        """Return rendered action buttons for gather pipelines."""

        buttons = await self.templates.get_action_buttons_template(dog_id, modules)
        return self._build_action_button_cards(buttons)

    def _build_action_button_cards(
        self, action_buttons: list[CardConfigType] | None
    ) -> list[CardConfigType]:
        """Build optimized action button cards with better layout handling."""
        if not action_buttons:
            return []

        # OPTIMIZED: More efficient categorization
        regular_buttons = []
        conditional_buttons = []

        for button in action_buttons:
            if button.get("type") == "conditional":
                conditional_buttons.append(button)
            else:
                regular_buttons.append(button)

        cards: list[CardConfigType] = []

        if regular_buttons:
            cards.append(
                {
                    "type": "horizontal-stack",
                    "cards": regular_buttons,
                }
            )

        cards.extend(conditional_buttons)
        return cards

    async def _generate_dog_header_card(
        self, dog_config: RawDogConfig, options: OptionsConfigType
    ) -> CardConfigType | None:
        """Generate optimized dog header card with picture.

        Args:
            dog_config: Dog configuration
            options: Display options

        Returns:
            Header card or None if not applicable
        """
        typed_dog = self._ensure_dog_config(dog_config)
        if typed_dog is None:
            return None

        dog_id = typed_dog[DOG_ID_FIELD]
        dog_name = typed_dog[DOG_NAME_FIELD]

        # OPTIMIZED: Quick entity existence check with cache
        status_entity = f"sensor.{dog_id}_status"
        if not await self._entity_exists_cached(status_entity):
            return None

        # Use custom image if provided, otherwise default
        dog_image = typed_dog.get(DOG_IMAGE_FIELD, f"/local/paw_control/{dog_id}.jpg")

        return {
            "type": "picture-entity",
            "entity": status_entity,
            "name": dog_name,
            "image": dog_image,
            "show_state": True,
            "show_name": True,
            "aspect_ratio": "16:9",
        }

    async def _generate_gps_map_card(
        self, dog_id: str, options: OptionsConfigType
    ) -> CardConfigType | None:
        """Generate optimized GPS map card for dog.

        Args:
            dog_id: Dog identifier
            options: Display options

        Returns:
            Map card or None if GPS not available
        """
        tracker_entity = f"device_tracker.{dog_id}_location"

        # OPTIMIZED: Use cached entity validation
        if not await self._entity_exists_cached(tracker_entity):
            return None

        map_options = _coerce_map_options(options)
        return await self.templates.get_map_card_template(dog_id, map_options)

    async def _generate_activity_graph_card(
        self, dog_config: RawDogConfig, options: OptionsConfigType
    ) -> CardConfigType | None:
        """Generate optimized activity graph card.

        Args:
            dog_config: Dog configuration
            options: Display options

        Returns:
            Activity graph card or None if no data
        """
        if not options.get("show_activity_graph", True):
            return None

        typed_dog = self._ensure_dog_config(dog_config)
        if typed_dog is None:
            return None

        dog_config = typed_dog
        dog_id = dog_config[DOG_ID_FIELD]
        modules = coerce_dog_modules_config(dog_config.get(DOG_MODULES_FIELD))

        # OPTIMIZED: Build entity list efficiently
        activity_entities = [f"sensor.{dog_id}_activity_level"]

        if modules.get(MODULE_WALK):
            activity_entities.append(f"binary_sensor.{dog_id}_is_walking")

        # OPTIMIZED: Batch validate activity entities
        valid_entities = await self._validate_entities_batch(activity_entities)

        if not valid_entities:
            return None

        return await self.templates.get_history_graph_template(
            valid_entities, "24h Activity", 24
        )


class HealthAwareFeedingCardGenerator(BaseCardGenerator):
    """Generator for health-integrated feeding dashboard cards with optimization."""

    async def generate_health_feeding_overview(
        self, dog_config: RawDogConfig, options: OptionsConfigType
    ) -> list[CardConfigType]:
        """Generate optimized comprehensive health-aware feeding overview cards.

        Args:
            dog_config: Dog configuration including health data
            options: Display options

        Returns:
            List of health feeding overview cards
        """
        typed_dog = self._ensure_dog_config(dog_config)
        if typed_dog is None:
            return []

        dog_config = typed_dog
        dog_id = dog_config[DOG_ID_FIELD]
        dog_name = dog_config[DOG_NAME_FIELD]
        language: str | None = getattr(self.hass.config, "language", None)

        # OPTIMIZED: Generate all cards concurrently
        card_generators: list[tuple[str, asyncio.Task[CardCollection]]] = [
            (
                "health_status",
                asyncio.create_task(
                    self._collect_single_card(
                        self._generate_health_feeding_status_card(
                            dog_id, dog_name, options, language
                        )
                    )
                ),
            ),
            (
                "calorie",
                asyncio.create_task(
                    self._collect_single_card(
                        self._generate_calorie_tracking_card(dog_id, options, language)
                    )
                ),
            ),
            (
                "weight",
                asyncio.create_task(
                    self._collect_single_card(
                        self._generate_weight_management_card(dog_id, options, language)
                    )
                ),
            ),
            (
                "portion",
                asyncio.create_task(
                    self._collect_single_card(
                        self._generate_portion_calculator_card(
                            dog_id, options, language
                        )
                    )
                ),
            ),
        ]

        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    *(task for _, task in card_generators), return_exceptions=True
                ),
                timeout=CARD_GENERATION_TIMEOUT,
            )

            cards: list[CardConfigType] = []
            for (card_type, _), result in zip(card_generators, results, strict=False):
                card_payload = _unwrap_async_result(
                    result,
                    context=f"Health feeding card {card_type} generation failed",
                    logger=_LOGGER,
                )
                if card_payload is None:
                    self._performance_stats["errors_handled"] += 1
                    continue
                cards.extend(card_payload)

            return cards

        except TimeoutError:
            for _, task in card_generators:
                task.cancel()
            _LOGGER.error("Health feeding overview generation timeout for %s", dog_name)
            self._performance_stats["errors_handled"] += 1
            return []

    async def _generate_health_feeding_status_card(
        self,
        dog_id: str,
        dog_name: str,
        options: OptionsConfigType,
        language: str | None,
    ) -> CardConfigType | None:
        """Generate optimized health-integrated feeding status card."""
        # OPTIMIZED: Quick cache-based entity check
        health_status_entity = f"sensor.{dog_id}_health_feeding_status"
        if not await self._entity_exists_cached(health_status_entity):
            return None

        return {
            "type": "entities",
            "title": _translated_health_template(
                language, "health_feeding_title", dog_name=dog_name
            ),
            "entities": [
                {
                    "entity": f"sensor.{dog_id}_health_feeding_status",
                    "name": _translated_health_label(language, "health_status"),
                    "icon": "mdi:heart-pulse",
                },
                {
                    "entity": f"sensor.{dog_id}_daily_calorie_target",
                    "name": _translated_health_label(language, "calorie_target"),
                    "icon": "mdi:fire",
                },
                {
                    "entity": f"sensor.{dog_id}_calories_consumed_today",
                    "name": _translated_health_label(language, "calories_today"),
                    "icon": "mdi:counter",
                },
                {
                    "entity": f"sensor.{dog_id}_portion_adjustment_factor",
                    "name": _translated_health_label(language, "portion_adjustment"),
                    "icon": "mdi:scale-balance",
                },
            ],
            "state_color": True,
            "show_header_toggle": False,
        }

    async def _generate_calorie_tracking_card(
        self, dog_id: str, options: OptionsConfigType, language: str | None
    ) -> CardConfigType | None:
        """Generate optimized calorie tracking and progress card."""
        calorie_entities = [
            f"sensor.{dog_id}_calories_consumed_today",
            f"sensor.{dog_id}_daily_calorie_target",
            f"sensor.{dog_id}_calorie_goal_progress",
        ]

        # OPTIMIZED: Batch validate calorie entities
        valid_entities = await self._validate_entities_batch(calorie_entities)
        if not valid_entities:
            return None

        return {
            "type": "history-graph",
            "title": _translated_health_label(language, "calorie_tracking_title"),
            "entities": [
                f"sensor.{dog_id}_calories_consumed_today",
                f"sensor.{dog_id}_daily_calorie_target",
            ],
            "hours_to_show": 24,
            "refresh_interval": 0,
        }

    async def _generate_weight_management_card(
        self, dog_id: str, options: OptionsConfigType, language: str | None
    ) -> CardConfigType | None:
        """Generate optimized weight management and body condition tracking card."""
        weight_entities = [
            f"sensor.{dog_id}_current_weight",
            f"sensor.{dog_id}_ideal_weight",
            f"sensor.{dog_id}_body_condition_score",
            f"sensor.{dog_id}_weight_goal_progress",
        ]

        # OPTIMIZED: Batch validate weight entities
        valid_entities = await self._validate_entities_batch(weight_entities)
        if not valid_entities:
            return None

        return {
            "type": "vertical-stack",
            "cards": [
                {
                    "type": "entities",
                    "title": _translated_health_label(
                        language, "weight_management_title"
                    ),
                    "entities": [
                        {
                            "entity": f"sensor.{dog_id}_current_weight",
                            "name": _translated_health_label(
                                language, "current_weight"
                            ),
                            "icon": "mdi:weight-kilogram",
                        },
                        {
                            "entity": f"sensor.{dog_id}_ideal_weight",
                            "name": _translated_health_label(language, "ideal_weight"),
                            "icon": "mdi:target",
                        },
                        {
                            "entity": f"sensor.{dog_id}_body_condition_score",
                            "name": _translated_health_label(
                                language, "body_condition"
                            ),
                            "icon": "mdi:dog-side",
                        },
                    ],
                    "state_color": True,
                },
                {
                    "type": "gauge",
                    "entity": f"sensor.{dog_id}_weight_goal_progress",
                    "name": _translated_health_label(language, "weight_goal_progress"),
                    "min": 0,
                    "max": 100,
                    "unit": "%",
                    "severity": {"green": 80, "yellow": 50, "red": 0},
                },
            ],
        }

    async def _generate_portion_calculator_card(
        self, dog_id: str, options: OptionsConfigType, language: str | None
    ) -> CardConfigType | None:
        """Generate optimized interactive health-aware portion calculator card."""
        portions_entity = f"sensor.{dog_id}_health_aware_portions"
        if not await self._entity_exists_cached(portions_entity):
            return None

        return {
            "type": "vertical-stack",
            "cards": [
                {
                    "type": "markdown",
                    "content": _translated_health_template(
                        language, "portion_calculator", dog_id=dog_id
                    ),
                },
                {
                    "type": "horizontal-stack",
                    "cards": [
                        {
                            "type": "button",
                            "name": _translated_health_label(language, "recalculate"),
                            "icon": "mdi:calculator-variant",
                            "tap_action": {
                                "action": "call-service",
                                "service": f"{DOMAIN}.recalculate_portions",
                                "service_data": {"dog_id": dog_id},
                            },
                        },
                        {
                            "type": "button",
                            "name": _translated_health_label(language, "update_health"),
                            "icon": "mdi:heart-pulse",
                            "tap_action": {
                                "action": "call-service",
                                "service": f"{DOMAIN}.update_health_data",
                                "service_data": {"dog_id": dog_id},
                            },
                        },
                    ],
                },
            ],
        }

    async def generate_health_feeding_controls(
        self, dog_config: RawDogConfig, options: OptionsConfigType
    ) -> list[CardConfigType]:
        """Generate optimized health-aware feeding control cards."""
        typed_dog = self._ensure_dog_config(dog_config)
        if typed_dog is None:
            return []

        dog_config = typed_dog
        dog_id = dog_config[DOG_ID_FIELD]
        language: str | None = getattr(self.hass.config, "language", None)

        # OPTIMIZED: Direct card generation without unnecessary async calls
        smart_buttons_card = self._generate_smart_feeding_buttons(
            dog_id, options, language
        )
        return [smart_buttons_card] if smart_buttons_card else []

    def _generate_smart_feeding_buttons(
        self, dog_id: str, options: OptionsConfigType, language: str | None
    ) -> CardConfigType:
        """Generate optimized smart feeding buttons with health-calculated portions."""
        return {
            "type": "grid",
            "columns": 2,
            "cards": [
                {
                    "type": "button",
                    "name": _translated_health_label(language, "smart_breakfast"),
                    "icon": "mdi:weather-sunny",
                    "tap_action": {
                        "action": "call-service",
                        "service": f"{DOMAIN}.feed_health_aware",
                        "service_data": {
                            "dog_id": dog_id,
                            "meal_type": "breakfast",
                            "use_health_calculation": True,
                        },
                    },
                },
                {
                    "type": "button",
                    "name": _translated_health_label(language, "smart_dinner"),
                    "icon": "mdi:weather-night",
                    "tap_action": {
                        "action": "call-service",
                        "service": f"{DOMAIN}.feed_health_aware",
                        "service_data": {
                            "dog_id": dog_id,
                            "meal_type": "dinner",
                            "use_health_calculation": True,
                        },
                    },
                },
            ],
        }


class ModuleCardGenerator(BaseCardGenerator):
    """Generator for module-specific dashboard cards with performance optimization."""

    async def generate_feeding_cards(
        self, dog_config: RawDogConfig, options: OptionsConfigType
    ) -> list[CardConfigType]:
        """Generate optimized feeding module cards with health-aware integration.

        Args:
            dog_config: Dog configuration
            options: Display options

        Returns:
            List of feeding cards
        """
        typed_dog = self._ensure_dog_config(dog_config)
        if typed_dog is None:
            return []

        dog_config = typed_dog
        dog_id = dog_config[DOG_ID_FIELD]
        modules = coerce_dog_modules_config(dog_config.get(DOG_MODULES_FIELD))
        cards: list[CardConfigType] = []

        # OPTIMIZED: Check if health-aware feeding is enabled
        if modules.get(MODULE_HEALTH) and modules.get(MODULE_FEEDING):
            # Use health-aware feeding card generator
            health_generator = HealthAwareFeedingCardGenerator(
                self.hass, self.templates
            )

            # OPTIMIZED: Generate health cards concurrently
            health_overview_task = asyncio.create_task(
                health_generator.generate_health_feeding_overview(dog_config, options)
            )
            health_controls_task = asyncio.create_task(
                health_generator.generate_health_feeding_controls(dog_config, options)
            )

            try:
                overview_result, controls_result = await asyncio.gather(
                    health_overview_task,
                    health_controls_task,
                    return_exceptions=True,
                )

                health_overview_cards = _unwrap_async_result(
                    overview_result,
                    context="Health overview generation failed",
                    logger=_LOGGER,
                )
                if health_overview_cards is None:
                    self._performance_stats["errors_handled"] += 1
                else:
                    cards.extend(health_overview_cards)

                health_control_cards = _unwrap_async_result(
                    controls_result,
                    context="Health controls generation failed",
                    logger=_LOGGER,
                )
                if health_control_cards is None:
                    self._performance_stats["errors_handled"] += 1
                else:
                    cards.extend(health_control_cards)

            except Exception as err:
                _LOGGER.error("Health-aware feeding generation error: %s", err)
                # Fallback to standard feeding cards
                cards.extend(await self._generate_standard_feeding_cards(dog_id))
        else:
            # Standard feeding cards
            cards.extend(await self._generate_standard_feeding_cards(dog_id))

        # OPTIMIZED: Add feeding history graph (concurrent with other operations)
        try:
            history_card = await self._generate_feeding_history_card(dog_id)
            if history_card:
                cards.append(history_card)
        except Exception as err:
            _LOGGER.warning("Feeding history card generation failed: %s", err)

        return cards

    async def _generate_standard_feeding_cards(
        self, dog_id: str
    ) -> list[CardConfigType]:
        """Generate standard feeding cards with batch validation."""
        schedule_entities = [
            f"sensor.{dog_id}_next_meal_time",
            f"sensor.{dog_id}_meals_today",
            f"sensor.{dog_id}_calories_today",
            f"sensor.{dog_id}_last_fed",
        ]

        # OPTIMIZED: Batch validate schedule entities
        valid_entities = await self._validate_entities_batch(schedule_entities)
        cards = []

        if valid_entities:
            cards.append(
                {
                    "type": "entities",
                    "title": "Feeding Schedule",
                    "entities": valid_entities,
                    "state_color": True,
                }
            )

        # OPTIMIZED: Get feeding controls template asynchronously
        try:
            feeding_controls = await self.templates.get_feeding_controls_template(
                dog_id
            )
            cards.append(feeding_controls)
        except Exception as err:
            _LOGGER.debug("Feeding controls template error: %s", err)

        return cards

    async def _generate_feeding_history_card(
        self, dog_id: str
    ) -> CardConfigType | None:
        """Generate optimized feeding history card."""
        history_entities = [
            f"sensor.{dog_id}_meals_today",
            f"sensor.{dog_id}_calories_today",
        ]

        # OPTIMIZED: Get history graph template with entity validation
        history_card = await self.templates.get_history_graph_template(
            history_entities, "Feeding History (7 days)", 168
        )

        return history_card if history_card.get("entities") else None

    async def generate_walk_cards(
        self, dog_config: RawDogConfig, options: OptionsConfigType
    ) -> list[CardConfigType]:
        """Generate optimized walk module cards.

        Args:
            dog_config: Dog configuration
            options: Display options

        Returns:
            List of walk cards
        """
        typed_dog = self._ensure_dog_config(dog_config)
        if typed_dog is None:
            return []

        dog_config = typed_dog
        dog_id = dog_config[DOG_ID_FIELD]
        language: str | None = getattr(self.hass.config, "language", None)
        cards: list[CardConfigType] = []

        # OPTIMIZED: Prepare all walk-related entities for batch validation
        status_entities = [
            f"binary_sensor.{dog_id}_is_walking",
            f"sensor.{dog_id}_current_walk_duration",
            f"sensor.{dog_id}_walks_today",
            f"sensor.{dog_id}_walk_distance_today",
            f"sensor.{dog_id}_last_walk_time",
            f"sensor.{dog_id}_last_walk_distance",
        ]

        # OPTIMIZED: Batch validate all entities at once
        valid_entities = await self._validate_entities_batch(status_entities)

        if valid_entities:
            cards.append(
                {
                    "type": "entities",
                    "title": _translated_walk_label(language, "status"),
                    "entities": valid_entities,
                    "state_color": True,
                }
            )

        # OPTIMIZED: Generate walk control buttons if walking sensor exists
        walking_sensor = f"binary_sensor.{dog_id}_is_walking"
        if walking_sensor in valid_entities:
            walk_controls = self._generate_walk_control_buttons(dog_id, language)
            cards.extend(walk_controls)

        # OPTIMIZED: Generate walk history concurrently
        try:
            history_card = await self._generate_walk_history_card(dog_id, language)
            if history_card:
                cards.append(history_card)
        except Exception as err:
            _LOGGER.debug("Walk history generation failed: %s", err)

        return cards

    def _generate_walk_control_buttons(
        self, dog_id: str, language: str | None
    ) -> list[CardConfigType]:
        """Generate optimized walk control buttons."""
        return [
            {
                "type": "conditional",
                "conditions": [
                    {
                        "entity": f"binary_sensor.{dog_id}_is_walking",
                        "state": "off",
                    }
                ],
                "card": {
                    "type": "button",
                    "name": _translated_walk_label(language, "start"),
                    "icon": "mdi:walk",
                    "icon_height": "60px",
                    "tap_action": {
                        "action": "call-service",
                        "service": f"{DOMAIN}.start_walk",
                        "service_data": {"dog_id": dog_id},
                    },
                },
            },
            {
                "type": "conditional",
                "conditions": [
                    {
                        "entity": f"binary_sensor.{dog_id}_is_walking",
                        "state": "on",
                    }
                ],
                "card": {
                    "type": "button",
                    "name": _translated_walk_label(language, "end"),
                    "icon": "mdi:stop",
                    "icon_height": "60px",
                    "tap_action": {
                        "action": "call-service",
                        "service": f"{DOMAIN}.end_walk",
                        "service_data": {"dog_id": dog_id},
                    },
                },
            },
        ]

    async def _generate_walk_history_card(
        self, dog_id: str, language: str | None
    ) -> CardConfigType | None:
        """Generate optimized walk history card."""
        history_entities = [
            f"sensor.{dog_id}_walks_today",
            f"sensor.{dog_id}_walk_distance_today",
            f"sensor.{dog_id}_last_walk_distance",
        ]

        history_card = await self.templates.get_history_graph_template(
            history_entities,
            _translated_walk_template(language, "history_title", days=7),
            168,
        )

        return history_card if history_card.get("entities") else None

    async def generate_health_cards(
        self, dog_config: RawDogConfig, options: OptionsConfigType
    ) -> list[CardConfigType]:
        """Generate optimized health module cards.

        Args:
            dog_config: Dog configuration
            options: Display options

        Returns:
            List of health cards
        """
        typed_dog = self._ensure_dog_config(dog_config)
        if typed_dog is None:
            return []

        dog_config = typed_dog
        dog_id = dog_config[DOG_ID_FIELD]
        language: str | None = getattr(self.hass.config, "language", None)
        cards: list[CardConfigType] = []

        # OPTIMIZED: Prepare all health entities for batch validation
        metrics_entities = [
            f"sensor.{dog_id}_health_status",
            f"sensor.{dog_id}_weight",
            f"sensor.{dog_id}_temperature",
            f"sensor.{dog_id}_mood",
            f"sensor.{dog_id}_energy_level",
        ]

        date_entities = [
            f"date.{dog_id}_next_vet_visit",
            f"date.{dog_id}_next_vaccination",
            f"date.{dog_id}_next_grooming",
        ]

        # OPTIMIZED: Batch validate all entities concurrently
        metrics_task = self._validate_entities_batch(metrics_entities)
        dates_task = self._validate_entities_batch(date_entities)
        weight_entity_task = self._entity_exists_cached(f"sensor.{dog_id}_weight")

        metrics_result, dates_result, weight_result = await asyncio.gather(
            metrics_task, dates_task, weight_entity_task, return_exceptions=True
        )

        valid_metrics: EntityListType = (
            _unwrap_async_result(
                metrics_result,
                context="Health metrics validation failed",
                logger=_LOGGER,
                level=logging.DEBUG,
            )
            or []
        )

        valid_dates: EntityListType = (
            _unwrap_async_result(
                dates_result,
                context="Health schedule validation failed",
                logger=_LOGGER,
                level=logging.DEBUG,
            )
            or []
        )

        weight_check = _unwrap_async_result(
            weight_result,
            context="Weight entity validation failed",
            logger=_LOGGER,
            level=logging.DEBUG,
        )
        weight_exists = bool(weight_check)

        # Process results with error handling
        if valid_metrics:
            cards.append(
                {
                    "type": "entities",
                    "title": _translated_health_label(language, "health_metrics_title"),
                    "entities": valid_metrics,
                    "state_color": True,
                }
            )

        # Health management buttons (always add these)
        health_buttons = self._generate_health_management_buttons(dog_id, language)
        cards.append(health_buttons)

        # Weight tracking graph
        if weight_exists:
            try:
                weight_card = await self.templates.get_history_graph_template(
                    [f"sensor.{dog_id}_weight"],
                    _translated_health_template(
                        language, "weight_history_title", days=30
                    ),
                    720,
                )
                cards.append(weight_card)
            except Exception as err:
                _LOGGER.debug("Weight tracking card generation failed: %s", err)

        # Health schedule dates
        if valid_dates:
            cards.append(
                {
                    "type": "entities",
                    "title": _translated_health_label(
                        language, "health_schedule_title"
                    ),
                    "entities": valid_dates,
                }
            )

        return cards

    async def generate_notification_cards(
        self, dog_config: RawDogConfig, options: OptionsConfigType
    ) -> list[CardConfigType]:
        """Generate notification module cards using typed templates."""

        typed_dog = self._ensure_dog_config(dog_config)
        if typed_dog is None:
            return []

        dog_config = typed_dog
        dog_id = dog_config[DOG_ID_FIELD]
        dog_name = dog_config[DOG_NAME_FIELD]
        modules = coerce_dog_modules_config(dog_config.get(DOG_MODULES_FIELD))

        if not modules.get(MODULE_NOTIFICATIONS):
            return []

        theme_option = options.get("theme") if isinstance(options, dict) else None
        theme = (
            theme_option if isinstance(theme_option, str) and theme_option else "modern"
        )

        status_entities = [
            f"switch.{dog_id}_notifications_enabled",
            f"select.{dog_id}_notification_priority",
            f"binary_sensor.{dog_id}_notifications_quiet_hours_active",
        ]

        valid_entities = await self._validate_entities_batch(status_entities)

        cards: list[CardConfigType] = []

        settings_card = await self.templates.get_notification_settings_card_template(
            dog_id, dog_name, valid_entities, theme=theme
        )
        if settings_card is not None:
            cards.append(settings_card)

        overview_card = await self.templates.get_notifications_overview_card_template(
            dog_id, dog_name, theme=theme
        )
        cards.append(overview_card)

        actions_card = await self.templates.get_notifications_actions_card_template(
            dog_id, theme=theme
        )
        cards.append(actions_card)

        return cards

    async def generate_visitor_cards(
        self, dog_config: RawDogConfig, options: OptionsConfigType
    ) -> list[CardConfigType]:
        """Generate visitor module cards highlighting guest mode controls."""

        typed_dog = self._ensure_dog_config(dog_config)
        if typed_dog is None:
            return []

        dog_config = typed_dog
        dog_id = dog_config[DOG_ID_FIELD]
        dog_name = dog_config[DOG_NAME_FIELD]
        modules = coerce_dog_modules_config(dog_config.get(DOG_MODULES_FIELD))

        if not modules.get(MODULE_VISITOR):
            return []

        hass_language: str | None = getattr(self.hass.config, "language", None)
        status_entities = [
            f"switch.{dog_id}_visitor_mode",
            f"binary_sensor.{dog_id}_visitor_mode",
        ]

        valid_entities = await self._validate_entities_batch(status_entities)
        cards: list[CardConfigType] = []

        if valid_entities:
            cards.append(
                {
                    "type": "entities",
                    "title": _translated_visitor_label(hass_language, "entities_title"),
                    "entities": valid_entities,
                    "state_color": True,
                }
            )

        yes_value = _translated_visitor_value(hass_language, "yes")
        no_value = _translated_visitor_value(hass_language, "no")
        none_value = _translated_visitor_value(hass_language, "none")
        unknown_value = _translated_visitor_value(hass_language, "unknown")

        yes_literal = json.dumps(yes_value)
        no_literal = json.dumps(no_value)
        none_literal = json.dumps(none_value)
        unknown_literal = json.dumps(unknown_value)

        summary_content = (
            "### {status_heading}\n"
            "- {active_label}: {{{{ iif(is_state('binary_sensor.{dog_id}_visitor_mode', 'on'), {yes_value}, {no_value}) }}}}\n"
            "- {visitor_label}: {{{{ state_attr('binary_sensor.{dog_id}_visitor_mode', 'visitor_name') or {none_value} }}}}\n"
            "- {started_label}: {{{{ state_attr('binary_sensor.{dog_id}_visitor_mode', 'visitor_mode_started') or {unknown_value} }}}}\n"
            "- {alerts_reduced_label}: {{{{ iif(state_attr('binary_sensor.{dog_id}_visitor_mode', 'reduced_alerts'), {yes_value}, {no_value}) }}}}\n"
        ).format(
            status_heading=_translated_visitor_label(hass_language, "status_heading"),
            active_label=_translated_visitor_label(hass_language, "active"),
            yes_value=yes_literal,
            no_value=no_literal,
            visitor_label=_translated_visitor_label(hass_language, "visitor"),
            none_value=none_literal,
            started_label=_translated_visitor_label(hass_language, "started"),
            unknown_value=unknown_literal,
            alerts_reduced_label=_translated_visitor_label(
                hass_language, "alerts_reduced"
            ),
            dog_id=dog_id,
        )

        cards.append(
            {
                "type": "markdown",
                "title": _translated_visitor_template(
                    hass_language, "insights_title", dog_name=dog_name
                ),
                "content": summary_content,
            }
        )

        return cards

    def _generate_health_management_buttons(
        self, dog_id: str, language: str | None
    ) -> CardConfigType:
        """Generate optimized health management buttons."""
        return {
            "type": "horizontal-stack",
            "cards": [
                {
                    "type": "button",
                    "name": _translated_health_label(language, "log_health"),
                    "icon": "mdi:heart-pulse",
                    "tap_action": {
                        "action": "call-service",
                        "service": f"{DOMAIN}.log_health",
                        "service_data": {"dog_id": dog_id},
                    },
                },
                {
                    "type": "button",
                    "name": _translated_health_label(language, "log_medication"),
                    "icon": "mdi:pill",
                    "tap_action": {
                        "action": "call-service",
                        "service": f"{DOMAIN}.log_medication",
                        "service_data": {
                            "dog_id": dog_id,
                            "medication_name": "Daily Supplement",
                            "dosage": "1 tablet",
                        },
                    },
                },
            ],
        }

    async def generate_gps_cards(
        self, dog_config: RawDogConfig, options: OptionsConfigType
    ) -> list[CardConfigType]:
        """Generate optimized GPS module cards.

        Args:
            dog_config: Dog configuration
            options: Display options

        Returns:
            List of GPS cards
        """
        typed_dog = self._ensure_dog_config(dog_config)
        if typed_dog is None:
            return []

        dog_config = typed_dog
        dog_id = dog_config[DOG_ID_FIELD]
        cards: list[CardConfigType] = []

        # OPTIMIZED: Check tracker entity first
        tracker_entity = f"device_tracker.{dog_id}_location"
        if not await self._entity_exists_cached(tracker_entity):
            return cards

        # OPTIMIZED: Generate main GPS map
        try:
            map_options = _coerce_map_options(options)
            map_card = await self.templates.get_map_card_template(dog_id, map_options)
            cards.append(map_card)
        except Exception as err:
            _LOGGER.warning("GPS map card generation failed: %s", err)

        # OPTIMIZED: Prepare GPS entities for batch validation
        gps_entities = [
            tracker_entity,
            f"sensor.{dog_id}_gps_accuracy",
            f"sensor.{dog_id}_distance_from_home",
            f"sensor.{dog_id}_speed",
            f"sensor.{dog_id}_battery_level",
        ]

        geofence_entities = [
            f"binary_sensor.{dog_id}_at_home",
            f"binary_sensor.{dog_id}_at_park",
            f"binary_sensor.{dog_id}_in_safe_zone",
            f"switch.{dog_id}_gps_tracking_enabled",
        ]

        # OPTIMIZED: Batch validate all GPS entities
        gps_valid_task = self._validate_entities_batch(gps_entities)
        geofence_valid_task = self._validate_entities_batch(geofence_entities)

        gps_result, geofence_result = await asyncio.gather(
            gps_valid_task, geofence_valid_task, return_exceptions=True
        )

        valid_gps: EntityListType = (
            _unwrap_async_result(
                gps_result,
                context="GPS status validation failed",
                logger=_LOGGER,
                level=logging.DEBUG,
            )
            or []
        )

        valid_geofence: EntityListType = (
            _unwrap_async_result(
                geofence_result,
                context="Geofence validation failed",
                logger=_LOGGER,
                level=logging.DEBUG,
            )
            or []
        )

        # Build cards based on validation results
        if valid_gps:
            cards.append(
                {
                    "type": "entities",
                    "title": "GPS Status",
                    "entities": valid_gps,
                    "state_color": True,
                }
            )

        if valid_geofence:
            cards.append(
                {
                    "type": "entities",
                    "title": "Geofence & Safety",
                    "entities": valid_geofence,
                }
            )

        # OPTIMIZED: Location history graph (async generation)
        try:
            history_entities = [
                f"sensor.{dog_id}_distance_from_home",
                f"sensor.{dog_id}_speed",
            ]

            history_card = await self.templates.get_history_graph_template(
                history_entities, "Location History", 24
            )

            if history_card and history_card.get("entities"):
                cards.append(history_card)

        except Exception as err:
            _LOGGER.debug("GPS history card generation failed: %s", err)

        return cards


class WeatherCardGenerator(BaseCardGenerator):
    """Generator for weather integration dashboard cards with advanced UI components.

    OPTIMIZED: Enhanced with weather health visualization, breed-specific recommendations,
    real-time alerts, forecast display, and interactive weather controls.

    Quality Scale: Bronze target
    Weather Integration: v1.0.0
    """

    @staticmethod
    def _normalise_recommendations(source: object) -> list[str]:
        """Return a flat list of recommendation strings from arbitrary payloads."""

        if source is None:
            return []

        if isinstance(source, str):
            cleaned = source.replace("\r", "\n")
            items: list[str] = []
            for chunk in cleaned.split("\n"):
                for part in chunk.split(";"):
                    candidate = part.strip()
                    if candidate:
                        items.append(candidate)
            return items

        if isinstance(source, Mapping):
            mapping_results: list[str] = []
            for key in (
                "recommendations",
                "items",
                "values",
                "text",
                "message",
                "detail",
            ):
                if key in source:
                    mapping_results.extend(
                        WeatherCardGenerator._normalise_recommendations(source[key])
                    )
            return mapping_results

        if isinstance(source, Sequence):
            sequence_results: list[str] = []
            for item in source:
                sequence_results.extend(
                    WeatherCardGenerator._normalise_recommendations(item)
                )
            return sequence_results

        candidate = str(source).strip()
        return [candidate] if candidate else []

    def _collect_weather_recommendations(self, entity_id: str) -> list[str]:
        """Gather structured weather recommendations from Home Assistant state."""

        state = self.hass.states.get(entity_id)
        if state is None:
            return []

        collected: list[str] = []

        attributes = getattr(state, "attributes", {})
        if isinstance(attributes, Mapping):
            collected.extend(
                self._normalise_recommendations(attributes.get("recommendations"))
            )

        collected.extend(self._normalise_recommendations(getattr(state, "state", "")))

        deduplicated: list[str] = []
        seen: set[str] = set()
        for recommendation in collected:
            entry = recommendation.strip()
            if not entry:
                continue
            key = entry.casefold()
            if key in seen:
                continue
            seen.add(key)
            deduplicated.append(entry)

        return deduplicated

    async def generate_weather_overview_cards(
        self,
        dog_config: RawDogConfig,
        options: OptionsConfigType,
    ) -> list[CardConfigType]:
        """Generate comprehensive weather overview cards for dog health monitoring.

        Args:
            dog_config: Dog configuration including breed and health data
            options: Display options for weather cards

        Returns:
            List of weather overview cards
        """
        typed_dog = self._ensure_dog_config(dog_config)
        if typed_dog is None:
            return []

        dog_config = typed_dog
        dog_id = dog_config[DOG_ID_FIELD]
        dog_name = dog_config[DOG_NAME_FIELD]
        modules = coerce_dog_modules_config(dog_config.get(DOG_MODULES_FIELD))

        # Check if weather module is enabled
        if not modules.get("weather"):
            return []

        start_time = asyncio.get_event_loop().time()
        cards: list[CardConfigType] = []

        # OPTIMIZED: Generate weather cards concurrently
        weather_card_tasks = [
            (
                "health_score",
                self._generate_weather_health_score_card(dog_id, dog_name, options),
            ),
            (
                "active_alerts",
                self._generate_active_weather_alerts_card(dog_id, dog_name, options),
            ),
            (
                "recommendations",
                self._generate_weather_recommendations_card(dog_id, dog_name, options),
            ),
            (
                "current_conditions",
                self._generate_current_weather_conditions_card(
                    dog_id, dog_name, options
                ),
            ),
        ]

        # Add breed-specific and forecast cards based on options
        if options.get("show_breed_advice", True):
            weather_card_tasks.append(
                (
                    "breed_advice",
                    self._generate_breed_weather_advice_card(dog_config, options),
                )
            )

        if options.get("show_weather_forecast", True):
            weather_card_tasks.append(
                (
                    "forecast",
                    self._generate_weather_forecast_card(dog_id, dog_name, options),
                )
            )

        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    *(task for _, task in weather_card_tasks), return_exceptions=True
                ),
                timeout=CARD_GENERATION_TIMEOUT,
            )

            # Process results with error handling
            for (card_type, _), result in zip(
                weather_card_tasks, results, strict=False
            ):
                card_payload = _unwrap_async_result(
                    result,
                    context=f"Weather card {card_type} generation failed for {dog_name}",
                    logger=_LOGGER,
                )
                if card_payload is None:
                    self._performance_stats["errors_handled"] += 1
                    continue
                cards.append(card_payload)

        except TimeoutError:
            _LOGGER.error("Weather cards generation timeout for %s", dog_name)
            self._performance_stats["errors_handled"] += 1
            # Return minimal weather card on timeout
            return [
                {
                    "type": "markdown",
                    "content": f"## 🌤️ {dog_name} Weather\n\nTimeout generating weather cards. Please refresh.",
                }
            ]

        generation_time = asyncio.get_event_loop().time() - start_time
        self._performance_stats["generation_time_total"] += generation_time

        if generation_time > 1.5:
            _LOGGER.info(
                "Slow weather card generation: %.2fs for %s", generation_time, dog_name
            )

        return cards

    async def _generate_weather_health_score_card(
        self, dog_id: str, dog_name: str, options: OptionsConfigType
    ) -> CardConfigType | None:
        """Generate weather health score card with gauge visualization."""
        score_entity = f"sensor.{dog_id}_weather_health_score"

        # OPTIMIZED: Use cached entity validation
        if not await self._entity_exists_cached(score_entity):
            return None

        return {
            "type": "vertical-stack",
            "cards": [
                {
                    "type": "gauge",
                    "entity": score_entity,
                    "name": f"🌤️ {dog_name} Weather Safety",
                    "min": 0,
                    "max": 100,
                    "unit": "/100",
                    "needle": True,
                    "severity": {"green": 80, "yellow": 60, "orange": 40, "red": 0},
                },
                {
                    "type": "markdown",
                    "content": f"""
{{% set score = states('sensor.{dog_id}_weather_health_score') | int(0) %}}
{{% if score >= 80 %}}
**🌟 Excellent conditions** - Perfect for all activities
{{% elif score >= 60 %}}
**✅ Good conditions** - Normal activities with basic precautions
{{% elif score >= 40 %}}
**⚠️ Caution needed** - Modified activities and close monitoring
{{% else %}}
**🚨 Dangerous conditions** - Indoor activities only, emergency precautions
{{% endif %}}

*Last updated: {{{{ states.sensor.{dog_id}_weather_health_score.last_updated.strftime('%H:%M') }}}}*
                    """,
                },
            ],
        }

    async def _generate_active_weather_alerts_card(
        self, dog_id: str, dog_name: str, options: OptionsConfigType
    ) -> CardConfigType | None:
        """Generate active weather alerts card with alert chips."""
        # OPTIMIZED: Batch validate all alert entities
        alert_entities = [
            f"binary_sensor.{dog_id}_heat_stress_alert",
            f"binary_sensor.{dog_id}_cold_stress_alert",
            f"binary_sensor.{dog_id}_uv_exposure_alert",
            f"binary_sensor.{dog_id}_humidity_warning",
            f"binary_sensor.{dog_id}_storm_warning",
            f"binary_sensor.{dog_id}_paw_protection_needed",
        ]

        valid_alerts = await self._validate_entities_batch(alert_entities)
        if not valid_alerts:
            return None

        # Create conditional alert chips
        alert_chips = []
        alert_configs = [
            ("heat_stress_alert", "🔥", "Heat Stress", "red"),
            ("cold_stress_alert", "🥶", "Cold Stress", "blue"),
            ("uv_exposure_alert", "☀️", "UV Risk", "orange"),
            ("humidity_warning", "💨", "Humidity", "purple"),
            ("storm_warning", "⛈️", "Storm", "dark"),
            ("paw_protection_needed", "🐾", "Paw Protection", "brown"),
        ]

        for alert_type, icon, name, color in alert_configs:
            entity_id = f"binary_sensor.{dog_id}_{alert_type}"
            if entity_id in valid_alerts:
                alert_chips.append(
                    {
                        "type": "conditional",
                        "conditions": [{"entity": entity_id, "state": "on"}],
                        "chip": {
                            "type": "entity",
                            "entity": entity_id,
                            "name": f"{icon} {name}",
                            "icon_color": color,
                            "content_info": "none",
                            "tap_action": {
                                "action": "more-info",
                                "entity": entity_id,
                            },
                        },
                    }
                )

        return {
            "type": "vertical-stack",
            "cards": [
                {
                    "type": "custom:mushroom-title-card",
                    "title": f"⚠️ {dog_name} Weather Alerts",
                    "subtitle": "Active weather health warnings",
                },
                {
                    "type": "conditional",
                    "conditions": [
                        {
                            "entity": f"binary_sensor.{dog_id}_weather_alerts_active",
                            "state": "on",
                        }
                    ],
                    "card": {
                        "type": "custom:mushroom-chips-card",
                        "chips": alert_chips,
                        "alignment": "justify",
                    },
                },
                {
                    "type": "conditional",
                    "conditions": [
                        {
                            "entity": f"binary_sensor.{dog_id}_weather_alerts_active",
                            "state": "off",
                        }
                    ],
                    "card": {
                        "type": "markdown",
                        "content": "✅ **No active weather alerts** - Conditions are safe for normal activities.",
                    },
                },
            ],
        }

    async def _generate_weather_recommendations_card(
        self, dog_id: str, dog_name: str, options: OptionsConfigType
    ) -> CardConfigType | None:
        """Generate weather recommendations card with actionable advice."""
        recommendations_entity = f"sensor.{dog_id}_weather_recommendations"

        if not await self._entity_exists_cached(recommendations_entity):
            return None

        recommendations = self._collect_weather_recommendations(recommendations_entity)
        primary_recommendations = recommendations[:5]
        overflow = max(len(recommendations) - len(primary_recommendations), 0)

        theme_option = options.get("theme") if isinstance(options, dict) else None
        theme = (
            theme_option if isinstance(theme_option, str) and theme_option else "modern"
        )

        markdown_card = await self.templates.get_weather_recommendations_card_template(
            dog_id,
            dog_name,
            theme=theme,
            recommendations=primary_recommendations,
            overflow_recommendations=overflow,
        )

        return {
            "type": "vertical-stack",
            "cards": [
                {
                    "type": "custom:mushroom-title-card",
                    "title": f"💡 {dog_name} Weather Advice",
                    "subtitle": "Personalized recommendations based on current conditions",
                },
                markdown_card,
                {
                    "type": "horizontal-stack",
                    "cards": [
                        {
                            "type": "custom:mushroom-entity-card",
                            "entity": f"button.{dog_id}_update_weather_data",
                            "name": "Update Weather",
                            "icon": "mdi:weather-cloudy-clock",
                            "icon_color": "blue",
                            "tap_action": {
                                "action": "call-service",
                                "service": "pawcontrol.update_weather_data",
                                "service_data": {"dog_id": dog_id},
                            },
                        },
                        {
                            "type": "custom:mushroom-entity-card",
                            "entity": f"button.{dog_id}_get_weather_recommendations",
                            "name": "Get Advice",
                            "icon": "mdi:lightbulb-on",
                            "icon_color": "amber",
                            "tap_action": {
                                "action": "call-service",
                                "service": "pawcontrol.get_weather_recommendations",
                                "service_data": {
                                    "dog_id": dog_id,
                                    "include_breed_specific": True,
                                    "include_health_conditions": True,
                                },
                            },
                        },
                    ],
                },
            ],
        }

    async def _generate_current_weather_conditions_card(
        self, dog_id: str, dog_name: str, options: OptionsConfigType
    ) -> CardConfigType | None:
        """Generate current weather conditions card with impact analysis."""
        # OPTIMIZED: Batch validate weather condition entities
        weather_entities = [
            f"sensor.{dog_id}_temperature_impact",
            f"sensor.{dog_id}_humidity_impact",
            f"sensor.{dog_id}_uv_exposure_level",
            f"sensor.{dog_id}_wind_impact",
        ]

        valid_entities = await self._validate_entities_batch(weather_entities)
        if not valid_entities:
            return None

        # Create entities list for display
        entity_configs = []

        entity_mappings = [
            (
                f"sensor.{dog_id}_temperature_impact",
                "Temperature Impact",
                "mdi:thermometer",
            ),
            (
                f"sensor.{dog_id}_humidity_impact",
                "Humidity Impact",
                "mdi:water-percent",
            ),
            (
                f"sensor.{dog_id}_uv_exposure_level",
                "UV Exposure Level",
                "mdi:weather-sunny",
            ),
            (f"sensor.{dog_id}_wind_impact", "Wind Impact", "mdi:weather-windy"),
        ]

        for entity_id, name, icon in entity_mappings:
            if entity_id in valid_entities:
                entity_configs.append(
                    {
                        "entity": entity_id,
                        "name": name,
                        "icon": icon,
                    }
                )

        return {
            "type": "entities",
            "title": f"🌡️ {dog_name} Weather Impact",
            "entities": entity_configs,
            "state_color": True,
            "show_header_toggle": False,
        }

    async def _generate_breed_weather_advice_card(
        self, dog_config: RawDogConfig, options: OptionsConfigType
    ) -> CardConfigType | None:
        """Generate breed-specific weather advice card."""
        typed_dog = self._ensure_dog_config(dog_config)
        if typed_dog is None:
            return None

        dog_config = typed_dog
        dog_id = dog_config[DOG_ID_FIELD]
        dog_name = dog_config[DOG_NAME_FIELD]
        dog_breed = dog_config.get("breed", "Mixed Breed")

        breed_advice_entity = f"sensor.{dog_id}_breed_weather_advice"

        if not await self._entity_exists_cached(breed_advice_entity):
            return None

        return {
            "type": "vertical-stack",
            "cards": [
                {
                    "type": "custom:mushroom-title-card",
                    "title": f"🐕 {dog_breed} Weather Guide",
                    "subtitle": f"Breed-specific advice for {dog_name}",
                },
                {
                    "type": "markdown",
                    "content": f"""
{{% set breed_advice = states('sensor.{dog_id}_breed_weather_advice') %}}
{{% if breed_advice and breed_advice != 'unknown' %}}
**Breed Characteristics:**
{{% set advice_parts = breed_advice.split('|') %}}
{{% for part in advice_parts %}}
• {{{{ part.strip() }}}}
{{% endfor %}}
{{% else %}}
*Breed-specific advice not available*
{{% endif %}}

**General {dog_breed} Considerations:**
• Check current weather score above
• Monitor for breed-specific symptoms
• Adjust exercise intensity accordingly
                    """,
                },
            ],
        }

    async def _generate_weather_forecast_card(
        self, dog_id: str, dog_name: str, options: OptionsConfigType
    ) -> CardConfigType | None:
        """Generate weather forecast card with health predictions."""
        forecast_entity = f"sensor.{dog_id}_weather_forecast_health"

        language: str | None = getattr(self.hass.config, "language", None)

        if not await self._entity_exists_cached(forecast_entity):
            return None

        return {
            "type": "vertical-stack",
            "cards": [
                {
                    "type": "custom:mushroom-title-card",
                    "title": f"🔮 {dog_name} Weather Forecast",
                    "subtitle": "Upcoming weather health predictions",
                },
                {
                    "type": "markdown",
                    "content": f"""
{{% set forecast_data = states('sensor.{dog_id}_weather_forecast_health') %}}
{{% if forecast_data and forecast_data != 'unknown' %}}
**Next 24 Hours:**
{{{{ forecast_data }}}}
{{% else %}}
*Weather forecast data not available*
{{% endif %}}

**Planning Tips:**
• Schedule walks during optimal times
• Prepare weather protection gear
• Monitor conditions throughout the day
                    """,
                },
                {
                    "type": "horizontal-stack",
                    "cards": [
                        {
                            "type": "custom:mushroom-entity-card",
                            "entity": f"sensor.{dog_id}_next_optimal_walk_time",
                            "name": _translated_walk_label(language, "next_good_time"),
                            "icon": "mdi:clock-check",
                            "icon_color": "green",
                        },
                        {
                            "type": "custom:mushroom-entity-card",
                            "entity": f"sensor.{dog_id}_weather_trend",
                            "name": "Weather Trend",
                            "icon": "mdi:trending-up",
                            "icon_color": "blue",
                        },
                    ],
                },
            ],
        }

    async def generate_weather_controls_card(
        self, dog_config: RawDogConfig, options: OptionsConfigType
    ) -> CardConfigType | None:
        """Generate weather control buttons and settings card."""
        typed_dog = self._ensure_dog_config(dog_config)
        if typed_dog is None:
            return None

        dog_config = typed_dog
        dog_id = dog_config[DOG_ID_FIELD]
        dog_name = dog_config[DOG_NAME_FIELD]

        # OPTIMIZED: Check if weather controls are enabled
        weather_switch = f"switch.{dog_id}_weather_monitoring"
        if not await self._entity_exists_cached(weather_switch):
            return None

        return {
            "type": "vertical-stack",
            "cards": [
                {
                    "type": "custom:mushroom-title-card",
                    "title": f"⚙️ {dog_name} Weather Settings",
                    "subtitle": "Control weather monitoring and alerts",
                },
                {
                    "type": "entities",
                    "entities": [
                        {
                            "entity": f"switch.{dog_id}_weather_monitoring",
                            "name": "Weather Monitoring",
                            "icon": "mdi:weather-partly-cloudy",
                        },
                        {
                            "entity": f"switch.{dog_id}_heat_alerts",
                            "name": "Heat Stress Alerts",
                            "icon": "mdi:thermometer-high",
                        },
                        {
                            "entity": f"switch.{dog_id}_cold_alerts",
                            "name": "Cold Stress Alerts",
                            "icon": "mdi:snowflake",
                        },
                        {
                            "entity": f"switch.{dog_id}_uv_alerts",
                            "name": "UV Protection Alerts",
                            "icon": "mdi:weather-sunny-alert",
                        },
                    ],
                    "show_header_toggle": False,
                    "state_color": True,
                },
                {
                    "type": "grid",
                    "columns": 2,
                    "cards": [
                        {
                            "type": "custom:mushroom-entity-card",
                            "entity": f"number.{dog_id}_heat_threshold",
                            "name": "Heat Threshold",
                            "icon": "mdi:temperature-celsius",
                            "icon_color": "red",
                        },
                        {
                            "type": "custom:mushroom-entity-card",
                            "entity": f"number.{dog_id}_cold_threshold",
                            "name": "Cold Threshold",
                            "icon": "mdi:temperature-celsius",
                            "icon_color": "blue",
                        },
                    ],
                },
            ],
        }

    async def generate_weather_history_card(
        self, dog_config: RawDogConfig, options: OptionsConfigType
    ) -> CardConfigType | None:
        """Generate weather history and trends card."""
        typed_dog = self._ensure_dog_config(dog_config)
        if typed_dog is None:
            return None

        dog_config = typed_dog
        dog_id = dog_config[DOG_ID_FIELD]
        dog_name = dog_config[DOG_NAME_FIELD]

        # OPTIMIZED: Batch validate history entities
        history_entities = [
            f"sensor.{dog_id}_weather_health_score",
            f"sensor.{dog_id}_temperature_impact",
            f"sensor.{dog_id}_daily_weather_alerts_count",
        ]

        valid_entities = await self._validate_entities_batch(history_entities)
        if not valid_entities:
            return None

        return {
            "type": "history-graph",
            "title": f"📈 {dog_name} Weather History (7 days)",
            "entities": valid_entities,
            "hours_to_show": 168,  # 7 days
            "refresh_interval": 0,
            "logarithmic_scale": False,
        }


class StatisticsCardGenerator(BaseCardGenerator):
    """Generator for statistics dashboard cards with performance optimization."""

    async def generate_statistics_cards(
        self,
        dogs_config: Sequence[RawDogConfig],
        options: OptionsConfigType,
        *,
        coordinator_statistics: CoordinatorStatisticsPayload
        | Mapping[str, Any]
        | None = None,
    ) -> list[CardConfigType]:
        """Generate optimized statistics cards for all dogs.

        Args:
            dogs_config: List of dog configurations
            options: Display options

        Returns:
            List of statistics cards
        """
        typed_dogs = self._ensure_dog_configs(dogs_config)
        if not typed_dogs:
            return []

        cards: list[CardConfigType] = []

        theme_option = options.get("theme") if isinstance(options, dict) else None
        theme = (
            theme_option if isinstance(theme_option, str) and theme_option else "modern"
        )

        # OPTIMIZED: Generate all statistics cards concurrently
        stats_generators = [
            ("activity", self._generate_activity_statistics(typed_dogs, theme)),
            ("feeding", self._generate_feeding_statistics(typed_dogs, theme)),
            ("walk", self._generate_walk_statistics(typed_dogs, theme)),
            ("health", self._generate_health_statistics(typed_dogs, theme)),
        ]

        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    *(task for _, task in stats_generators), return_exceptions=True
                ),
                timeout=CARD_GENERATION_TIMEOUT,
            )

            # Process results with error handling
            for (stats_type, _), result in zip(stats_generators, results, strict=False):
                card_payload = _unwrap_async_result(
                    result,
                    context=f"Statistics card {stats_type} generation failed",
                    logger=_LOGGER,
                )
                if card_payload is None:
                    self._performance_stats["errors_handled"] += 1
                    continue
                cards.append(card_payload)

        except TimeoutError:
            _LOGGER.error("Statistics cards generation timeout")
            self._performance_stats["errors_handled"] += 1

        # Add summary card (always include)
        summary_card = self._generate_summary_card(
            typed_dogs,
            theme,
            coordinator_statistics=coordinator_statistics,
        )
        cards.append(summary_card)

        return cards

    async def _generate_activity_statistics(
        self, dogs_config: Sequence[DogConfigData], theme: str
    ) -> CardConfigType | None:
        """Generate optimized activity statistics card."""
        # OPTIMIZED: Build entity list efficiently
        activity_entities = []

        for dog in dogs_config:
            dog_id = dog[DOG_ID_FIELD]
            if dog_id:
                activity_entities.append(f"sensor.{dog_id}_activity_level")

        if not activity_entities:
            return None

        # OPTIMIZED: Batch validate all activity entities
        valid_entities = await self._validate_entities_batch(activity_entities)

        return await self.templates.get_statistics_graph_template(
            "Activity Statistics (30 days)",
            valid_entities,
            ["mean", "min", "max"],
            days_to_show=30,
            theme=theme,
        )

    async def _generate_feeding_statistics(
        self, dogs_config: Sequence[DogConfigData], theme: str
    ) -> CardConfigType | None:
        """Generate optimized feeding statistics card."""
        feeding_entities = []

        for dog in dogs_config:
            dog_id = dog[DOG_ID_FIELD]
            modules = coerce_dog_modules_config(dog.get(DOG_MODULES_FIELD))
            if dog_id and modules.get(MODULE_FEEDING):
                feeding_entities.append(f"sensor.{dog_id}_meals_today")

        if not feeding_entities:
            return None

        # OPTIMIZED: Batch validate feeding entities
        valid_entities = await self._validate_entities_batch(feeding_entities)

        return await self.templates.get_statistics_graph_template(
            "Feeding Statistics (30 days)",
            valid_entities,
            ["sum", "mean"],
            days_to_show=30,
            theme=theme,
        )

    async def _generate_walk_statistics(
        self, dogs_config: Sequence[DogConfigData], theme: str
    ) -> CardConfigType | None:
        """Generate optimized walk statistics card."""
        walk_entities = []

        language: str | None = getattr(self.hass.config, "language", None)

        for dog in dogs_config:
            dog_id = dog[DOG_ID_FIELD]
            modules = coerce_dog_modules_config(dog.get(DOG_MODULES_FIELD))
            if dog_id and modules.get(MODULE_WALK):
                walk_entities.append(f"sensor.{dog_id}_walk_distance_today")

        if not walk_entities:
            return None

        # OPTIMIZED: Batch validate walk entities
        valid_entities = await self._validate_entities_batch(walk_entities)

        return await self.templates.get_statistics_graph_template(
            _translated_walk_template(language, "statistics_title", days=30),
            valid_entities,
            ["sum", "mean", "max"],
            days_to_show=30,
            theme=theme,
        )

    async def _generate_health_statistics(
        self, dogs_config: Sequence[DogConfigData], theme: str
    ) -> CardConfigType | None:
        """Generate optimized health statistics card."""
        weight_entities = []

        for dog in dogs_config:
            dog_id = dog[DOG_ID_FIELD]
            modules = coerce_dog_modules_config(dog.get(DOG_MODULES_FIELD))
            if dog_id and modules.get(MODULE_HEALTH):
                weight_entities.append(f"sensor.{dog_id}_weight")

        if not weight_entities:
            return None

        # OPTIMIZED: Batch validate weight entities
        valid_entities = await self._validate_entities_batch(weight_entities)

        return await self.templates.get_statistics_graph_template(
            "Weight Trends (60 days)",
            valid_entities,
            ["mean", "min", "max"],
            days_to_show=60,
            theme=theme,
        )

    def _generate_summary_card(
        self,
        dogs_config: Sequence[DogConfigData],
        theme: str,
        *,
        coordinator_statistics: CoordinatorStatisticsPayload
        | Mapping[str, Any]
        | None = None,
    ) -> CardConfigType:
        """Generate optimized statistics summary card."""
        return self.templates.get_statistics_summary_template(
            list(dogs_config),
            theme,
            coordinator_statistics=coordinator_statistics,
        )


# OPTIMIZED: Global cache cleanup function
async def cleanup_validation_cache() -> None:
    """Clean up global validation cache."""
    global _entity_validation_cache
    current_time = asyncio.get_event_loop().time()

    expired_keys = [
        entity_id
        for entity_id, (timestamp, _) in _entity_validation_cache.items()
        if current_time - timestamp > _cache_cleanup_threshold
    ]

    for key in expired_keys:
        _entity_validation_cache.pop(key, None)

    _LOGGER.debug("Cleaned %d expired entries from validation cache", len(expired_keys))


# OPTIMIZED: Export performance monitoring function
def get_global_performance_stats() -> dict[str, Any]:
    """Get global performance statistics for all card generators."""
    return {
        "validation_cache_size": len(_entity_validation_cache),
        "cache_threshold": _cache_cleanup_threshold,
        "max_concurrent_validations": MAX_CONCURRENT_VALIDATIONS,
        "validation_timeout": ENTITY_VALIDATION_TIMEOUT,
        "card_generation_timeout": CARD_GENERATION_TIMEOUT,
    }


def _unwrap_async_result[T](
    result: T | BaseException,
    *,
    context: str,
    logger: logging.Logger = _LOGGER,
    level: int = logging.WARNING,
    suppress_cancelled: bool = False,
) -> T | None:
    """Wrap :func:`unwrap_async_result` with module logging defaults."""

    return unwrap_async_result(
        result,
        context=context,
        logger=logger,
        level=level,
        suppress_cancelled=suppress_cancelled,
    )
