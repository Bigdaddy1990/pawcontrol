"""Button platform for Paw Control integration."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    CONF_DOGS,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_MODULES,
    MODULE_WALK,
    MODULE_FEEDING,
    MODULE_HEALTH,
    MODULE_GROOMING,
    MODULE_TRAINING,
    MODULE_NOTIFICATIONS,
    SERVICE_GPS_START_WALK,
    SERVICE_GPS_END_WALK,
    SERVICE_NOTIFY_TEST,
    SERVICE_SEND_MEDICATION_REMINDER,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control button entities."""
    # Safe coordinator access with error handling
    try:
        domain_data = hass.data.get(DOMAIN, {})
        entry_data = domain_data.get(entry.entry_id, {})
        coordinator = entry_data.get("coordinator")
        
        if not coordinator:
            _LOGGER.warning("Coordinator not available for button platform")
            return
            
    except Exception as exc:
        _LOGGER.error("Failed to get coordinator for button platform: %s", exc)
        return

    entities = []
    dogs = entry.options.get(CONF_DOGS, [])

    for dog in dogs:
        dog_id = dog.get(CONF_DOG_ID)
        if not dog_id:
            continue

        dog_name = dog.get(CONF_DOG_NAME, dog_id)
        modules = dog.get(CONF_DOG_MODULES, {})

        # Walk module buttons
        if modules.get(MODULE_WALK):
            entities.extend([
                StartWalkButton(hass, coordinator, dog_id, dog_name),
                EndWalkButton(hass, coordinator, dog_id, dog_name),
            ])

        # Feeding module buttons
        if modules.get(MODULE_FEEDING):
            entities.extend([
                MarkFedButton(hass, coordinator, dog_id, dog_name),
                FeedBreakfastButton(hass, coordinator, dog_id, dog_name),
                FeedLunchButton(hass, coordinator, dog_id, dog_name),
                FeedDinnerButton(hass, coordinator, dog_id, dog_name),
                FeedSnackButton(hass, coordinator, dog_id, dog_name),
            ])

        # Health module buttons
        if modules.get(MODULE_HEALTH):
            entities.extend([
                MarkMedicationButton(hass, coordinator, dog_id, dog_name),
                LogHealthDataButton(hass, coordinator, dog_id, dog_name),
                VetVisitButton(hass, coordinator, dog_id, dog_name),
            ])

        # Grooming module buttons
        if modules.get(MODULE_GROOMING):
            entities.extend([
                StartGroomingButton(hass, coordinator, dog_id, dog_name),
            ])

        # Training module buttons
        if modules.get(MODULE_TRAINING):
            entities.extend([
                StartTrainingButton(hass, coordinator, dog_id, dog_name),
            ])

        # Notification test button
        if modules.get(MODULE_NOTIFICATIONS):
            entities.append(NotifyTestButton(hass, coordinator, dog_id, dog_name))

        # Always add poop tracking and play buttons
        entities.extend([
            LogPoopButton(hass, coordinator, dog_id, dog_name),
            StartPlayButton(hass, coordinator, dog_id, dog_name),
        ])

    # Global system buttons
    entities.extend([
        DailyResetButton(hass, coordinator),
        SystemHealthCheckButton(hass, coordinator),
        GenerateReportButton(hass, coordinator),
    ])

    if entities:
        async_add_entities(entities, True)


class PawControlButtonBase(ButtonEntity):
    """Base class for Paw Control buttons."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: Any,
        dog_id: str,
        dog_name: str,
        button_type: str,
        name: str,
        icon: str,
    ) -> None:
        """Initialize the button."""
        self.hass = hass
        self.coordinator = coordinator
        self._dog_id = dog_id
        self._dog_name = dog_name
        self._button_type = button_type

        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = f"{DOMAIN}.{dog_id}.button.{button_type}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dog_id)},
            name=f"🐕 {dog_name}",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.0.15",
        )

    @property
    def dog_data(self) -> dict:
        """Get dog data from coordinator."""
        if self.coordinator:
            return self.coordinator.get_dog_data(self._dog_id)
        return {}


# Walk-related buttons
class StartWalkButton(PawControlButtonBase):
    """Button to start a walk."""

    def __init__(self, hass: HomeAssistant, coordinator: Any, dog_id: str, dog_name: str):
        """Initialize the button."""
        super().__init__(
            hass, coordinator, dog_id, dog_name, "start_walk", "Gassi starten", "mdi:dog-side"
        )

    async def async_press(self) -> None:
        """Handle button press."""
        try:
            if self.coordinator:
                await self.coordinator.start_walk(self._dog_id, "button")
            else:
                await self.hass.services.async_call(
                    DOMAIN,
                    SERVICE_GPS_START_WALK,
                    {"dog_id": self._dog_id, "walk_type": "manual"},
                    blocking=False,
                )
        except Exception as exc:
            _LOGGER.error("Failed to start walk for %s: %s", self._dog_id, exc)


class EndWalkButton(PawControlButtonBase):
    """Button to end a walk."""

    def __init__(self, hass: HomeAssistant, coordinator: Any, dog_id: str, dog_name: str):
        """Initialize the button."""
        super().__init__(
            hass, coordinator, dog_id, dog_name, "end_walk", "Gassi beenden", "mdi:home"
        )

    async def async_press(self) -> None:
        """Handle button press."""
        try:
            if self.coordinator:
                await self.coordinator.end_walk(self._dog_id, "button")
            else:
                await self.hass.services.async_call(
                    DOMAIN,
                    SERVICE_GPS_END_WALK,
                    {"dog_id": self._dog_id, "notes": "Beendet über Button"},
                    blocking=False,
                )
        except Exception as exc:
            _LOGGER.error("Failed to end walk for %s: %s", self._dog_id, exc)


# Feeding-related buttons
class MarkFedButton(PawControlButtonBase):
    """Button to mark dog as fed (generic)."""

    def __init__(self, hass: HomeAssistant, coordinator: Any, dog_id: str, dog_name: str):
        """Initialize the button."""
        super().__init__(
            hass, coordinator, dog_id, dog_name, "mark_fed", "Gefüttert", "mdi:food"
        )

    async def async_press(self) -> None:
        """Handle button press."""
        try:
            if self.coordinator:
                await self.coordinator.feed_dog(self._dog_id, "generic", 0, "unknown")
        except Exception as exc:
            _LOGGER.error("Failed to mark fed for %s: %s", self._dog_id, exc)


class FeedBreakfastButton(PawControlButtonBase):
    """Button to feed breakfast."""

    def __init__(self, hass: HomeAssistant, coordinator: Any, dog_id: str, dog_name: str):
        """Initialize the button."""
        super().__init__(
            hass, coordinator, dog_id, dog_name, "feed_breakfast", "Frühstück", "mdi:weather-sunny"
        )

    async def async_press(self) -> None:
        """Handle button press."""
        try:
            if self.coordinator:
                await self.coordinator.feed_dog(self._dog_id, "breakfast", 150, "dry")
        except Exception as exc:
            _LOGGER.error("Failed to feed breakfast for %s: %s", self._dog_id, exc)


class FeedLunchButton(PawControlButtonBase):
    """Button to feed lunch."""

    def __init__(self, hass: HomeAssistant, coordinator: Any, dog_id: str, dog_name: str):
        """Initialize the button."""
        super().__init__(
            hass, coordinator, dog_id, dog_name, "feed_lunch", "Mittag", "mdi:weather-partly-cloudy"
        )

    async def async_press(self) -> None:
        """Handle button press."""
        try:
            if self.coordinator:
                await self.coordinator.feed_dog(self._dog_id, "lunch", 100, "dry")
        except Exception as exc:
            _LOGGER.error("Failed to feed lunch for %s: %s", self._dog_id, exc)


class FeedDinnerButton(PawControlButtonBase):
    """Button to feed dinner."""

    def __init__(self, hass: HomeAssistant, coordinator: Any, dog_id: str, dog_name: str):
        """Initialize the button."""
        super().__init__(
            hass, coordinator, dog_id, dog_name, "feed_dinner", "Abendessen", "mdi:weather-night"
        )

    async def async_press(self) -> None:
        """Handle button press."""
        try:
            if self.coordinator:
                await self.coordinator.feed_dog(self._dog_id, "dinner", 150, "dry")
        except Exception as exc:
            _LOGGER.error("Failed to feed dinner for %s: %s", self._dog_id, exc)


class FeedSnackButton(PawControlButtonBase):
    """Button to feed snack."""

    def __init__(self, hass: HomeAssistant, coordinator: Any, dog_id: str, dog_name: str):
        """Initialize the button."""
        super().__init__(
            hass, coordinator, dog_id, dog_name, "feed_snack", "Leckerli", "mdi:candy"
        )

    async def async_press(self) -> None:
        """Handle button press."""
        try:
            if self.coordinator:
                await self.coordinator.feed_dog(self._dog_id, "snack", 25, "treat")
        except Exception as exc:
            _LOGGER.error("Failed to feed snack for %s: %s", self._dog_id, exc)


# Health-related buttons
class MarkMedicationButton(PawControlButtonBase):
    """Button to mark medication as given."""

    def __init__(self, hass: HomeAssistant, coordinator: Any, dog_id: str, dog_name: str):
        """Initialize the button."""
        super().__init__(
            hass, coordinator, dog_id, dog_name, "mark_medication", "Medikament gegeben", "mdi:pill"
        )

    async def async_press(self) -> None:
        """Handle button press."""
        try:
            if self.coordinator:
                await self.coordinator.log_medication(self._dog_id, "Manual Entry", "1 dose")
            else:
                await self.hass.services.async_call(
                    DOMAIN,
                    SERVICE_SEND_MEDICATION_REMINDER,
                    {"dog_id": self._dog_id, "notes": "Markiert als gegeben"},
                    blocking=False,
                )
        except Exception as exc:
            _LOGGER.error("Failed to mark medication for %s: %s", self._dog_id, exc)


class LogHealthDataButton(PawControlButtonBase):
    """Button to log health data."""

    def __init__(self, hass: HomeAssistant, coordinator: Any, dog_id: str, dog_name: str):
        """Initialize the button."""
        super().__init__(
            hass, coordinator, dog_id, dog_name, "log_health", "Gesundheit erfassen", "mdi:heart-pulse"
        )

    async def async_press(self) -> None:
        """Handle button press."""
        try:
            if self.coordinator:
                await self.coordinator.log_health_data(self._dog_id, None, "Routine check")
        except Exception as exc:
            _LOGGER.error("Failed to log health data for %s: %s", self._dog_id, exc)


class VetVisitButton(PawControlButtonBase):
    """Button to mark vet visit."""

    def __init__(self, hass: HomeAssistant, coordinator: Any, dog_id: str, dog_name: str):
        """Initialize the button."""
        super().__init__(
            hass, coordinator, dog_id, dog_name, "vet_visit", "Tierarzt-Besuch", "mdi:medical-bag"
        )

    async def async_press(self) -> None:
        """Handle button press."""
        try:
            if self.coordinator:
                await self.coordinator.log_health_data(self._dog_id, None, "Veterinary visit")
        except Exception as exc:
            _LOGGER.error("Failed to log vet visit for %s: %s", self._dog_id, exc)


# Grooming-related buttons
class StartGroomingButton(PawControlButtonBase):
    """Button to start grooming session."""

    def __init__(self, hass: HomeAssistant, coordinator: Any, dog_id: str, dog_name: str):
        """Initialize the button."""
        super().__init__(
            hass, coordinator, dog_id, dog_name, "start_grooming", "Pflege starten", "mdi:content-cut"
        )

    async def async_press(self) -> None:
        """Handle button press."""
        try:
            if self.coordinator:
                await self.coordinator.start_grooming(self._dog_id, "general", "Started via button")
        except Exception as exc:
            _LOGGER.error("Failed to start grooming for %s: %s", self._dog_id, exc)


# Training-related buttons
class StartTrainingButton(PawControlButtonBase):
    """Button to start training session."""

    def __init__(self, hass: HomeAssistant, coordinator: Any, dog_id: str, dog_name: str):
        """Initialize the button."""
        super().__init__(
            hass, coordinator, dog_id, dog_name, "start_training", "Training starten", "mdi:school"
        )

    async def async_press(self) -> None:
        """Handle button press."""
        try:
            if self.coordinator:
                await self.coordinator.log_training(self._dog_id, "general", 15, "Started via button")
        except Exception as exc:
            _LOGGER.error("Failed to start training for %s: %s", self._dog_id, exc)


# Activity buttons
class LogPoopButton(PawControlButtonBase):
    """Button to log poop."""

    def __init__(self, hass: HomeAssistant, coordinator: Any, dog_id: str, dog_name: str):
        """Initialize the button."""
        super().__init__(
            hass, coordinator, dog_id, dog_name, "log_poop", "Häufchen protokollieren", "mdi:emoticon-poop"
        )

    async def async_press(self) -> None:
        """Handle button press."""
        try:
            if self.coordinator:
                await self.coordinator.log_poop(self._dog_id)
        except Exception as exc:
            _LOGGER.error("Failed to log poop for %s: %s", self._dog_id, exc)


class StartPlayButton(PawControlButtonBase):
    """Button to start play session."""

    def __init__(self, hass: HomeAssistant, coordinator: Any, dog_id: str, dog_name: str):
        """Initialize the button."""
        super().__init__(
            hass, coordinator, dog_id, dog_name, "start_play", "Spielen starten", "mdi:tennis"
        )

    async def async_press(self) -> None:
        """Handle button press."""
        try:
            if self.coordinator:
                await self.coordinator.log_play_session(self._dog_id, 10, "medium")
        except Exception as exc:
            _LOGGER.error("Failed to start play for %s: %s", self._dog_id, exc)


# Notification button
class NotifyTestButton(PawControlButtonBase):
    """Button to test notifications."""

    def __init__(self, hass: HomeAssistant, coordinator: Any, dog_id: str, dog_name: str):
        """Initialize the button."""
        super().__init__(
            hass, coordinator, dog_id, dog_name, "notify_test", "Benachrichtigung testen", "mdi:bell-ring"
        )

    async def async_press(self) -> None:
        """Handle button press."""
        try:
            await self.hass.services.async_call(
                DOMAIN,
                SERVICE_NOTIFY_TEST,
                {},
                blocking=False,
            )
        except Exception as exc:
            _LOGGER.error("Failed to test notification: %s", exc)


# Global system buttons
class GlobalButtonBase(ButtonEntity):
    """Base class for global system buttons."""

    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, coordinator: Any, button_type: str, name: str, icon: str):
        """Initialize the button."""
        self.hass = hass
        self.coordinator = coordinator
        self._button_type = button_type

        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = f"{DOMAIN}.global.button.{button_type}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.0.15",
        )


class DailyResetButton(GlobalButtonBase):
    """Button to trigger daily reset."""

    def __init__(self, hass: HomeAssistant, coordinator: Any):
        """Initialize the button."""
        super().__init__(hass, coordinator, "daily_reset", "Täglicher Reset", "mdi:restart")

    async def async_press(self) -> None:
        """Handle button press."""
        try:
            if self.coordinator:
                await self.coordinator.reset_daily_counters()
                _LOGGER.info("Daily reset completed via button")
            else:
                _LOGGER.warning("Coordinator not available for daily reset")
        except Exception as exc:
            _LOGGER.error("Failed to perform daily reset: %s", exc)


class SystemHealthCheckButton(GlobalButtonBase):
    """Button to perform system health check."""

    def __init__(self, hass: HomeAssistant, coordinator: Any):
        """Initialize the button."""
        super().__init__(hass, coordinator, "system_health", "System-Check", "mdi:clipboard-check")

    async def async_press(self) -> None:
        """Handle button press."""
        try:
            # Perform basic system health checks
            domain_data = self.hass.data.get(DOMAIN, {})
            entry_count = len(domain_data)
            
            if self.coordinator:
                dog_count = len(self.coordinator.get_all_dog_ids())
                _LOGGER.info("System health check: %d entries, %d dogs configured", entry_count, dog_count)
            else:
                _LOGGER.warning("Coordinator not available for health check")
                
        except Exception as exc:
            _LOGGER.error("Failed to perform system health check: %s", exc)


class GenerateReportButton(GlobalButtonBase):
    """Button to generate system report."""

    def __init__(self, hass: HomeAssistant, coordinator: Any):
        """Initialize the button."""
        super().__init__(hass, coordinator, "generate_report", "Report erstellen", "mdi:file-document")

    async def async_press(self) -> None:
        """Handle button press."""
        try:
            if self.coordinator:
                # Generate basic report data
                dog_ids = self.coordinator.get_all_dog_ids()
                report_data = {}
                
                for dog_id in dog_ids:
                    dog_data = self.coordinator.get_dog_data(dog_id)
                    report_data[dog_id] = {
                        "walks_today": dog_data.get("walk", {}).get("walks_today", 0),
                        "feeding_count": sum(dog_data.get("feeding", {}).get("feedings_today", {}).values()),
                        "activity_level": dog_data.get("activity", {}).get("activity_level", "unknown"),
                    }
                
                _LOGGER.info("Generated report for %d dogs: %s", len(dog_ids), report_data)
            else:
                _LOGGER.warning("Coordinator not available for report generation")
                
        except Exception as exc:
            _LOGGER.error("Failed to generate report: %s", exc)
