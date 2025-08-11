"""Notification router for Paw Control integration."""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional

from homeassistant.components.notify import DOMAIN as NOTIFY_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from ..const import (
    DOMAIN,
    CONF_NOTIFICATIONS,
    CONF_NOTIFY_FALLBACK,
    CONF_PERSON_ENTITIES,
    CONF_SOURCES,
    CONF_QUIET_HOURS,
    CONF_QUIET_START,
    CONF_QUIET_END,
    CONF_REMINDER_REPEAT,
    CONF_SNOOZE_MIN,
)

_LOGGER = logging.getLogger(__name__)


class NotificationRouter:
    """Handle intelligent notification routing."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize notification router."""
        self.hass = hass
        self.entry = entry
        self._active_notifications: Dict[str, Dict[str, Any]] = {}
        self._snoozed_notifications: Dict[str, datetime] = {}

    async def send_notification(
        self,
        title: str,
        message: str,
        dog_id: Optional[str] = None,
        category: str = "general",
        actions: Optional[List[Dict[str, str]]] = None,
        priority: str = "normal",
        tag: Optional[str] = None,
    ) -> bool:
        """Send notification with intelligent routing."""
        
        # Check quiet hours
        if not self._should_send_now(priority):
            _LOGGER.debug(f"Notification delayed due to quiet hours: {title}")
            # Schedule for later
            await self._schedule_notification(
                title, message, dog_id, category, actions, priority, tag
            )
            return False
        
        # Check if snoozed
        if tag and tag in self._snoozed_notifications:
            if dt_util.now() < self._snoozed_notifications[tag]:
                _LOGGER.debug(f"Notification snoozed: {tag}")
                return False
        
        # Get target devices
        targets = await self._get_notification_targets()
        
        if not targets:
            _LOGGER.warning("No notification targets available")
            return False
        
        # Build notification data
        notification_data = self._build_notification_data(
            title, message, dog_id, category, actions, tag
        )
        
        # Send to all targets
        success = False
        for target in targets:
            try:
                await self.hass.services.async_call(
                    NOTIFY_DOMAIN,
                    target,
                    notification_data,
                    blocking=False,
                )
                success = True
                _LOGGER.debug(f"Notification sent to {target}")
            except Exception as err:
                _LOGGER.error(f"Failed to send notification to {target}: {err}")
        
        # Track active notification
        if tag and success:
            self._active_notifications[tag] = {
                "title": title,
                "message": message,
                "sent_at": dt_util.now(),
                "dog_id": dog_id,
                "category": category,
            }
        
        return success

    async def handle_notification_action(
        self,
        action: str,
        tag: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Handle notification action response."""
        _LOGGER.info(f"Handling notification action: {action} for tag: {tag}")
        
        if action == "SNOOZE":
            # Snooze notification
            snooze_min = self.entry.options.get(CONF_NOTIFICATIONS, {}).get(
                CONF_SNOOZE_MIN, 15
            )
            self._snoozed_notifications[tag] = dt_util.now() + timedelta(
                minutes=snooze_min
            )
            _LOGGER.info(f"Notification {tag} snoozed for {snooze_min} minutes")
            
            # Clear notification on all devices
            await self._clear_notification(tag)
            
        elif action == "DISMISS":
            # Remove from active and snoozed
            self._active_notifications.pop(tag, None)
            self._snoozed_notifications.pop(tag, None)
            
            # Clear notification on all devices
            await self._clear_notification(tag)
            
        elif action == "CONFIRM":
            # Mark as confirmed and clear
            self._active_notifications.pop(tag, None)
            await self._clear_notification(tag)
            
            # Fire event for other components to handle
            self.hass.bus.async_fire(
                f"{DOMAIN}_notification_confirmed",
                {"tag": tag, "data": data}
            )

    def _should_send_now(self, priority: str) -> bool:
        """Check if notification should be sent now based on quiet hours."""
        if priority == "emergency":
            return True
        
        quiet_hours = self.entry.options.get(CONF_NOTIFICATIONS, {}).get(
            CONF_QUIET_HOURS, {}
        )
        
        if not quiet_hours:
            return True
        
        quiet_start = quiet_hours.get(CONF_QUIET_START)
        quiet_end = quiet_hours.get(CONF_QUIET_END)
        
        if not quiet_start or not quiet_end:
            return True
        
        try:
            # Parse time strings
            start_time = time.fromisoformat(quiet_start)
            end_time = time.fromisoformat(quiet_end)
            current_time = dt_util.now().time()
            
            # Check if currently in quiet hours
            if start_time <= end_time:
                # Quiet hours don't cross midnight
                return not (start_time <= current_time <= end_time)
            else:
                # Quiet hours cross midnight
                return not (current_time >= start_time or current_time <= end_time)
                
        except ValueError as err:
            _LOGGER.error(f"Invalid quiet hours configuration: {err}")
            return True

    async def _get_notification_targets(self) -> List[str]:
        """Get list of notification targets based on presence and configuration."""
        targets = []
        
        # Check for person-based notifications
        person_entities = self.entry.options.get(CONF_SOURCES, {}).get(
            CONF_PERSON_ENTITIES, []
        )
        
        for person_entity in person_entities:
            state = self.hass.states.get(person_entity)
            if state and state.state == "home":
                # Person is home, find their notify service
                # Entity IDs occasionally include additional dots beyond the
                # ``domain.object_id`` separator (e.g. ``person.john.doe``). A
                # naive ``split('.')`` would return only ``john`` and we'd build
                # the service name ``mobile_app_john`` which doesn't exist. By
                # splitting just once we keep the full identifier (``john.doe``)
                # and then normalize any remaining dots to underscores so
                # ``notify.mobile_app_john_doe`` remains intact.
                person_name = person_entity.split(".", 1)[-1].replace(".", "_")
                notify_service = f"mobile_app_{person_name}"

                # Check if service exists
                if self.hass.services.has_service(NOTIFY_DOMAIN, notify_service):
                    targets.append(notify_service)
                    _LOGGER.debug(
                        f"Added notification target for {person_name} (home)"
                    )
        
        # If no one home or no person entities, use fallback
        if not targets:
            fallback = self.entry.options.get(CONF_NOTIFICATIONS, {}).get(
                CONF_NOTIFY_FALLBACK
            )
            
            if fallback:
                # Extract the service name from the entity ID. ``notify``
                # services may contain additional dots after the domain portion
                # (e.g. ``notify.mobile_app.pixel_7``). A simple
                # ``split('.')`` call would drop everything after the first dot
                # and produce an invalid service name. Using ``split('.', 1)``
                # and taking the last element preserves the entire service
                # identifier while also handling values without a domain
                # prefix, ensuring we don't misroute the notification.
                service = fallback.split(".", 1)[-1]

                if self.hass.services.has_service(NOTIFY_DOMAIN, service):
                    targets.append(service)
                    _LOGGER.debug(
                        f"Using fallback notification target: {service}"
                    )
        
        # If still no targets, try to find any mobile_app service
        if not targets:
            services = self.hass.services.async_services().get(NOTIFY_DOMAIN, {})
            for service_name in services:
                if service_name.startswith("mobile_app_"):
                    targets.append(service_name)
                    _LOGGER.debug(f"Found mobile app service: {service_name}")
                    break
        
        return targets

    def _build_notification_data(
        self,
        title: str,
        message: str,
        dog_id: Optional[str],
        category: str,
        actions: Optional[List[Dict[str, str]]],
        tag: Optional[str],
    ) -> Dict[str, Any]:
        """Build notification data payload."""
        data = {
            "title": title,
            "message": message,
            "data": {
                "push": {
                    "sound": {
                        "name": "default",
                        "critical": 0,
                        "volume": 0.5,
                    }
                },
                "tag": tag or f"{DOMAIN}_{category}_{dog_id or 'general'}",
                "group": f"{DOMAIN}_{category}",
                "importance": "default",
                "channel": DOMAIN,
                "clickAction": f"/{DOMAIN}",
            }
        }
        
        # Add actions if provided
        if actions:
            data["data"]["actions"] = actions
        
        # Add dog identifier if specified
        if dog_id:
            data["data"]["dog_id"] = dog_id
        
        # Add icon
        data["data"]["icon"] = "mdi:dog"
        
        # Add color based on category
        color_map = {
            "feeding": "#4CAF50",
            "walk": "#2196F3",
            "health": "#FF9800",
            "emergency": "#F44336",
            "grooming": "#9C27B0",
            "training": "#00BCD4",
            "general": "#607D8B",
        }
        data["data"]["color"] = color_map.get(category, "#607D8B")
        
        return data

    async def _clear_notification(self, tag: str) -> None:
        """Clear notification on all devices."""
        targets = await self._get_notification_targets()
        
        clear_data = {
            "message": "clear_notification",
            "data": {
                "tag": tag,
            }
        }
        
        for target in targets:
            try:
                await self.hass.services.async_call(
                    NOTIFY_DOMAIN,
                    target,
                    clear_data,
                    blocking=False,
                )
            except Exception as err:
                _LOGGER.error(f"Failed to clear notification on {target}: {err}")

    async def _schedule_notification(
        self,
        title: str,
        message: str,
        dog_id: Optional[str],
        category: str,
        actions: Optional[List[Dict[str, str]]],
        priority: str,
        tag: Optional[str],
    ) -> None:
        """Schedule notification for later delivery."""
        # This would typically use async_track_time_change or similar
        # For now, we'll just log the intent
        _LOGGER.info(
            f"Would schedule notification '{title}' for delivery after quiet hours"
        )

    async def send_reminder(
        self,
        reminder_type: str,
        dog_id: str,
        dog_name: str,
        additional_info: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Send a reminder notification for a specific type."""
        
        # Build reminder message based on type
        if reminder_type == "feeding":
            meal_type = additional_info.get("meal_type", "meal") if additional_info else "meal"
            title = f"🍽️ {dog_name} - Feeding Time"
            message = f"Time for {dog_name}'s {meal_type}!"
            actions = [
                {
                    "action": "FEED_CONFIRM",
                    "title": "Fed ✅",
                },
                {
                    "action": "SNOOZE",
                    "title": "Later ⏰",
                },
            ]
            category = "feeding"
            
        elif reminder_type == "walk":
            title = f"🚶 {dog_name} - Walk Time"
            message = f"{dog_name} needs a walk!"
            actions = [
                {
                    "action": "WALK_START",
                    "title": "Start Walk 🐕",
                },
                {
                    "action": "SNOOZE",
                    "title": "Later ⏰",
                },
            ]
            category = "walk"
            
        elif reminder_type == "medication":
            med_name = additional_info.get("medication", "medication") if additional_info else "medication"
            title = f"💊 {dog_name} - Medication"
            message = f"Time to give {dog_name} their {med_name}"
            actions = [
                {
                    "action": "MED_CONFIRM",
                    "title": "Given ✅",
                },
                {
                    "action": "SNOOZE",
                    "title": "Later ⏰",
                },
            ]
            category = "health"
            
        elif reminder_type == "grooming":
            title = f"✂️ {dog_name} - Grooming Due"
            message = f"{dog_name} needs grooming!"
            actions = [
                {
                    "action": "GROOM_START",
                    "title": "Start ✅",
                },
                {
                    "action": "SNOOZE",
                    "title": "Tomorrow 📅",
                },
            ]
            category = "grooming"
            
        else:
            title = f"🐕 {dog_name} - Reminder"
            message = f"Reminder for {dog_name}"
            actions = None
            category = "general"
        
        tag = f"{DOMAIN}_{reminder_type}_{dog_id}"
        
        return await self.send_notification(
            title=title,
            message=message,
            dog_id=dog_id,
            category=category,
            actions=actions,
            priority="normal",
            tag=tag,
        )

    def get_active_notifications(self) -> Dict[str, Dict[str, Any]]:
        """Get all active notifications."""
        return self._active_notifications.copy()

    def clear_all_notifications(self) -> None:
        """Clear all active and snoozed notifications."""
        self._active_notifications.clear()
        self._snoozed_notifications.clear()
