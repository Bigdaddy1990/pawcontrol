from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.script import Script

from .const import (
    DOMAIN,
    CONF_DOG_NAME,
    ICONS,
    ENTITIES,
    FEEDING_TYPES,
    MEAL_TYPES,
    STATUS_MESSAGES,
)
from .utils import register_services

_LOGGER = logging.getLogger(__name__)

# Service names
SERVICE_FEED_DOG = "feed_dog"
SERVICE_WALK_DOG = "walk_dog"
SERVICE_PLAY_WITH_DOG = "play_with_dog"
SERVICE_EMERGENCY_MODE = "activate_emergency_mode"
SERVICE_VISITOR_MODE = "toggle_visitor_mode"
SERVICE_DAILY_RESET = "daily_reset"
SERVICE_HEALTH_CHECK = "perform_health_check"
SERVICE_MEDICATION_GIVEN = "mark_medication_given"
SERVICE_GROOMING_SESSION = "start_grooming_session"
SERVICE_TRAINING_SESSION = "start_training_session"
SERVICE_VET_VISIT = "record_vet_visit"
SERVICE_GENERATE_REPORT = "generate_report"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> None:
    """Set up Paw Control scripts and services."""
    dog_name = config_entry.data[CONF_DOG_NAME]
    
    # Create script manager
    script_manager = PawControlScriptManager(hass, config_entry, dog_name)
    
    # Register all services
    await script_manager.async_setup_services()
    
    _LOGGER.info("Successfully set up Paw Control scripts for %s", dog_name)


class PawControlScriptManager:
    """Manager for Paw Control scripts and services."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        dog_name: str,
    ) -> None:
        """Initialize the script manager."""
        self.hass = hass
        self._config_entry = config_entry
        self._dog_name = dog_name
        
        # Service execution statistics
        self._service_stats = {
            "total_executions": 0,
            "feeding_actions": 0,
            "activity_actions": 0,
            "health_actions": 0,
            "maintenance_actions": 0,
            "last_execution": None,
        }

    async def async_setup_services(self) -> None:
        """Set up all services."""
        try:
            services = {
                SERVICE_FEED_DOG: self._feed_dog_service,
                SERVICE_WALK_DOG: self._walk_dog_service,
                SERVICE_PLAY_WITH_DOG: self._play_with_dog_service,
                SERVICE_TRAINING_SESSION: self._training_session_service,
                SERVICE_HEALTH_CHECK: self._health_check_service,
                SERVICE_MEDICATION_GIVEN: self._medication_given_service,
                SERVICE_VET_VISIT: self._vet_visit_service,
                SERVICE_GROOMING_SESSION: self._grooming_session_service,
                SERVICE_EMERGENCY_MODE: self._emergency_mode_service,
                SERVICE_VISITOR_MODE: self._visitor_mode_service,
                SERVICE_DAILY_RESET: self._daily_reset_service,
                SERVICE_GENERATE_REPORT: self._generate_report_service,
            }

            register_services(self.hass, DOMAIN, services)

            _LOGGER.info(
                "Registered %d services for %s", len(services), self._dog_name
            )

        except Exception as e:
            _LOGGER.error("Error setting up services for %s: %s", self._dog_name, e)
            raise

    # FEEDING SERVICES
    
    async def _feed_dog_service(self, call: ServiceCall) -> None:
        """Service to feed the dog."""
        try:
            self._update_stats("feeding_actions")
            
            # Get meal type from service data
            meal_type = call.data.get("meal_type", "")
            portion_size = call.data.get("portion_size", "normal")
            notes = call.data.get("notes", "")
            
            # If no meal type specified, determine current meal
            if not meal_type:
                meal_type = await self._determine_current_meal()
            
            # Validate meal type
            if meal_type not in FEEDING_TYPES:
                _LOGGER.warning("Invalid meal type: %s", meal_type)
                return
            
            # Execute feeding action
            await self._execute_feeding_action(meal_type, portion_size, notes)
            
            # Send notification
            meal_name = MEAL_TYPES.get(meal_type, meal_type)
            await self._send_notification(
                f"🍽️ Fütterung - {self._dog_name.title()}",
                f"{meal_name} gegeben ({portion_size})",
                f"feeding_completed_{self._dog_name}_{meal_type}"
            )
            
            _LOGGER.info("Fed %s: %s (%s)", self._dog_name, meal_name, portion_size)
            
        except Exception as e:
            _LOGGER.error("Error in feed dog service for %s: %s", self._dog_name, e)

    async def _execute_feeding_action(self, meal_type: str, portion_size: str, notes: str) -> None:
        """Execute the feeding action."""
        try:
            # Mark meal as given
            feeding_entity = f"input_boolean.{self._dog_name}_feeding_{meal_type}"
            await self.hass.services.async_call(
                "input_boolean", "turn_on",
                {"entity_id": feeding_entity}
            )
            
            # Increment feeding counter
            counter_entity = f"counter.{self._dog_name}_feeding_{meal_type}_count"
            await self.hass.services.async_call(
                "counter", "increment",
                {"entity_id": counter_entity}
            )
            
            # Update last feeding time
            last_feeding_entity = f"input_datetime.{self._dog_name}_last_feeding_{meal_type}"
            await self.hass.services.async_call(
                "input_datetime", "set_datetime",
                {
                    "entity_id": last_feeding_entity,
                    "datetime": datetime.now().isoformat()
                }
            )
            
            # Update general last activity
            await self.hass.services.async_call(
                "input_datetime", "set_datetime",
                {
                    "entity_id": f"input_datetime.{self._dog_name}_last_activity",
                    "datetime": datetime.now().isoformat()
                }
            )
            
            # Add notes if provided
            if notes:
                notes_entity = f"input_text.{self._dog_name}_daily_notes"
                current_notes_state = self.hass.states.get(notes_entity)
                current_notes = current_notes_state.state if current_notes_state else ""
                
                timestamp = datetime.now().strftime("%H:%M")
                new_note = f"[{timestamp}] Fütterung {meal_type}: {notes}"
                
                if current_notes:
                    updated_notes = f"{current_notes}\n{new_note}"
                else:
                    updated_notes = new_note
                
                await self.hass.services.async_call(
                    "input_text", "set_value",
                    {
                        "entity_id": notes_entity,
                        "value": updated_notes[:255]  # Limit to max length
                    }
                )
            
        except Exception as e:
            _LOGGER.error("Error executing feeding action: %s", e)
            raise

    async def _determine_current_meal(self) -> str:
        """Determine which meal should be given now."""
        try:
            now = datetime.now()
            hour = now.hour
            
            # Check which meals are already given today
            meals_given = {}
            for meal in FEEDING_TYPES:
                entity_id = f"input_boolean.{self._dog_name}_feeding_{meal}"
                state = self.hass.states.get(entity_id)
                meals_given[meal] = state.state == "on" if state else False
            
            # Determine meal based on time and what's already given
            if hour < 10 and not meals_given.get("morning", False):
                return "morning"
            elif 11 <= hour < 15 and not meals_given.get("lunch", False):
                return "lunch"
            elif 15 <= hour < 20 and not meals_given.get("evening", False):
                return "evening"
            elif not meals_given.get("snack", False):
                return "snack"
            else:
                # Default to next due meal
                for meal in FEEDING_TYPES:
                    if not meals_given.get(meal, False):
                        return meal
                return "morning"  # All meals given, default to morning
                
        except Exception as e:
            _LOGGER.error("Error determining current meal: %s", e)
            return "morning"

    # ACTIVITY SERVICES
    
    async def _walk_dog_service(self, call: ServiceCall) -> None:
        """Service to record a dog walk."""
        try:
            self._update_stats("activity_actions")
            
            duration = call.data.get("duration", 30)  # minutes
            distance = call.data.get("distance", "")  # km
            notes = call.data.get("notes", "")
            weather = call.data.get("weather", "")
            
            await self._execute_walk_action(duration, distance, notes, weather)
            
            # Send notification
            message = f"Spaziergang beendet ({duration} min"
            if distance:
                message += f", {distance} km"
            message += ")"
            
            await self._send_notification(
                f"🚶 Spaziergang - {self._dog_name.title()}",
                message,
                f"walk_completed_{self._dog_name}"
            )
            
            _LOGGER.info("Recorded walk for %s: %d minutes", self._dog_name, duration)
            
        except Exception as e:
            _LOGGER.error("Error in walk dog service for %s: %s", self._dog_name, e)

    async def _execute_walk_action(self, duration: int, distance: str, notes: str, weather: str) -> None:
        """Execute walk action."""
        try:
            # Increment walk counter
            await self.hass.services.async_call(
                "counter", "increment",
                {"entity_id": f"counter.{self._dog_name}_walk_count"}
            )
            
            # Update last walk time
            await self.hass.services.async_call(
                "input_datetime", "set_datetime",
                {
                    "entity_id": f"input_datetime.{self._dog_name}_last_walk",
                    "datetime": datetime.now().isoformat()
                }
            )
            
            # Update last activity
            await self.hass.services.async_call(
                "input_datetime", "set_datetime",
                {
                    "entity_id": f"input_datetime.{self._dog_name}_last_activity",
                    "datetime": datetime.now().isoformat()
                }
            )
            
            # Mark as having been outside and walked today
            await self.hass.services.async_call(
                "input_boolean", "turn_on",
                {"entity_id": f"input_boolean.{self._dog_name}_outside"}
            )
            
            await self.hass.services.async_call(
                "input_boolean", "turn_on",
                {"entity_id": f"input_boolean.{self._dog_name}_walked_today"}
            )
            
            # Update walk duration if entity exists
            if duration:
                duration_entity = f"input_number.{self._dog_name}_daily_walk_duration"
                await self.hass.services.async_call(
                    "input_number", "set_value",
                    {
                        "entity_id": duration_entity,
                        "value": duration
                    }
                )
            
            # Add detailed notes
            await self._add_activity_notes("Spaziergang", {
                "duration": f"{duration} min",
                "distance": distance or "Nicht angegeben",
                "weather": weather or "Nicht angegeben", 
                "notes": notes or "Keine besonderen Vorkommnisse"
            })
            
        except Exception as e:
            _LOGGER.error("Error executing walk action: %s", e)
            raise

    async def _play_with_dog_service(self, call: ServiceCall) -> None:
        """Service to record play session."""
        try:
            self._update_stats("activity_actions")
            
            duration = call.data.get("duration", 15)  # minutes
            play_type = call.data.get("play_type", "general")
            intensity = call.data.get("intensity", "medium")
            notes = call.data.get("notes", "")
            
            await self._execute_play_action(duration, play_type, intensity, notes)
            
            await self._send_notification(
                f"🎾 Spielzeit - {self._dog_name.title()}",
                f"Spielsession beendet ({duration} min, {play_type}, {intensity})",
                f"play_completed_{self._dog_name}"
            )
            
            _LOGGER.info("Recorded play session for %s: %d minutes", self._dog_name, duration)
            
        except Exception as e:
            _LOGGER.error("Error in play with dog service for %s: %s", self._dog_name, e)

    async def _execute_play_action(self, duration: int, play_type: str, intensity: str, notes: str) -> None:
        """Execute play action."""
        try:
            # Increment play counter
            await self.hass.services.async_call(
                "counter", "increment",
                {"entity_id": f"counter.{self._dog_name}_play_count"}
            )
            
            # Update last play time
            await self.hass.services.async_call(
                "input_datetime", "set_datetime",
                {
                    "entity_id": f"input_datetime.{self._dog_name}_last_play",
                    "datetime": datetime.now().isoformat()
                }
            )
            
            # Update last activity
            await self.hass.services.async_call(
                "input_datetime", "set_datetime",
                {
                    "entity_id": f"input_datetime.{self._dog_name}_last_activity", 
                    "datetime": datetime.now().isoformat()
                }
            )
            
            # Mark as played today
            await self.hass.services.async_call(
                "input_boolean", "turn_on",
                {"entity_id": f"input_boolean.{self._dog_name}_played_today"}
            )
            
            # Update play duration if entity exists
            if duration:
                duration_entity = f"input_number.{self._dog_name}_daily_play_time"
                await self.hass.services.async_call(
                    "input_number", "set_value",
                    {
                        "entity_id": duration_entity,
                        "value": duration
                    }
                )
            
            # Add detailed notes
            await self._add_activity_notes("Spielsession", {
                "duration": f"{duration} min",
                "type": play_type,
                "intensity": intensity,
                "notes": notes or "Keine besonderen Vorkommnisse"
            })
            
        except Exception as e:
            _LOGGER.error("Error executing play action: %s", e)
            raise

    async def _training_session_service(self, call: ServiceCall) -> None:
        """Service to record training session."""
        try:
            self._update_stats("activity_actions")
            
            duration = call.data.get("duration", 10)  # minutes
            training_type = call.data.get("training_type", "basic")
            commands_practiced = call.data.get("commands", "")
            success_rate = call.data.get("success_rate", "good")
            notes = call.data.get("notes", "")
            
            await self._execute_training_action(duration, training_type, commands_practiced, success_rate, notes)
            
            await self._send_notification(
                f"🎓 Training - {self._dog_name.title()}",
                f"Training beendet ({duration} min, {training_type}, {success_rate})",
                f"training_completed_{self._dog_name}"
            )
            
            _LOGGER.info("Recorded training session for %s: %d minutes", self._dog_name, duration)
            
        except Exception as e:
            _LOGGER.error("Error in training session service for %s: %s", self._dog_name, e)

    async def _execute_training_action(self, duration: int, training_type: str, commands: str, success_rate: str, notes: str) -> None:
        """Execute training action."""
        try:
            # Increment training counter
            await self.hass.services.async_call(
                "counter", "increment",
                {"entity_id": f"counter.{self._dog_name}_training_count"}
            )
            
            # Update last training time
            await self.hass.services.async_call(
                "input_datetime", "set_datetime",
                {
                    "entity_id": f"input_datetime.{self._dog_name}_last_training",
                    "datetime": datetime.now().isoformat()
                }
            )
            
            # Update last activity
            await self.hass.services.async_call(
                "input_datetime", "set_datetime",
                {
                    "entity_id": f"input_datetime.{self._dog_name}_last_activity",
                    "datetime": datetime.now().isoformat()
                }
            )
            
            # Update training duration
            if duration:
                duration_entity = f"input_number.{self._dog_name}_training_duration"
                await self.hass.services.async_call(
                    "input_number", "set_value",
                    {
                        "entity_id": duration_entity,
                        "value": duration
                    }
                )
            
            # Add detailed training notes
            await self._add_activity_notes("Training", {
                "duration": f"{duration} min",
                "type": training_type,
                "commands": commands or "Verschiedene Kommandos",
                "success_rate": success_rate,
                "notes": notes or "Keine besonderen Vorkommnisse"
            })
            
        except Exception as e:
            _LOGGER.error("Error executing training action: %s", e)
            raise

    # HEALTH SERVICES
    
    async def _health_check_service(self, call: ServiceCall) -> None:
        """Service to perform health check."""
        try:
            self._update_stats("health_actions")
            
            health_status = call.data.get("health_status", "")
            weight = call.data.get("weight", None)
            temperature = call.data.get("temperature", None)
            mood = call.data.get("mood", "")
            appetite = call.data.get("appetite", "")
            energy_level = call.data.get("energy_level", "")
            notes = call.data.get("notes", "")
            
            await self._execute_health_check(health_status, weight, temperature, mood, appetite, energy_level, notes)
            
            await self._send_notification(
                f"🏥 Gesundheitscheck - {self._dog_name.title()}",
                f"Gesundheitscheck durchgeführt (Status: {health_status or 'Aktualisiert'})",
                f"health_check_completed_{self._dog_name}"
            )
            
            _LOGGER.info("Performed health check for %s", self._dog_name)
            
        except Exception as e:
            _LOGGER.error("Error in health check service for %s: %s", self._dog_name, e)

    async def _execute_health_check(self, health_status: str, weight: Optional[float], 
                                  temperature: Optional[float], mood: str, appetite: str, 
                                  energy_level: str, notes: str) -> None:
        """Execute health check."""
        try:
            # Update health status if provided
            if health_status:
                await self.hass.services.async_call(
                    "input_select", "select_option",
                    {
                        "entity_id": f"input_select.{self._dog_name}_health_status",
                        "option": health_status
                    }
                )
            
            # Update mood if provided
            if mood:
                await self.hass.services.async_call(
                    "input_select", "select_option",
                    {
                        "entity_id": f"input_select.{self._dog_name}_mood",
                        "option": mood
                    }
                )
            
            # Update appetite if provided
            if appetite:
                await self.hass.services.async_call(
                    "input_select", "select_option",
                    {
                        "entity_id": f"input_select.{self._dog_name}_appetite_level",
                        "option": appetite
                    }
                )
            
            # Update energy level if provided
            if energy_level:
                await self.hass.services.async_call(
                    "input_select", "select_option",
                    {
                        "entity_id": f"input_select.{self._dog_name}_energy_level_category",
                        "option": energy_level
                    }
                )
            
            # Update weight if provided
            if weight is not None:
                await self.hass.services.async_call(
                    "input_number", "set_value",
                    {
                        "entity_id": f"input_number.{self._dog_name}_weight",
                        "value": weight
                    }
                )
                
                # Update last weight check time
                await self.hass.services.async_call(
                    "input_datetime", "set_datetime",
                    {
                        "entity_id": f"input_datetime.{self._dog_name}_last_weight_check",
                        "datetime": datetime.now().isoformat()
                    }
                )
            
            # Update temperature if provided
            if temperature is not None:
                await self.hass.services.async_call(
                    "input_number", "set_value",
                    {
                        "entity_id": f"input_number.{self._dog_name}_temperature",
                        "value": temperature
                    }
                )
            
            # Add health notes
            health_details = {
                "health_status": health_status or "Nicht geändert",
                "mood": mood or "Nicht geändert",
                "appetite": appetite or "Nicht geändert",
                "energy_level": energy_level or "Nicht geändert",
            }
            
            if weight is not None:
                health_details["weight"] = f"{weight} kg"
            if temperature is not None:
                health_details["temperature"] = f"{temperature} °C"
            
            health_details["notes"] = notes or "Keine besonderen Beobachtungen"
            
            await self._add_activity_notes("Gesundheitscheck", health_details)
            
        except Exception as e:
            _LOGGER.error("Error executing health check: %s", e)
            raise

    async def _medication_given_service(self, call: ServiceCall) -> None:
        """Service to mark medication as given."""
        try:
            self._update_stats("health_actions")
            
            medication_name = call.data.get("medication", "")
            dosage = call.data.get("dosage", "")
            time_given = call.data.get("time", datetime.now().strftime("%H:%M"))
            notes = call.data.get("notes", "")
            
            await self._execute_medication_action(medication_name, dosage, time_given, notes)
            
            await self._send_notification(
                f"💊 Medikament - {self._dog_name.title()}",
                f"Medikament gegeben ({medication_name or 'Standard'} um {time_given})",
                f"medication_given_{self._dog_name}"
            )
            
            _LOGGER.info("Recorded medication for %s: %s", self._dog_name, medication_name)
            
        except Exception as e:
            _LOGGER.error("Error in medication service for %s: %s", self._dog_name, e)

    async def _execute_medication_action(self, medication: str, dosage: str, time_given: str, notes: str) -> None:
        """Execute medication action."""
        try:
            # Mark medication as given
            await self.hass.services.async_call(
                "input_boolean", "turn_on",
                {"entity_id": f"input_boolean.{self._dog_name}_medication_given"}
            )
            
            # Increment medication counter
            await self.hass.services.async_call(
                "counter", "increment",
                {"entity_id": f"counter.{self._dog_name}_medication_count"}
            )
            
            # Add medication details to notes
            await self._add_activity_notes("Medikament", {
                "medication": medication or "Standardmedikation",
                "dosage": dosage or "Wie verordnet",
                "time_given": time_given,
                "notes": notes or "Ohne Probleme gegeben"
            })
            
        except Exception as e:
            _LOGGER.error("Error executing medication action: %s", e)
            raise

    async def _vet_visit_service(self, call: ServiceCall) -> None:
        """Service to record vet visit."""
        try:
            self._update_stats("health_actions")
            
            visit_type = call.data.get("visit_type", "routine")
            diagnosis = call.data.get("diagnosis", "")
            treatment = call.data.get("treatment", "")
            next_appointment = call.data.get("next_appointment", "")
            cost = call.data.get("cost", "")
            notes = call.data.get("notes", "")
            
            await self._execute_vet_visit_action(visit_type, diagnosis, treatment, next_appointment, cost, notes)
            
            await self._send_notification(
                f"🏥 Tierarztbesuch - {self._dog_name.title()}",
                f"Tierarztbesuch eingetragen ({visit_type})",
                f"vet_visit_recorded_{self._dog_name}"
            )
            
            _LOGGER.info("Recorded vet visit for %s: %s", self._dog_name, visit_type)
            
        except Exception as e:
            _LOGGER.error("Error in vet visit service for %s: %s", self._dog_name, e)

    async def _execute_vet_visit_action(self, visit_type: str, diagnosis: str, treatment: str, 
                                      next_appointment: str, cost: str, notes: str) -> None:
        """Execute vet visit action."""
        try:
            # Update last vet visit time
            await self.hass.services.async_call(
                "input_datetime", "set_datetime",
                {
                    "entity_id": f"input_datetime.{self._dog_name}_last_vet_visit",
                    "datetime": datetime.now().isoformat()
                }
            )
            
            # Increment vet visit counter
            await self.hass.services.async_call(
                "counter", "increment",
                {"entity_id": f"counter.{self._dog_name}_vet_visits_count"}
            )
            
            # Set next appointment if provided
            if next_appointment:
                try:
                    next_date = datetime.fromisoformat(next_appointment)
                    await self.hass.services.async_call(
                        "input_datetime", "set_datetime",
                        {
                            "entity_id": f"input_datetime.{self._dog_name}_next_vet_appointment",
                            "datetime": next_date.isoformat()
                        }
                    )
                except ValueError:
                    _LOGGER.warning("Invalid next appointment date: %s", next_appointment)
            
            # Add detailed vet notes
            await self._add_activity_notes("Tierarztbesuch", {
                "visit_type": visit_type,
                "diagnosis": diagnosis or "Keine Diagnose",
                "treatment": treatment or "Keine Behandlung",
                "next_appointment": next_appointment or "Nicht geplant",
                "cost": cost or "Nicht angegeben",
                "notes": notes or "Routine-Besuch"
            })
            
        except Exception as e:
            _LOGGER.error("Error executing vet visit action: %s", e)
            raise

    # CARE SERVICES
    
    async def _grooming_session_service(self, call: ServiceCall) -> None:
        """Service to record grooming session."""
        try:
            self._update_stats("maintenance_actions")
            
            grooming_type = call.data.get("grooming_type", "basic")
            duration = call.data.get("duration", 30)
            professional = call.data.get("professional", False)
            notes = call.data.get("notes", "")
            
            await self._execute_grooming_action(grooming_type, duration, professional, notes)
            
            groomer = "Professionell" if professional else "Zuhause"
            await self._send_notification(
                f"✂️ Pflege - {self._dog_name.title()}",
                f"Pflegesession beendet ({grooming_type}, {duration} min, {groomer})",
                f"grooming_completed_{self._dog_name}"
            )
            
            _LOGGER.info("Recorded grooming session for %s: %s", self._dog_name, grooming_type)
            
        except Exception as e:
            _LOGGER.error("Error in grooming session service for %s: %s", self._dog_name, e)

    async def _execute_grooming_action(self, grooming_type: str, duration: int, professional: bool, notes: str) -> None:
        """Execute grooming action."""
        try:
            # Update last grooming time
            await self.hass.services.async_call(
                "input_datetime", "set_datetime",
                {
                    "entity_id": f"input_datetime.{self._dog_name}_last_grooming",
                    "datetime": datetime.now().isoformat()
                }
            )
            
            # Increment grooming counter
            await self.hass.services.async_call(
                "counter", "increment",
                {"entity_id": f"counter.{self._dog_name}_grooming_count"}
            )
            
            # Mark as not needing grooming
            await self.hass.services.async_call(
                "input_boolean", "turn_off",
                {"entity_id": f"input_boolean.{self._dog_name}_needs_grooming"}
            )
            
            # Add grooming details
            await self._add_activity_notes("Pflege", {
                "type": grooming_type,
                "duration": f"{duration} min",
                "professional": "Ja" if professional else "Nein",
                "notes": notes or "Standard Pflegesession"
            })
            
        except Exception as e:
            _LOGGER.error("Error executing grooming action: %s", e)
            raise

    # SYSTEM SERVICES
    
    async def _emergency_mode_service(self, call: ServiceCall) -> None:
        """Service to activate/deactivate emergency mode."""
        try:
            self._update_stats("maintenance_actions")
            
            activate = call.data.get("activate", True)
            reason = call.data.get("reason", "")
            contact_vet = call.data.get("contact_vet", False)
            
            if activate:
                await self._activate_emergency_mode(reason, contact_vet)
            else:
                await self._deactivate_emergency_mode()
            
            status = "aktiviert" if activate else "deaktiviert"
            await self._send_notification(
                f"🚨 Notfallmodus - {self._dog_name.title()}",
                f"Notfallmodus {status}" + (f" - {reason}" if reason else ""),
                f"emergency_mode_{self._dog_name}"
            )
            
            _LOGGER.info("Emergency mode %s for %s", status, self._dog_name)
            
        except Exception as e:
            _LOGGER.error("Error in emergency mode service for %s: %s", self._dog_name, e)

    async def _activate_emergency_mode(self, reason: str, contact_vet: bool) -> None:
        """Activate emergency mode."""
        try:
            # Activate emergency mode
            await self.hass.services.async_call(
                "input_boolean", "turn_on",
                {"entity_id": f"input_boolean.{self._dog_name}_emergency_mode"}
            )
            
            # Set emergency level to critical
            await self.hass.services.async_call(
                "input_select", "select_option",
                {
                    "entity_id": f"input_select.{self._dog_name}_emergency_level",
                    "option": "Kritisch"
                }
            )
            
            # Record emergency activation time
            await self.hass.services.async_call(
                "input_datetime", "set_datetime",
                {
                    "entity_id": f"input_datetime.{self._dog_name}_emergency_contact_time",
                    "datetime": datetime.now().isoformat()
                }
            )
            
            # Increment emergency counter
            await self.hass.services.async_call(
                "counter", "increment",
                {"entity_id": f"counter.{self._dog_name}_emergency_calls"}
            )
            
            # Add emergency notes
            await self._add_activity_notes("NOTFALL", {
                "reason": reason or "Notfallmodus aktiviert",
                "contact_vet": "Ja" if contact_vet else "Nein",
                "activation_time": datetime.now().strftime("%H:%M:%S")
            })
            
        except Exception as e:
            _LOGGER.error("Error activating emergency mode: %s", e)
            raise

    async def _deactivate_emergency_mode(self) -> None:
        """Deactivate emergency mode."""
        try:
            # Deactivate emergency mode
            await self.hass.services.async_call(
                "input_boolean", "turn_off",
                {"entity_id": f"input_boolean.{self._dog_name}_emergency_mode"}
            )
            
            # Reset emergency level to normal
            await self.hass.services.async_call(
                "input_select", "select_option",
                {
                    "entity_id": f"input_select.{self._dog_name}_emergency_level",
                    "option": "Normal"
                }
            )
            
            # Add deactivation note
            await self._add_activity_notes("Notfall beendet", {
                "deactivation_time": datetime.now().strftime("%H:%M:%S"),
                "status": "Notfallmodus deaktiviert"
            })
            
        except Exception as e:
            _LOGGER.error("Error deactivating emergency mode: %s", e)
            raise

    async def _visitor_mode_service(self, call: ServiceCall) -> None:
        """Service to toggle visitor mode."""
        try:
            activate = call.data.get("activate", None)
            visitor_name = call.data.get("visitor_name", "")
            start_time = call.data.get("start_time", "")
            end_time = call.data.get("end_time", "")
            
            # Get current state if activate not specified
            if activate is None:
                current_state = self.hass.states.get(f"input_boolean.{self._dog_name}_visitor_mode_input")
                activate = not (current_state and current_state.state == "on")
            
            await self._execute_visitor_mode_toggle(activate, visitor_name, start_time, end_time)
            
            status = "aktiviert" if activate else "deaktiviert"
            visitor_text = f" ({visitor_name})" if visitor_name else ""
            
            await self._send_notification(
                f"👋 Besuchsmodus - {self._dog_name.title()}",
                f"Besuchsmodus {status}{visitor_text}",
                f"visitor_mode_{self._dog_name}"
            )
            
            _LOGGER.info("Visitor mode %s for %s", status, self._dog_name)
            
        except Exception as e:
            _LOGGER.error("Error in visitor mode service for %s: %s", self._dog_name, e)

    async def _execute_visitor_mode_toggle(self, activate: bool, visitor_name: str, start_time: str, end_time: str) -> None:
        """Execute visitor mode toggle."""
        try:
            if activate:
                # Activate visitor mode
                await self.hass.services.async_call(
                    "input_boolean", "turn_on",
                    {"entity_id": f"input_boolean.{self._dog_name}_visitor_mode_input"}
                )
                
                # Set visitor name
                if visitor_name:
                    await self.hass.services.async_call(
                        "input_text", "set_value",
                        {
                            "entity_id": f"input_text.{self._dog_name}_visitor_name",
                            "value": visitor_name
                        }
                    )
                
                # Set start time
                start_dt = datetime.now()
                if start_time:
                    try:
                        start_dt = datetime.fromisoformat(start_time)
                    except ValueError:
                        pass
                
                await self.hass.services.async_call(
                    "input_datetime", "set_datetime",
                    {
                        "entity_id": f"input_datetime.{self._dog_name}_visitor_start",
                        "datetime": start_dt.isoformat()
                    }
                )
                
                # Set end time if provided
                if end_time:
                    try:
                        end_dt = datetime.fromisoformat(end_time)
                        await self.hass.services.async_call(
                            "input_datetime", "set_datetime",
                            {
                                "entity_id": f"input_datetime.{self._dog_name}_visitor_end",
                                "datetime": end_dt.isoformat()
                            }
                        )
                    except ValueError:
                        pass
                
            else:
                # Deactivate visitor mode
                await self.hass.services.async_call(
                    "input_boolean", "turn_off",
                    {"entity_id": f"input_boolean.{self._dog_name}_visitor_mode_input"}
                )
                
                # Set end time to now
                await self.hass.services.async_call(
                    "input_datetime", "set_datetime",
                    {
                        "entity_id": f"input_datetime.{self._dog_name}_visitor_end",
                        "datetime": datetime.now().isoformat()
                    }
                )
            
        except Exception as e:
            _LOGGER.error("Error executing visitor mode toggle: %s", e)
            raise

    async def _daily_reset_service(self, call: ServiceCall) -> None:
        """Service to perform daily reset."""
        try:
            self._update_stats("maintenance_actions")
            
            reset_date = call.data.get("date", datetime.now().date().isoformat())
            
            await self._execute_daily_reset()
            
            await self._send_notification(
                f"🔄 Tagesreset - {self._dog_name.title()}",
                f"Tagesreset durchgeführt für {reset_date}",
                f"daily_reset_{self._dog_name}"
            )
            
            _LOGGER.info("Performed daily reset for %s", self._dog_name)
            
        except Exception as e:
            _LOGGER.error("Error in daily reset service for %s: %s", self._dog_name, e)

    async def _execute_daily_reset(self) -> None:
        """Execute daily reset."""
        try:
            # Reset daily feeding booleans
            feeding_entities = [f"input_boolean.{self._dog_name}_feeding_{meal}" for meal in FEEDING_TYPES]
            for entity_id in feeding_entities:
                await self.hass.services.async_call(
                    "input_boolean", "turn_off",
                    {"entity_id": entity_id}
                )
            
            # Reset daily activity booleans
            daily_booleans = [
                f"input_boolean.{self._dog_name}_outside",
                f"input_boolean.{self._dog_name}_poop_done",
                f"input_boolean.{self._dog_name}_walked_today",
                f"input_boolean.{self._dog_name}_played_today",
                f"input_boolean.{self._dog_name}_socialized_today",
                f"input_boolean.{self._dog_name}_medication_given",
            ]
            
            for entity_id in daily_booleans:
                await self.hass.services.async_call(
                    "input_boolean", "turn_off",
                    {"entity_id": entity_id}
                )
            
            # Clear daily notes
            await self.hass.services.async_call(
                "input_text", "set_value",
                {
                    "entity_id": f"input_text.{self._dog_name}_daily_notes",
                    "value": f"Tagesreset: {datetime.now().strftime('%d.%m.%Y')}"
                }
            )
            
            # Add reset note
            await self._add_activity_notes("Tagesreset", {
                "reset_time": datetime.now().strftime("%H:%M:%S"),
                "reset_date": datetime.now().date().isoformat(),
                "status": "Alle täglichen Einstellungen zurückgesetzt"
            })
            
        except Exception as e:
            _LOGGER.error("Error executing daily reset: %s", e)
            raise


from custom_components.pawcontrol.setup.logic import create_feeding_helpers, apply_setup_schema

SERVICE_INITIALIZE_SETUP = "initialize_setup"

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    dog_name = config_entry.data[CONF_DOG_NAME]
    script_manager = PawControlScriptManager(hass, config_entry, dog_name)

    await script_manager.async_setup_services()

    async def _initialize_setup(call: ServiceCall):
        feeding = await create_feeding_helpers(hass)
        schema = await apply_setup_schema(hass)
        await sync_all_dog_helpers, generate_dashboard_view, register_dashboard_view(hass)
        await register_dashboard_view(hass)
        await generate_dashboard_view, register_dashboard_view(hass)
        _LOGGER.info("Initialized feeding: %%s", feeding)
        _LOGGER.info("Applied setup schema: %%s", schema)

    hass.services.async_register(DOMAIN, SERVICE_INITIALIZE_SETUP, _initialize_setup)

    _LOGGER.info("Successfully set up Paw Control scripts for %%s", dog_name)
