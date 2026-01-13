"""Ultra-optimized switch platform for PawControl with profile-based entity creation.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+

This module implements profile-optimized switch entities that only create switches
for enabled modules, significantly reducing entity count and improving performance.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from typing import Any, cast

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .compat import HomeAssistantError
from .const import (
    CONF_DOGS,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_GROOMING,
    MODULE_HEALTH,
    MODULE_MEDICATION,
    MODULE_NOTIFICATIONS,
    MODULE_TRAINING,
    MODULE_VISITOR,
    MODULE_WALK,
)
from .coordinator import PawControlCoordinator
from .diagnostics import normalize_value
from .entity import PawControlDogEntityBase
from .grooming_translations import translated_grooming_label
from .runtime_data import get_runtime_data
from .types import (
    DOG_ID_FIELD,
    DOG_MODULES_FIELD,
    DOG_NAME_FIELD,
    CoordinatorDogData,
    DogConfigData,
    DogModulesConfig,
    JSONMutableMapping,
    PawControlConfigEntry,
    coerce_dog_modules_config,
    ensure_json_mapping,
)
from .utils import async_call_add_entities

_LOGGER = logging.getLogger(__name__)

# OPTIMIZATION: Enhanced batching parameters for profile-based creation
BATCH_SIZE = 15  # Optimized for profile-filtered entities
BATCH_DELAY = 0.003  # Reduced to 3ms for faster setup
MAX_CONCURRENT_BATCHES = 8  # Balanced for profile optimization

# Switches toggle features and therefore execute actions. The coordinator
# prevents conflicting commands, so we can expose unlimited parallel entity
# updates to Home Assistant.
PARALLEL_UPDATES = 0


class ProfileOptimizedSwitchFactory:
    """Factory for efficient profile-based switch creation with minimal entity count."""

    # Module configurations - only for modules that support switches
    MODULE_CONFIGS = [
        (MODULE_FEEDING, 'Feeding Tracking', 'mdi:food-drumstick'),
        (MODULE_WALK, 'Walk Tracking', 'mdi:walk'),
        (MODULE_GPS, 'GPS Tracking', 'mdi:map-marker'),
        (MODULE_HEALTH, 'Health Monitoring', 'mdi:heart-pulse'),
        (MODULE_NOTIFICATIONS, 'Notifications', 'mdi:bell'),
        (MODULE_GROOMING, 'Grooming Tracking', 'mdi:content-cut'),
        (MODULE_MEDICATION, 'Medication Tracking', 'mdi:pill'),
        (MODULE_TRAINING, 'Training Mode', 'mdi:school'),
    ]

    # Feature switches grouped by module - only created if module is enabled
    FEATURE_SWITCHES = {
        MODULE_FEEDING: [
            ('auto_feeding_reminders', 'Auto Feeding Reminders', 'mdi:clock-alert'),
            ('feeding_schedule', 'Feeding Schedule', 'mdi:calendar-check'),
            ('portion_control', 'Portion Control', 'mdi:scale'),
            ('feeding_alerts', 'Feeding Alerts', 'mdi:alert-circle'),
            ('meal_tracking', 'Meal Tracking', 'mdi:food-variant'),
        ],
        MODULE_GPS: [
            ('gps_tracking', 'GPS Tracking', 'mdi:crosshairs-gps'),
            ('geofencing', 'Geofencing', 'mdi:map-marker-circle'),
            ('route_recording', 'Route Recording', 'mdi:map-marker-path'),
            ('auto_walk_detection', 'Auto Walk Detection', 'mdi:walk'),
            ('location_sharing', 'Location Sharing', 'mdi:share-variant'),
            ('safety_zones', 'Safety Zones', 'mdi:shield-check'),
        ],
        MODULE_HEALTH: [
            ('health_monitoring', 'Health Monitoring', 'mdi:heart-pulse'),
            ('weight_tracking', 'Weight Tracking', 'mdi:scale'),
            ('medication_reminders', 'Medication Reminders', 'mdi:pill'),
            ('vet_reminders', 'Vet Reminders', 'mdi:medical-bag'),
            ('activity_tracking', 'Activity Tracking', 'mdi:run'),
            ('health_alerts', 'Health Alerts', 'mdi:alert-octagon'),
        ],
        MODULE_NOTIFICATIONS: [
            ('notifications', 'Notifications', 'mdi:bell'),
            ('urgent_notifications', 'Urgent Notifications', 'mdi:bell-alert'),
            ('daily_reports', 'Daily Reports', 'mdi:file-chart'),
            ('weekly_reports', 'Weekly Reports', 'mdi:calendar-week'),
            ('sound_alerts', 'Sound Alerts', 'mdi:volume-high'),
        ],
        MODULE_WALK: [
            ('walk_reminders', 'Walk Reminders', 'mdi:clock-alert-outline'),
            ('auto_walk_start', 'Auto Walk Start', 'mdi:play-circle'),
            ('walk_analytics', 'Walk Analytics', 'mdi:chart-line'),
        ],
        MODULE_GROOMING: [
            ('grooming_reminders', 'Grooming Reminders', 'mdi:clock-alert'),
            ('grooming_schedule', 'Grooming Schedule', 'mdi:calendar'),
            ('grooming_tracking', 'Grooming Tracking', 'mdi:clipboard-list'),
        ],
        MODULE_MEDICATION: [
            ('medication_schedule', 'Medication Schedule', 'mdi:calendar-clock'),
            ('dose_reminders', 'Dose Reminders', 'mdi:alarm'),
            ('medication_tracking', 'Medication Tracking', 'mdi:clipboard-check'),
        ],
        MODULE_TRAINING: [
            ('training_mode', 'Training Mode', 'mdi:school'),
            ('training_reminders', 'Training Reminders', 'mdi:bell-outline'),
            ('progress_tracking', 'Progress Tracking', 'mdi:trending-up'),
        ],
    }

    @classmethod
    def create_switches_for_dog(
        cls,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
        modules: DogModulesConfig,
    ) -> list[OptimizedSwitchBase]:
        """Create profile-optimized switches for a dog.

        Only creates switches for enabled modules to minimize entity count.

        Args:
            coordinator: Data coordinator
            dog_id: Dog identifier
            dog_name: Dog name
            modules: Enabled modules configuration

        Returns:
            List of switch entities (profile-optimized)
        """
        switches: list[OptimizedSwitchBase] = []
        enabled_modules = {m for m, e in modules.items() if e}

        _LOGGER.debug(
            'Creating profile-optimized switches for %s. Enabled modules: %s',
            dog_name,
            enabled_modules,
        )

        # Base switches - always created (essential functionality)
        switches.extend(
            [
                PawControlMainPowerSwitch(coordinator, dog_id, dog_name),
                PawControlDoNotDisturbSwitch(coordinator, dog_id, dog_name),
            ]
        )

        # Visitor mode switch - only if visitor module enabled OR as fallback
        if MODULE_VISITOR in enabled_modules or not enabled_modules:
            switches.append(PawControlVisitorModeSwitch(coordinator, dog_id, dog_name))

        # Module control switches - only for enabled modules
        for module_id, module_name, icon in cls.MODULE_CONFIGS:
            if module_id in enabled_modules:
                switches.append(
                    PawControlModuleSwitch(
                        coordinator,
                        dog_id,
                        dog_name,
                        module_id,
                        module_name,
                        icon,
                        True,  # Already enabled in profile
                    )
                )

        # Feature switches - only for enabled modules
        for module in enabled_modules:
            if module in cls.FEATURE_SWITCHES:
                for switch_id, switch_name, icon in cls.FEATURE_SWITCHES[module]:
                    switches.append(
                        PawControlFeatureSwitch(
                            coordinator,
                            dog_id,
                            dog_name,
                            switch_id,
                            switch_name,
                            icon,
                            module,
                        )
                    )

        _LOGGER.debug(
            'Created %d profile-optimized switches for %s (modules: %d enabled)',
            len(switches),
            dog_name,
            len(enabled_modules),
        )

        return switches


async def _async_add_entities_in_batches(
    async_add_entities_func: AddEntitiesCallback,
    entities: Sequence[OptimizedSwitchBase],
    *,
    batch_size: int = BATCH_SIZE,
    delay_between_batches: float = BATCH_DELAY,
) -> None:
    """Add switch entities in optimized batches to prevent Entity Registry overload.

    Args:
        async_add_entities_func: The actual async_add_entities callback
        entities: List of switch entities to add
        batch_size: Number of entities per batch
        delay_between_batches: Seconds to wait between batches
    """
    total_entities = len(entities)

    if total_entities == 0:
        _LOGGER.debug('No switches to add - profile optimization successful')
        return

    _LOGGER.debug(
        'Adding %d profile-optimized switches in batches of %d',
        total_entities,
        batch_size,
    )

    # Process entities in batches
    for i in range(0, total_entities, batch_size):
        batch = entities[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_entities + batch_size - 1) // batch_size

        _LOGGER.debug(
            'Processing switch batch %d/%d with %d entities',
            batch_num,
            total_batches,
            len(batch),
        )

        # Add batch without update_before_add to reduce Registry load
        await async_call_add_entities(
            async_add_entities_func, batch, update_before_add=False
        )

        # Small delay between batches to prevent Registry flooding
        if i + batch_size < total_entities:  # No delay after last batch
            await asyncio.sleep(delay_between_batches)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PawControlConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PawControl switch platform with profile-based optimization."""

    runtime_data = get_runtime_data(hass, entry)
    if runtime_data is None:
        _LOGGER.error('Runtime data missing for entry %s', entry.entry_id)
        return

    coordinator = runtime_data.coordinator
    dogs: list[DogConfigData] = runtime_data.dogs

    # Profile-optimized entity creation
    all_entities: list[OptimizedSwitchBase] = []
    total_modules_enabled = 0

    for dog in dogs:
        dog_id = dog[DOG_ID_FIELD]
        dog_name = dog[DOG_NAME_FIELD]
        modules = coerce_dog_modules_config(dog.get(DOG_MODULES_FIELD))

        # Count enabled modules for statistics
        enabled_count = sum(1 for enabled in modules.values() if enabled)
        total_modules_enabled += enabled_count

        _LOGGER.debug(
            'Processing dog %s: %d/%d modules enabled',
            dog_name,
            enabled_count,
            len(modules),
        )

        # Create only switches for enabled modules
        dog_switches = ProfileOptimizedSwitchFactory.create_switches_for_dog(
            coordinator, dog_id, dog_name, modules
        )
        all_entities.extend(dog_switches)

    total_entities = len(all_entities)

    # Add entities using optimized batching
    await _async_add_entities_in_batches(async_add_entities, all_entities)

    _LOGGER.info(
        'Profile optimization: Created %d switch entities for %d dogs '
        '(avg %.1f switches/dog, %d total modules enabled)',
        total_entities,
        len(dogs),
        total_entities / len(dogs) if dogs else 0,
        total_modules_enabled,
    )


class OptimizedSwitchBase(PawControlDogEntityBase, SwitchEntity, RestoreEntity):
    """Optimized base switch class with enhanced caching and state management."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    # OPTIMIZATION: Enhanced state cache with TTL
    _state_cache: dict[str, tuple[bool, float]] = {}
    _cache_ttl = 3.0  # Reduced to 3 seconds for better responsiveness

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
        switch_type: str,
        *,
        device_class: SwitchDeviceClass | None = None,
        icon: str | None = None,
        entity_category: EntityCategory | None = None,
        initial_state: bool = False,
    ) -> None:
        """Initialize optimized switch with profile awareness."""
        super().__init__(coordinator, dog_id, dog_name)
        self._switch_type = switch_type
        self._is_on = initial_state
        self._last_changed = dt_util.utcnow()

        # Entity configuration
        self._attr_unique_id = f"pawcontrol_{dog_id}_{switch_type}"
        self._attr_translation_key = switch_type
        self._attr_device_class = device_class
        self._attr_icon = icon
        self._attr_entity_category = entity_category

        # Link entity to PawControl device entry for the dog
        self.update_device_metadata(
            model='Smart Dog Monitoring',
            sw_version='1.1.0',
            configuration_url='https://github.com/BigDaddy1990/pawcontrol',
        )

    async def async_added_to_hass(self) -> None:
        """Restore state when added with enhanced logging."""
        await super().async_added_to_hass()

        # Restore previous state
        if last_state := await self.async_get_last_state():
            if last_state.state in ('on', 'off'):
                self._is_on = last_state.state == 'on'
                _LOGGER.debug(
                    'Restored switch state for %s %s: %s',
                    self._dog_name,
                    self._switch_type,
                    'on' if self._is_on else 'off',
                )

    @property
    def is_on(self) -> bool:
        """Return switch state with enhanced caching."""
        # Check cache first
        cache_key = f"{self._dog_id}_{self._switch_type}"
        now = dt_util.utcnow().timestamp()

        if cache_key in self._state_cache:
            cached_state, cache_time = self._state_cache[cache_key]
            if now - cache_time < self._cache_ttl:
                return cached_state

        # Return stored state and update cache
        self._update_cache(self._is_on)
        return self._is_on

    @property
    def extra_state_attributes(self) -> JSONMutableMapping:
        """Return enhanced attributes with profile information."""
        attrs = ensure_json_mapping(super().extra_state_attributes)
        attrs.update(
            {
                'dog_id': self._dog_id,
                'dog_name': self._dog_name,
                'switch_type': self._switch_type,
                'last_changed': self._last_changed.isoformat(),
                'profile_optimized': True,
            }
        )

        if dog_config := self._get_dog_config():
            modules = coerce_dog_modules_config(dog_config.get(DOG_MODULES_FIELD))
            enabled_modules = [module for module, enabled in modules.items() if enabled]
            attrs['enabled_modules'] = enabled_modules
            attrs['total_modules'] = len(enabled_modules)

        return cast(JSONMutableMapping, normalize_value(attrs))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn switch on with enhanced error handling."""
        try:
            await self._async_set_state(True)
            self._is_on = True
            self._last_changed = dt_util.utcnow()
            self._update_cache(True)
            if self.hass is not None:
                self.async_write_ha_state()

            _LOGGER.debug(
                'Switch turned on: %s %s',
                self._dog_name,
                self._switch_type,
            )

        except Exception as err:
            _LOGGER.error(
                'Failed to turn on %s for %s: %s',
                self._switch_type,
                self._dog_name,
                err,
            )
            raise HomeAssistantError(f"Failed to turn on {self._switch_type}") from err

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn switch off with enhanced error handling."""
        try:
            await self._async_set_state(False)
            self._is_on = False
            self._last_changed = dt_util.utcnow()
            self._update_cache(False)
            if self.hass is not None:
                self.async_write_ha_state()

            _LOGGER.debug(
                'Switch turned off: %s %s',
                self._dog_name,
                self._switch_type,
            )

        except Exception as err:
            _LOGGER.error(
                'Failed to turn off %s for %s: %s',
                self._switch_type,
                self._dog_name,
                err,
            )
            raise HomeAssistantError(f"Failed to turn off {self._switch_type}") from err

    async def _async_set_state(self, state: bool) -> None:
        """Set switch state - override in subclasses."""
        # Base implementation - subclasses should override
        pass

    def _update_cache(self, state: bool) -> None:
        """Update state cache with current timestamp."""
        cache_key = f"{self._dog_id}_{self._switch_type}"
        self._state_cache[cache_key] = (state, dt_util.utcnow().timestamp())

    def _get_coordinator_dog_data(self) -> CoordinatorDogData | None:
        """Get dog data from coordinator."""

        if self.coordinator.available:
            return self.coordinator.get_dog_data(self._dog_id)
        return None

    def _get_dog_config(self) -> DogConfigData | None:
        """Return the typed dog configuration when available."""

        payload = self._get_coordinator_dog_data()
        if payload is None:
            return None

        dog_info = payload.get('dog_info')
        if isinstance(dog_info, Mapping):
            return cast(DogConfigData, dog_info)

        return None

    @property
    def available(self) -> bool:
        """Check availability with enhanced logic."""
        return (
            self.coordinator.available and self._get_coordinator_dog_data() is not None
        )


# Core switches (always created)
class PawControlMainPowerSwitch(OptimizedSwitchBase):
    """Main power switch for dog monitoring system."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialise the master power toggle for the integration."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            'main_power',
            device_class=SwitchDeviceClass.SWITCH,
            icon='mdi:power',
            initial_state=True,
        )

    async def _async_set_state(self, state: bool) -> None:
        """Set main power state with system-wide impact."""
        if self.hass is None:
            _LOGGER.debug('Skipping main power update; hass not available')
            return

        try:
            data_manager = self._get_data_manager()

            if data_manager is not None:
                await data_manager.async_set_dog_power_state(self._dog_id, state)

            # High priority refresh for power changes
            await self.coordinator.async_request_selective_refresh(
                [self._dog_id], priority=10
            )

        except Exception as err:
            _LOGGER.warning('Power state update failed for %s: %s', self._dog_name, err)


class PawControlDoNotDisturbSwitch(OptimizedSwitchBase):
    """Do not disturb switch for quiet periods."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialise the do-not-disturb switch."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            'do_not_disturb',
            icon='mdi:sleep',
            initial_state=False,
        )

    async def _async_set_state(self, state: bool) -> None:
        """Set DND state with notification impact."""
        if self.hass is None:
            _LOGGER.debug('Skipping DND update; hass not available')
            return

        try:
            notification_manager = self._get_notification_manager()

            if notification_manager and hasattr(
                notification_manager, 'async_set_dnd_mode'
            ):
                await notification_manager.async_set_dnd_mode(self._dog_id, state)

        except Exception as err:
            _LOGGER.error('Failed to update DND for %s: %s', self._dog_name, err)


class PawControlVisitorModeSwitch(OptimizedSwitchBase):
    """Visitor mode switch for reduced monitoring."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialise the visitor mode switch for temporary guests."""
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            'visitor_mode',
            icon='mdi:account-group',
            initial_state=False,
        )

    @property
    def is_on(self) -> bool:
        """Check visitor mode state from data."""
        if dog_data := self._get_coordinator_dog_data():
            return bool(dog_data.get('visitor_mode_active', False))
        return self._is_on

    async def _async_set_state(self, state: bool) -> None:
        """Set visitor mode with service call."""
        if not await self._async_call_hass_service(
            DOMAIN,
            'set_visitor_mode',
            {
                'dog_id': self._dog_id,
                'enabled': state,
                'visitor_name': 'Switch Toggle' if state else None,
                'reduced_alerts': state,
            },
            blocking=False,
        ):
            return


# Module switch (only for enabled modules)
class PawControlModuleSwitch(OptimizedSwitchBase):
    """Switch to control individual modules."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
        module_id: str,
        module_name: str,
        icon: str,
        initial_state: bool,
    ) -> None:
        """Initialise a toggle for enabling or disabling a module."""
        self._module_id = module_id
        hass_language: str | None = None
        hass_obj = getattr(coordinator, 'hass', None)
        config_obj = getattr(hass_obj, 'config', None) if hass_obj else None
        if config_obj is not None:
            hass_language = getattr(config_obj, 'language', None)

        if module_id == MODULE_GROOMING:
            display_name = translated_grooming_label(hass_language, 'module_switch')
        else:
            display_name = module_name

        self._module_name = display_name

        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            f"module_{module_id}",
            icon=icon,
            initial_state=initial_state,
            entity_category=EntityCategory.CONFIG,
        )
        self._attr_name = f"{dog_name} {display_name}"

    async def _async_set_state(self, state: bool) -> None:
        """Set module state with config update."""
        hass = self.hass
        if hass is None:
            _LOGGER.debug('Skipping module state update; hass not available')
            return

        try:
            # Update config entry
            new_data = dict(self.coordinator.config_entry.data)
            dogs_data = list(new_data.get(CONF_DOGS, []))

            for index, dog in enumerate(dogs_data):
                if not isinstance(dog, dict):
                    continue
                if dog.get(DOG_ID_FIELD) != self._dog_id:
                    continue

                modules = dict(coerce_dog_modules_config(dog.get(DOG_MODULES_FIELD)))
                modules[self._module_id] = state
                dogs_data[index] = {
                    **dog,
                    DOG_MODULES_FIELD: cast(DogModulesConfig, modules),
                }
                break

            new_data[CONF_DOGS] = dogs_data

            hass.config_entries.async_update_entry(
                self.coordinator.config_entry, data=new_data
            )

            await self.coordinator.async_request_selective_refresh(
                [self._dog_id], priority=7
            )

            _LOGGER.info(
                'Module %s %s for %s',
                self._module_name,
                'enabled' if state else 'disabled',
                self._dog_name,
            )

        except Exception as err:
            _LOGGER.error(
                'Failed to update module %s for %s: %s',
                self._module_name,
                self._dog_name,
                err,
            )


# Feature switch (only for enabled modules)
class PawControlFeatureSwitch(OptimizedSwitchBase):
    """Feature switch for module-specific functionality."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
        feature_id: str,
        feature_name: str,
        icon: str,
        module: str,
    ) -> None:
        """Initialise a toggle for fine-grained module features."""
        self._feature_id = feature_id
        self._module = module

        hass_language: str | None = None
        hass_obj = getattr(coordinator, 'hass', None)
        config_obj = getattr(hass_obj, 'config', None) if hass_obj else None
        if config_obj is not None:
            hass_language = getattr(config_obj, 'language', None)

        if module == MODULE_GROOMING:
            display_name = translated_grooming_label(
                hass_language, f"feature_{feature_id}"
            )
        else:
            display_name = feature_name

        self._feature_name = display_name

        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            feature_id,
            icon=icon,
            initial_state=True,
        )
        self._attr_name = f"{dog_name} {display_name}"

    @property
    def extra_state_attributes(self) -> JSONMutableMapping:
        """Return feature-specific attributes."""
        feature_attrs = ensure_json_mapping(super().extra_state_attributes)
        feature_attrs.update(
            {
                'feature_id': self._feature_id,
                'parent_module': self._module,
                'feature_name': self._feature_name,
            }
        )
        return cast(JSONMutableMapping, normalize_value(feature_attrs))

    async def _async_set_state(self, state: bool) -> None:
        """Set feature state with module-specific handling."""
        if self.hass is None:
            _LOGGER.debug(
                'Skipping feature state update for %s; hass not available',
                self._feature_id,
            )
            return

        _LOGGER.info(
            '%s %s for %s (module: %s)',
            'Enabled' if state else 'Disabled',
            self._feature_name,
            self._dog_name,
            self._module,
        )

        # Feature-specific handling
        try:
            if self._feature_id == 'gps_tracking':
                await self._set_gps_tracking(state)
            elif self._feature_id == 'notifications':
                await self._set_notifications(state)
            elif self._feature_id == 'feeding_schedule':
                await self._set_feeding_schedule(state)
            elif self._feature_id == 'health_monitoring':
                await self._set_health_monitoring(state)
            elif self._feature_id == 'medication_reminders':
                await self._set_medication_reminders(state)
            # Add more specific handlers as needed

        except Exception as err:
            _LOGGER.warning(
                'Feature state update failed for %s %s: %s',
                self._dog_name,
                self._feature_name,
                err,
            )

    async def _set_gps_tracking(self, state: bool) -> None:
        """Handle GPS tracking state."""
        try:
            data_manager = self._get_data_manager()

            if data_manager is not None:
                await data_manager.async_set_gps_tracking(self._dog_id, state)

        except Exception as err:
            _LOGGER.warning('GPS tracking update failed: %s', err)

    async def _set_notifications(self, state: bool) -> None:
        """Handle notifications state."""
        await self._async_call_hass_service(
            DOMAIN,
            'configure_alerts',
            {
                'dog_id': self._dog_id,
                'feeding_alerts': state,
                'walk_alerts': state,
                'health_alerts': state,
                'gps_alerts': state,
            },
            blocking=False,
        )

    async def _set_feeding_schedule(self, state: bool) -> None:
        """Handle feeding schedule state."""
        await self._async_call_hass_service(
            DOMAIN,
            'set_feeding_schedule',
            {
                'dog_id': self._dog_id,
                'enabled': state,
            },
            blocking=False,
        )

    async def _set_health_monitoring(self, state: bool) -> None:
        """Handle health monitoring state."""
        await self._async_call_hass_service(
            DOMAIN,
            'configure_health_monitoring',
            {
                'dog_id': self._dog_id,
                'enabled': state,
            },
            blocking=False,
        )

    async def _set_medication_reminders(self, state: bool) -> None:
        """Handle medication reminders state."""
        await self._async_call_hass_service(
            DOMAIN,
            'configure_medication_reminders',
            {
                'dog_id': self._dog_id,
                'enabled': state,
            },
            blocking=False,
        )
