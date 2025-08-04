"""Automation system for Paw Control integration - SMART DOG CARE - REPARIERT."""
from __future__ import annotations

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable

from homeassistant.core import HomeAssistant, callback, Event, State
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.template import Template

from .const import (
    DOMAIN,
    CONF_DOG_NAME,
    ICONS,
    FEEDING_TYPES,
    MEAL_TYPES,
    STATUS_MESSAGES,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control automations based on a config entry."""
    dog_name = config_entry.data[CONF_DOG_NAME]
    
    # Create automation manager
    automation_manager = PawControlAutomationManager(hass, config_entry, dog_name)
    
    # Initialize all automations
    await automation_manager.async_setup()
    
    # Register automation manager as a single entity for management
    async_add_entities([automation_manager], True)


class PawControlAutomationManager(RestoreEntity):
    """Central automation manager for the PawControl."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        dog_name: str,
    ) -> None:
        """Initialize the automation manager."""
        self.hass = hass
        self._config_entry = config_entry
        self._dog_name = dog_name
        self._attr_unique_id = f"{DOMAIN}_{dog_name}_automation_manager"
        self._attr_name = f"{dog_name.title()} Automation Manager"
        self._attr_icon = "mdi:robot"
        
        # Track all automation listeners for cleanup
        self._listeners: List[Callable[[], None]] = []
        self._automation_registry: Dict[str, Dict[str, Any]] = {}
        
        # Automation state tracking
        self._feeding_automation_active = True
        self._activity_automation_active = True
        self._health_automation_active = True
        self._emergency_automation_active = True
        
        # Statistics
        self._automation_stats = {
            "total_triggers": 0,
            "feeding_triggers": 0,
            "activity_triggers": 0,
            "health_triggers": 0,
            "emergency_triggers": 0,
            "last_trigger": None,
        }

    async def async_setup(self) -> None:
        """Set up all automations."""
        try:
            _LOGGER.info("Setting up PawControl automations for %s", self._dog_name)
            
            # Setup different automation categories
            await self._setup_feeding_automations()
            await self._setup_activity_automations()
            await self._setup_health_automations()
            await self._setup_emergency_automations()
            await self._setup_visitor_automations()
            await self._setup_maintenance_automations()
            
            # Setup periodic checks
            self._setup_periodic_automations()
            
            _LOGGER.info("Successfully set up %d automations for %s", 
                        len(self._automation_registry), self._dog_name)
            
        except Exception as e:
            _LOGGER.error("Error setting up automations for %s: %s", self._dog_name, e)
            raise

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        
        # Restore previous state
        if (old_state := await self.async_get_last_state()) is not None:
            if old_state.attributes:
                self._automation_stats = old_state.attributes.get("automation_stats", self._automation_stats)

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed."""
        # Remove all automation listeners
        for remove_listener in self._listeners:
            try:
                remove_listener()
            except Exception as e:
                _LOGGER.warning("Error removing automation listener: %s", e)
        self._listeners.clear()
        
        _LOGGER.info("Cleaned up %d automation listeners for %s", 
                    len(self._listeners), self._dog_name)
        
        await super().async_will_remove_from_hass()

    @property
    def state(self) -> str:
        """Return the state of the automation manager."""
        active_count = sum([
            self._feeding_automation_active,
            self._activity_automation_active,
            self._health_automation_active,
            self._emergency_automation_active,
        ])
        
        if active_count == 4:
            return "all_active"
        elif active_count > 0:
            return "partially_active"
        else:
            return "inactive"

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return extra state attributes."""
        return {
            "automation_registry": list(self._automation_registry.keys()),
            "total_automations": len(self._automation_registry),
            "feeding_automation_active": self._feeding_automation_active,
            "activity_automation_active": self._activity_automation_active,
            "health_automation_active": self._health_automation_active,
            "emergency_automation_active": self._emergency_automation_active,
            "automation_stats": self._automation_stats,
            "last_updated": datetime.now().isoformat(),
        }

    async def _setup_feeding_automations(self) -> None:
        """Set up feeding-related automations."""
        
        def create_feeding_automation(meal_type: str):
            @callback
            def feeding_reminder_trigger(event: Event) -> None:
                """Trigger feeding reminder automation."""
                self.hass.async_create_task(
                    self._handle_feeding_reminder(meal_type, event)
                )
            return feeding_reminder_trigger
        
        # Set up feeding reminders for each meal
        for meal in FEEDING_TYPES:
            automation_id = f"feeding_reminder_{meal}"
            
            # Track scheduled time changes
            time_entity = f"input_datetime.{self._dog_name}_feeding_{meal}_time"
            status_entity = f"input_boolean.{self._dog_name}_feeding_{meal}"
            
            if self.hass.states.get(time_entity) or self.hass.states.get(status_entity):
                # Register automation
                self._automation_registry[automation_id] = {
                    "type": "feeding",
                    "meal_type": meal,
                    "trigger_entities": [time_entity, status_entity],
                    "description": f"Feeding reminder for {MEAL_TYPES.get(meal, meal)}",
                    "active": True,
                }
                
                # Set up state change tracking
                remove_listener = async_track_state_change_event(
                    self.hass, [time_entity, status_entity], 
                    create_feeding_automation(meal)
                )
                self._listeners.append(remove_listener)

    async def _setup_activity_automations(self) -> None:
        """Set up activity-related automations."""
        
        # Automation: Activity milestone celebrations
        activity_counters = [
            f"counter.{self._dog_name}_walk_count",
            f"counter.{self._dog_name}_play_count",
            f"counter.{self._dog_name}_training_count",
        ]
        
        # Filter for existing entities
        existing_counters = [entity for entity in activity_counters if self.hass.states.get(entity)]
        
        if existing_counters:
            @callback
            def activity_milestone_trigger(event: Event) -> None:
                """Trigger activity milestone automation."""
                self.hass.async_create_task(self._handle_activity_milestone(event))
            
            remove_listener = async_track_state_change_event(
                self.hass, existing_counters, activity_milestone_trigger
            )
            self._listeners.append(remove_listener)
            
            self._automation_registry["activity_milestones"] = {
                "type": "activity",
                "trigger_entities": existing_counters,
                "description": "Celebrate activity milestones",
                "active": True,
            }

    async def _setup_health_automations(self) -> None:
        """Set up health-related automations."""
        
        # Automation: Health status changes
        health_entities = [
            f"input_select.{self._dog_name}_health_status",
            f"input_select.{self._dog_name}_mood",
            f"sensor.{self._dog_name}_health_score",
        ]
        
        # Filter for existing entities
        existing_health_entities = [entity for entity in health_entities if self.hass.states.get(entity)]
        
        if existing_health_entities:
            @callback
            def health_status_trigger(event: Event) -> None:
                """Trigger health status automation."""
                self.hass.async_create_task(self._handle_health_status_change(event))
            
            remove_listener = async_track_state_change_event(
                self.hass, existing_health_entities, health_status_trigger
            )
            self._listeners.append(remove_listener)
            
            self._automation_registry["health_monitoring"] = {
                "type": "health",
                "trigger_entities": existing_health_entities,
                "description": "Monitor health status changes",
                "active": True,
            }

    async def _setup_emergency_automations(self) -> None:
        """Set up emergency-related automations."""
        
        # Automation: Emergency mode activation
        emergency_entities = [
            f"input_boolean.{self._dog_name}_emergency_mode",
            f"binary_sensor.{self._dog_name}_needs_attention",
        ]
        
        # Filter for existing entities
        existing_emergency_entities = [entity for entity in emergency_entities if self.hass.states.get(entity)]
        
        if existing_emergency_entities:
            @callback
            def emergency_trigger(event: Event) -> None:
                """Trigger emergency automation."""
                self.hass.async_create_task(self._handle_emergency_activation(event))
            
            remove_listener = async_track_state_change_event(
                self.hass, existing_emergency_entities, emergency_trigger
            )
            self._listeners.append(remove_listener)
            
            self._automation_registry["emergency_response"] = {
                "type": "emergency",
                "trigger_entities": existing_emergency_entities,
                "description": "Emergency response system",
                "active": True,
            }

    async def _setup_visitor_automations(self) -> None:
        """Set up visitor-related automations."""
        
        # Automation: Visitor mode management
        visitor_entities = [
            f"input_boolean.{self._dog_name}_visitor_mode_input",
        ]
        
        # Filter for existing entities
        existing_visitor_entities = [entity for entity in visitor_entities if self.hass.states.get(entity)]
        
        if existing_visitor_entities:
            @callback
            def visitor_mode_trigger(event: Event) -> None:
                """Trigger visitor mode automation."""
                self.hass.async_create_task(self._handle_visitor_mode_change(event))
            
            remove_listener = async_track_state_change_event(
                self.hass, existing_visitor_entities, visitor_mode_trigger
            )
            self._listeners.append(remove_listener)
            
            self._automation_registry["visitor_management"] = {
                "type": "visitor",
                "trigger_entities": existing_visitor_entities,
                "description": "Visitor mode management",
                "active": True,
            }

    async def _setup_maintenance_automations(self) -> None:
        """Set up maintenance-related automations."""
        
        # Automation: Daily summary generation
        @callback
        def daily_summary_trigger(time) -> None:
            """Trigger daily summary automation."""
            self.hass.async_create_task(self._handle_daily_summary())
        
        # Generate daily summary at 23:30
        remove_listener = async_track_time_interval(
            self.hass, daily_summary_trigger, timedelta(days=1)
        )
        self._listeners.append(remove_listener)
        
        self._automation_registry["daily_summary"] = {
            "type": "maintenance",
            "trigger_entities": [],
            "description": "Daily summary generation",
            "active": True,
        }

    def _setup_periodic_automations(self) -> None:
        """Set up periodic check automations."""
        
        # Periodic system health check every 30 minutes
        @callback
        def system_health_check(time) -> None:
            """Periodic system health check."""
            self.hass.async_create_task(self._handle_system_health_check())
        
        remove_listener = async_track_time_interval(
            self.hass, system_health_check, timedelta(minutes=30)
        )
        self._listeners.append(remove_listener)
        
        self._automation_registry["system_health_check"] = {
            "type": "maintenance",
            "trigger_entities": [],
            "description": "Periodic system health monitoring",
            "active": True,
        }

    # AUTOMATION HANDLERS
    
    async def _handle_feeding_reminder(self, meal_type: str, event: Event) -> None:
        """Handle feeding reminder automation."""
        try:
            self._update_stats("feeding_triggers")
            
            # Check if meal is already given
            status_entity = f"input_boolean.{self._dog_name}_feeding_{meal_type}"
            status_state = self.hass.states.get(status_entity)
            
            if status_state and status_state.state == "on":
                # Meal already given, no reminder needed
                return
            
            # Get scheduled time
            time_entity = f"input_datetime.{self._dog_name}_feeding_{meal_type}_time"
            time_state = self.hass.states.get(time_entity)
            
            if not time_state or time_state.state in ["unknown", "unavailable"]:
                return
            
            scheduled_time = time_state.state
            meal_name = MEAL_TYPES.get(meal_type, meal_type)
            
            # Check if it's time for reminder (30 minutes before scheduled time)
            now = datetime.now()
            try:
                scheduled_dt = datetime.strptime(scheduled_time, "%H:%M:%S")
                scheduled_today = now.replace(
                    hour=scheduled_dt.hour, 
                    minute=scheduled_dt.minute, 
                    second=0, 
                    microsecond=0
                )
                
                reminder_time = scheduled_today - timedelta(minutes=30)
                
                # Send reminder if within 5 minutes of reminder time
                time_diff = abs((now - reminder_time).total_seconds())
                
                if time_diff <= 300:  # Within 5 minutes
                    await self._send_feeding_reminder(meal_name, scheduled_time)
                
            except ValueError as e:
                _LOGGER.warning("Error parsing feeding time for %s: %s", meal_type, e)
                
        except Exception as e:
            _LOGGER.error("Error in feeding reminder automation for %s: %s", self._dog_name, e)

    async def _handle_activity_milestone(self, event: Event) -> None:
        """Handle activity milestone automation."""
        try:
            self._update_stats("activity_triggers")
            
            entity_id = event.data.get("entity_id")
            new_state = event.data.get("new_state")
            
            if not new_state:
                return
            
            try:
                count = int(new_state.state)
                
                # Check for milestone achievements (5, 10, 25, 50, 100)
                milestones = [5, 10, 25, 50, 100]
                
                for milestone in milestones:
                    if count == milestone:
                        activity_type = self._extract_activity_type(entity_id)
                        await self._send_milestone_celebration(activity_type, milestone)
                        break
                        
            except ValueError:
                pass  # Not a numeric state
                
        except Exception as e:
            _LOGGER.error("Error in activity milestone automation for %s: %s", self._dog_name, e)

    async def _handle_health_status_change(self, event: Event) -> None:
        """Handle health status change automation."""
        try:
            self._update_stats("health_triggers")
            
            entity_id = event.data.get("entity_id")
            new_state = event.data.get("new_state")
            old_state = event.data.get("old_state")
            
            if not new_state or not old_state:
                return
            
            # Check for health deterioration
            if "health_status" in entity_id:
                await self._handle_health_status_specific_change(new_state.state, old_state.state)
            elif "mood" in entity_id:
                await self._handle_mood_change(new_state.state, old_state.state)
                
        except Exception as e:
            _LOGGER.error("Error in health status automation for %s: %s", self._dog_name, e)

    async def _handle_emergency_activation(self, event: Event) -> None:
        """Handle emergency activation automation."""
        try:
            self._update_stats("emergency_triggers")
            
            new_state = event.data.get("new_state")
            
            if not new_state or new_state.state != "on":
                return
            
            # Emergency activated - immediate response
            await self._execute_emergency_protocol()
            
        except Exception as e:
            _LOGGER.error("Error in emergency activation automation for %s: %s", self._dog_name, e)

    async def _handle_visitor_mode_change(self, event: Event) -> None:
        """Handle visitor mode change automation."""
        try:
            new_state = event.data.get("new_state")
            
            if not new_state:
                return
            
            if new_state.state == "on":
                # Visitor mode activated
                visitor_name = ""
                if new_state.attributes:
                    visitor_name = new_state.attributes.get("visitor_name", "")
                
                await self._send_visitor_mode_notification(True, visitor_name)
            else:
                # Visitor mode deactivated
                await self._send_visitor_mode_notification(False, "")
                
        except Exception as e:
            _LOGGER.error("Error in visitor mode automation for %s: %s", self._dog_name, e)

    async def _handle_daily_summary(self) -> None:
        """Handle daily summary generation."""
        try:
            # Get daily summary data
            summary_sensor = self.hass.states.get(f"sensor.{self._dog_name}_daily_summary")
            
            if summary_sensor:
                summary_text = summary_sensor.state
                await self._send_daily_summary_notification(summary_text)
                
        except Exception as e:
            _LOGGER.error("Error in daily summary automation for %s: %s", self._dog_name, e)

    async def _handle_system_health_check(self) -> None:
        """Handle periodic system health check."""
        try:
            # Simple system health check - verify key entities exist
            key_entities = [
                f"input_boolean.{self._dog_name}_feeding_morning",
                f"input_boolean.{self._dog_name}_outside",
                f"counter.{self._dog_name}_walk_count",
            ]
            
            missing_entities = []
            for entity_id in key_entities:
                if not self.hass.states.get(entity_id):
                    missing_entities.append(entity_id)
            
            if missing_entities:
                await self._send_system_health_alert(missing_entities)
                        
        except Exception as e:
            _LOGGER.error("Error in system health check automation for %s: %s", self._dog_name, e)

    # UTILITY METHODS
    
    def _update_stats(self, stat_type: str) -> None:
        """Update automation statistics."""
        self._automation_stats["total_triggers"] += 1
        self._automation_stats[stat_type] += 1
        self._automation_stats["last_trigger"] = datetime.now().isoformat()

    def _extract_activity_type(self, entity_id: str) -> str:
        """Extract activity type from entity_id."""
        if "walk" in entity_id:
            return "Spaziergang"
        elif "play" in entity_id:
            return "Spielzeit"
        elif "training" in entity_id:
            return "Training"
        else:
            return "Aktivität"

    # NOTIFICATION METHODS
    
    async def _send_feeding_reminder(self, meal_name: str, scheduled_time: str) -> None:
        """Send feeding reminder notification."""
        try:
            if self.hass.services.has_service("persistent_notification", "create"):
                await self.hass.services.async_call(
                    "persistent_notification", "create",
                    {
                        "title": f"🍽️ Fütterung - {self._dog_name.title()}",
                        "message": f"Erinnerung: {meal_name} ist für {scheduled_time[:5]} geplant",
                        "notification_id": f"feeding_reminder_{self._dog_name}_{meal_name.lower()}",
                    }
                )
        except Exception as e:
            _LOGGER.error("Error sending feeding reminder: %s", e)

    async def _send_milestone_celebration(self, activity_type: str, milestone: int) -> None:
        """Send milestone celebration notification."""
        try:
            if self.hass.services.has_service("persistent_notification", "create"):
                await self.hass.services.async_call(
                    "persistent_notification", "create",
                    {
                        "title": f"🏆 Meilenstein - {self._dog_name.title()}",
                        "message": f"Glückwunsch! {milestone}. {activity_type} erreicht! 🎉",
                        "notification_id": f"milestone_{self._dog_name}_{activity_type}_{milestone}",
                    }
                )
        except Exception as e:
            _LOGGER.error("Error sending milestone celebration: %s", e)

    async def _send_visitor_mode_notification(self, activated: bool, visitor_name: str) -> None:
        """Send visitor mode notification."""
        try:
            if self.hass.services.has_service("persistent_notification", "create"):
                status = "aktiviert" if activated else "deaktiviert"
                visitor_text = f" für {visitor_name}" if visitor_name else ""
                
                await self.hass.services.async_call(
                    "persistent_notification", "create",
                    {
                        "title": f"👥 Besuchermodus - {self._dog_name.title()}",
                        "message": f"Besuchermodus {status}{visitor_text}",
                        "notification_id": f"visitor_mode_{self._dog_name}",
                    }
                )
        except Exception as e:
            _LOGGER.error("Error sending visitor mode notification: %s", e)

    async def _send_daily_summary_notification(self, summary_text: str) -> None:
        """Send daily summary notification."""
        try:
            if self.hass.services.has_service("persistent_notification", "create"):
                await self.hass.services.async_call(
                    "persistent_notification", "create",
                    {
                        "title": f"📊 Tagesbericht - {self._dog_name.title()}",
                        "message": summary_text,
                        "notification_id": f"daily_summary_{self._dog_name}",
                    }
                )
        except Exception as e:
            _LOGGER.error("Error sending daily summary notification: %s", e)

    async def _send_system_health_alert(self, missing_entities: List[str]) -> None:
        """Send system health alert."""
        try:
            if self.hass.services.has_service("persistent_notification", "create"):
                await self.hass.services.async_call(
                    "persistent_notification", "create",
                    {
                        "title": f"⚠️ System-Problem - {self._dog_name.title()}",
                        "message": f"Fehlende Entitäten erkannt: {len(missing_entities)} Probleme",
                        "notification_id": f"system_health_{self._dog_name}",
                    }
                )
        except Exception as e:
            _LOGGER.error("Error sending system health alert: %s", e)

    async def _execute_emergency_protocol(self) -> None:
        """Execute emergency protocol."""
        try:
            if self.hass.services.has_service("persistent_notification", "create"):
                await self.hass.services.async_call(
                    "persistent_notification", "create",
                    {
                        "title": f"🚨 NOTFALL - {self._dog_name.title()}",
                        "message": "Notfallprotokoll aktiviert! Sofortige Aufmerksamkeit erforderlich!",
                        "notification_id": f"emergency_{self._dog_name}",
                    }
                )
        except Exception as e:
            _LOGGER.error("Error executing emergency protocol: %s", e)

    async def _handle_health_status_specific_change(self, new_status: str, old_status: str) -> None:
        """Handle specific health status changes."""
        try:
            # Define health status severity levels
            severity_levels = {
                "Ausgezeichnet": 5,
                "Sehr gut": 4,
                "Gut": 3,
                "Normal": 2,
                "Unwohl": 1,
                "Krank": 0,
            }
            
            new_severity = severity_levels.get(new_status, 2)
            old_severity = severity_levels.get(old_status, 2)
            
            # Alert if health deteriorated significantly
            if new_severity < old_severity - 1:
                if self.hass.services.has_service("persistent_notification", "create"):
                    await self.hass.services.async_call(
                        "persistent_notification", "create",
                        {
                            "title": f"🏥 Gesundheitsänderung - {self._dog_name.title()}",
                            "message": f"Gesundheitsstatus von '{old_status}' zu '{new_status}' verschlechtert",
                            "notification_id": f"health_change_{self._dog_name}",
                        }
                    )
        except Exception as e:
            _LOGGER.error("Error handling health status change: %s", e)

    async def _handle_mood_change(self, new_mood: str, old_mood: str) -> None:
        """Handle mood changes."""
        try:
            # Alert for negative mood changes
            negative_moods = ["😟 Traurig", "😠 Ärgerlich", "😰 Ängstlich"]
            
            if new_mood in negative_moods and old_mood not in negative_moods:
                if self.hass.services.has_service("persistent_notification", "create"):
                    await self.hass.services.async_call(
                        "persistent_notification", "create",
                        {
                            "title": f"😟 Stimmungsänderung - {self._dog_name.title()}",
                            "message": f"Stimmung hat sich zu '{new_mood}' geändert - Aufmerksamkeit empfohlen",
                            "notification_id": f"mood_change_{self._dog_name}",
                        }
                    )
        except Exception as e:
            _LOGGER.error("Error handling mood change: %s", e)
