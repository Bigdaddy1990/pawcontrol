"""Setup verification and auto-fix functionality for Paw Control."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .utils import safe_service_call

_LOGGER = logging.getLogger(__name__)


@dataclass
class CriticalEntityReport:
    """Result information from :func:`async_verify_critical_entities`."""

    critical_entities_total: int
    critical_entities_found: int = 0
    critical_entities_missing: list[str] = field(default_factory=list)
    critical_entities_working: list[str] = field(default_factory=list)
    critical_entities_broken: list[str] = field(default_factory=list)
    is_functional: bool = False
    error: str | None = None


async def async_verify_critical_entities(
    hass: HomeAssistant, dog_name: str
) -> Dict[str, Any]:
    """Verify that critical entities exist and are functional."""
    critical_entities = [
        f"input_boolean.{dog_name}_feeding_morning",
        f"input_boolean.{dog_name}_feeding_evening",
        f"input_boolean.{dog_name}_outside",
        f"counter.{dog_name}_outside_count",
        f"input_text.{dog_name}_notes",
        f"input_datetime.{dog_name}_last_outside",
        f"input_select.{dog_name}_health_status",
        f"input_number.{dog_name}_weight",
    ]

    report = CriticalEntityReport(critical_entities_total=len(critical_entities))

    try:
        for entity_id in critical_entities:
            state = hass.states.get(entity_id)
            if not state:
                report.critical_entities_missing.append(entity_id)
                continue

            report.critical_entities_found += 1
            if state.state in ["unknown", "unavailable"]:
                report.critical_entities_broken.append(entity_id)
            else:
                report.critical_entities_working.append(entity_id)

        working_count = len(report.critical_entities_working)
        report.is_functional = (
            working_count / report.critical_entities_total
        ) >= 0.8  # 80% threshold

        _LOGGER.info(
            "Critical entity verification for %s: %d/%d working (%.1f%%)",
            dog_name,
            working_count,
            report.critical_entities_total,
            (working_count / report.critical_entities_total) * 100,
        )

        return asdict(report)

    except Exception as e:
        report.error = str(e)
        _LOGGER.error("Error during critical entity verification: %s", e)
        report.is_functional = False
        return asdict(report)


async def async_repair_broken_entities(hass: HomeAssistant, dog_name: str, expected_entities: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Attempt to repair broken entities by recreating them."""
    repair_result = {
        "entities_checked": 0,
        "entities_repaired": 0,
        "entities_failed": 0,
        "repaired_entities": [],
        "failed_entities": [],
        "repair_actions": []
    }
    
    try:
        for entity_id, entity_info in expected_entities.items():
            repair_result["entities_checked"] += 1
            state = hass.states.get(entity_id)
            needs_repair = False
            repair_reason = ""
            
            if not state:
                needs_repair = True
                repair_reason = "Entity does not exist"
            elif state.state in ["unknown", "unavailable"]:
                needs_repair = True
                repair_reason = f"Entity in invalid state: {state.state}"
            elif not state.attributes.get("friendly_name"):
                needs_repair = True
                repair_reason = "Missing friendly name"
            
            if needs_repair:
                _LOGGER.info("Repairing entity %s: %s", entity_id, repair_reason)
                try:
                    # Remove existing entity if it exists but is broken
                    if state:
                        try:
                            domain = entity_id.split('.')[0]
                            await hass.services.async_call(
                                domain, "remove", 
                                {"entity_id": entity_id}, 
                                blocking=True
                            )
                            await asyncio.sleep(1.0)
                        except Exception as remove_error:
                            _LOGGER.debug("Could not remove broken entity %s: %s", entity_id, remove_error)
                    
                    # Recreate the entity
                    success = await _create_missing_entity(hass, entity_id, entity_info, dog_name)
                    
                    if success:
                        repair_result["entities_repaired"] += 1
                        repair_result["repaired_entities"].append(entity_id)
                        repair_result["repair_actions"].append(f"Repaired {entity_id}: {repair_reason}")
                        _LOGGER.info("✅ Successfully repaired: %s", entity_id)
                    else:
                        repair_result["entities_failed"] += 1
                        repair_result["failed_entities"].append(entity_id)
                        repair_result["repair_actions"].append(f"Failed to repair {entity_id}: {repair_reason}")
                        _LOGGER.error("❌ Failed to repair: %s", entity_id)
                        
                except Exception as repair_error:
                    repair_result["entities_failed"] += 1
                    repair_result["failed_entities"].append(entity_id)
                    error_msg = f"Exception repairing {entity_id}: {str(repair_error)}"
                    repair_result["repair_actions"].append(error_msg)
                    _LOGGER.error("❌ %s", error_msg)
                
                await asyncio.sleep(0.5)
        
        _LOGGER.info("Entity repair completed for %s: %d repaired, %d failed", 
                    dog_name, repair_result["entities_repaired"], repair_result["entities_failed"])
        
        return repair_result
        
    except Exception as e:
        _LOGGER.error("Critical error during entity repair: %s", e)
        return {
            **repair_result,
            "error": str(e)
        }


async def async_generate_installation_report(hass: HomeAssistant, dog_name: str, verification_result: Dict[str, Any], critical_check: Dict[str, Any]) -> str:
    """Generate a comprehensive installation report."""
    try:
        _LOGGER.info("Generating installation report for %s", dog_name)
        
        report = f"""
# 🐕 Paw Control Installation Report - {dog_name.title()}

**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 📊 Overview
- **Status:** {verification_result.get('status', 'unknown').upper()}
- **Success Rate:** {verification_result.get('success_rate', 0):.1f}%
- **Total Expected Entities:** {verification_result.get('total_entities_expected', 0)}
- **Total Found Entities:** {verification_result.get('total_entities_found', 0)}

## 🎯 Critical Entities Status
- **Critical Entities Working:** {critical_check.get('critical_entities_found', 0)}/{critical_check.get('critical_entities_total', 0)}
- **Installation Functional:** {'✅ YES' if critical_check.get('is_functional') else '❌ NO'}

## 🔧 Auto-Fix Results
"""
        
        if verification_result.get('created_entities'):
            report += f"- **Entities Created:** {len(verification_result['created_entities'])}\n"
            for entity in verification_result['created_entities'][:10]:
                report += f"  - ✅ {entity}\n"
            if len(verification_result['created_entities']) > 10:
                report += f"  - ... and {len(verification_result['created_entities']) - 10} more\n"
        else:
            report += "- **No entities needed to be created**\n"
        
        if verification_result.get('errors'):
            report += f"\n## ❌ Errors ({len(verification_result['errors'])})\n"
            for error in verification_result['errors'][:5]:
                report += f"- {error}\n"
            if len(verification_result['errors']) > 5:
                report += f"- ... and {len(verification_result['errors']) - 5} more errors\n"
        
        if verification_result.get('missing_entities'):
            report += f"\n## 🚫 Still Missing Entities ({len(verification_result['missing_entities'])})\n"
            for entity in verification_result['missing_entities'][:10]:
                report += f"- {entity}\n"
            if len(verification_result['missing_entities']) > 10:
                report += f"- ... and {len(verification_result['missing_entities']) - 10} more\n"
        
        report += "\n## 💡 Recommendations\n"
        if verification_result.get('success_rate', 0) >= 95:
            report += "- ✅ Installation is excellent! All systems ready.\n"
        elif verification_result.get('success_rate', 0) >= 80:
            report += "- ⚡ Installation is good. Minor issues auto-fixed.\n"
        elif verification_result.get('success_rate', 0) >= 60:
            report += "- ⚠️ Installation has some issues. Consider manual intervention.\n"
        else:
            report += "- 🚨 Installation has significant problems. Manual setup may be required.\n"
        
        if not critical_check.get('is_functional'):
            report += "- 🔧 Critical entities are missing. Run verification again or recreate integration.\n"
        
        report += f"\n---\n*Report generated by Paw Control v1.0 for {dog_name}*"
        
        return report
        
    except Exception as e:
        _LOGGER.error("Error generating installation report: %s", e)
        return f"# Error Generating Report\n\nAn error occurred: {str(e)}"


async def async_verify_and_fix_installation(hass: HomeAssistant, dog_name: str) -> Dict[str, Any]:
    """Verify Paw Control installation and auto-fix any issues."""
    try:
        _LOGGER.info("🔍 Starting installation verification for %s", dog_name)
        
        verification_result = {
            "status": "unknown",
            "dog_name": dog_name,
            "total_entities_expected": 0,
            "total_entities_found": 0,
            "missing_entities": [],
            "created_entities": [],
            "errors": [],
            "success_rate": 0.0,
            "verification_timestamp": datetime.now().isoformat()
        }
        
        # Define all expected entities
        expected_entities = await _get_expected_entities(dog_name)
        verification_result["total_entities_expected"] = len(expected_entities)
        
        # Check which entities exist
        existing_entities = []
        missing_entities = []
        
        for entity_id, entity_info in expected_entities.items():
            if hass.states.get(entity_id):
                existing_entities.append(entity_id)
            else:
                missing_entities.append({
                    "entity_id": entity_id,
                    "domain": entity_info["domain"],
                    "friendly_name": entity_info["friendly_name"],
                    "icon": entity_info.get("icon", "mdi:dog"),
                    "config": entity_info.get("config", {})
                })
        
        verification_result["total_entities_found"] = len(existing_entities)
        verification_result["missing_entities"] = [e["entity_id"] for e in missing_entities]
        verification_result["success_rate"] = (len(existing_entities) / len(expected_entities)) * 100 if expected_entities else 0
        
        _LOGGER.info("📊 Initial verification: %d/%d entities found (%.1f%%)", 
                    len(existing_entities), len(expected_entities), 
                    verification_result["success_rate"])
        
        # Auto-fix missing entities
        if missing_entities:
            _LOGGER.info("🔧 Auto-fixing %d missing entities...", len(missing_entities))
            
            created_entities = []
            fix_errors = []
            
            for missing_entity in missing_entities:
                try:
                    success = await _create_missing_entity(hass, missing_entity["entity_id"], missing_entity, dog_name)
                    if success:
                        created_entities.append(missing_entity["entity_id"])
                        _LOGGER.debug("✅ Created: %s", missing_entity["entity_id"])
                    else:
                        fix_errors.append(f"Failed to create {missing_entity['entity_id']}")
                        
                except Exception as e:
                    error_msg = f"Error creating {missing_entity['entity_id']}: {str(e)}"
                    fix_errors.append(error_msg)
                    _LOGGER.error("❌ %s", error_msg)
                
                # Brief pause between entity creations
                await asyncio.sleep(0.5)
            
            verification_result["created_entities"] = created_entities
            verification_result["errors"] = fix_errors
            
            # Update statistics
            total_now_existing = verification_result["total_entities_found"] + len(created_entities)
            verification_result["total_entities_found"] = total_now_existing
            verification_result["success_rate"] = (total_now_existing / len(expected_entities)) * 100 if expected_entities else 0
            
            _LOGGER.info("🔧 Auto-fix completed: %d entities created, %d errors", 
                        len(created_entities), len(fix_errors))
        
        # Determine final status
        if verification_result["success_rate"] >= 100.0:
            verification_result["status"] = "success"
        elif verification_result["success_rate"] >= 80.0 and verification_result["created_entities"]:
            verification_result["status"] = "fixed"
        elif verification_result["success_rate"] >= 50.0:
            verification_result["status"] = "partial"
        else:
            verification_result["status"] = "failed"
        
        # Set smart defaults after entity creation
        await _set_smart_default_values(hass, dog_name)
        
        _LOGGER.info("🎯 Final verification result for %s: %s (%.1f%% success)", 
                    dog_name, verification_result["status"], verification_result["success_rate"])
        
        return verification_result
        
    except Exception as e:
        _LOGGER.error("❌ Critical error during installation verification: %s", e)
        return {
            "status": "error",
            "dog_name": dog_name,
            "error": str(e),
            "verification_timestamp": datetime.now().isoformat()
        }


async def _get_expected_entities(dog_name: str) -> Dict[str, Dict[str, Any]]:
    """Get dictionary of all expected entities for a dog."""
    from .const import ENTITIES
    
    expected_entities = {}
    
    # Process each entity type from ENTITIES constant
    for entity_type, entities_config in ENTITIES.items():
        for entity_suffix, entity_config in entities_config.items():
            entity_id = f"{entity_type}.{dog_name}_{entity_suffix}"
            
            expected_entities[entity_id] = {
                "domain": entity_type,
                "friendly_name": f"{dog_name.title()} {entity_config['name']}",
                "icon": entity_config.get("icon", "mdi:dog"),
                "config": entity_config
            }
    
    return expected_entities


async def _create_missing_entity(hass: HomeAssistant, entity_id: str, entity_info: Dict[str, Any], dog_name: str) -> bool:
    """Create a single missing entity."""
    try:
        domain = entity_info["domain"]
        friendly_name = entity_info["friendly_name"]
        config = entity_info.get("config", {})
        
        service_data = {
            "name": friendly_name,
            **config
        }
        
        await asyncio.wait_for(
            hass.services.async_call(domain, "create", service_data, blocking=True),
            timeout=30.0
        )
        await asyncio.sleep(1.0)
        
        state = hass.states.get(entity_id)
        if state:
            _LOGGER.debug("Successfully created entity: %s", entity_id)
            return True
        else:
            _LOGGER.warning("Entity created but not found in state registry: %s", entity_id)
            return False
            
    except asyncio.TimeoutError:
        _LOGGER.error("Timeout creating entity %s", entity_id)
        return False
    except Exception as e:
        _LOGGER.error("Error creating entity %s: %s", entity_id, e)
        return False


async def _set_smart_default_values(hass: HomeAssistant, dog_name: str) -> None:
    """Set intelligent default values for key entities."""
    try:
        # Set default home coordinates (Detmold, Germany)
        home_coords_entity = f"input_text.{dog_name}_home_coordinates"
        if hass.states.get(home_coords_entity):
            state = hass.states.get(home_coords_entity)
            if not state.state or state.state == "":
                await safe_service_call(
                    hass, "input_text", "set_value",
                    {
                        "entity_id": home_coords_entity,
                        "value": "52.233333,8.966667"
                    }
                )
                _LOGGER.info("🏠 Set default home coordinates for %s to Detmold", dog_name)
        
        # Set GPS tracker status config
        gps_status_entity = f"input_text.{dog_name}_gps_tracker_status"
        if hass.states.get(gps_status_entity):
            state = hass.states.get(gps_status_entity)
            if not state.state or state.state == "":
                intelligent_config = {
                    "source": "manual",
                    "entity": None,
                    "sensitivity": "medium",
                    "auto_start": False,
                    "auto_end": False,
                    "track_route": True,
                    "calculate_stats": True,
                    "setup_time": None,
                    "status": "ready_for_configuration",
                    "features": {
                        "distance_tracking": True,
                        "speed_calculation": True,
                        "route_recording": True,
                        "geofencing": True,
                        "automatic_detection": False
                    },
                    "thresholds": {
                        "movement_threshold_m": 50,
                        "home_zone_radius_m": 100,
                        "min_walk_duration_min": 5,
                        "max_walk_duration_min": 180
                    }
                }
                await safe_service_call(
                    hass, "input_text", "set_value",
                    {
                        "entity_id": gps_status_entity,
                        "value": str(intelligent_config)
                    }
                )
                _LOGGER.info("🔧 Set intelligent GPS configuration for %s", dog_name)
        
        # Set smart default metrics
        smart_defaults = {
            f"input_number.{dog_name}_gps_signal_strength": 100,
            f"input_number.{dog_name}_gps_battery_level": 100,
            f"input_number.{dog_name}_health_score": 8,
            f"input_number.{dog_name}_happiness_score": 8,
            f"input_number.{dog_name}_weight": 15.0,
            f"input_number.{dog_name}_age_years": 3.0,
            f"input_number.{dog_name}_daily_food_amount": 400,
        }
        
        for entity_id, value in smart_defaults.items():
            if hass.states.get(entity_id):
                state = hass.states.get(entity_id)
                try:
                    if not state.state or float(state.state) == 0:
                        await safe_service_call(
                            hass, "input_number", "set_value",
                            {"entity_id": entity_id, "value": value}
                        )
                except Exception:
                    pass
        
        # Set smart select defaults
        select_defaults = {
            f"input_select.{dog_name}_health_status": "Gut",
            f"input_select.{dog_name}_mood": "😊 Glücklich",
            f"input_select.{dog_name}_activity_level": "Normal",
            f"input_select.{dog_name}_size_category": "Mittel (10-25kg)",
        }
        
        for entity_id, value in select_defaults.items():
            if hass.states.get(entity_id):
                state = hass.states.get(entity_id)
                if not state.state:
                    await safe_service_call(
                        hass, "input_select", "select_option",
                        {"entity_id": entity_id, "option": value}
                    )
        
        _LOGGER.info("✅ Smart default values set successfully")
        
    except Exception as e:
        _LOGGER.warning("⚠️ Error setting smart defaults: %s", e)


async def async_cleanup_duplicate_entities(hass: HomeAssistant, dog_name: str) -> Dict[str, Any]:
    """Clean up any duplicate entities that might exist."""
    cleanup_result = {
        "duplicates_found": 0,
        "duplicates_removed": 0,
        "cleanup_errors": [],
        "cleaned_entities": []
    }
    
    try:
        all_entities = hass.states.async_all()
        dog_entities = []
        
        for state in all_entities:
            entity_id = state.entity_id
            if dog_name in entity_id.lower():
                dog_entities.append(entity_id)
        
        potential_duplicates = []
        checked_entities = set()
        
        for entity_id in dog_entities:
            if entity_id in checked_entities:
                continue
            
            base_name = entity_id.lower().replace("_1", "").replace("_2", "").replace("_copy", "")
            similar_entities = []
            
            for other_entity in dog_entities:
                if other_entity != entity_id and base_name in other_entity.lower():
                    similar_entities.append(other_entity)
            
            if similar_entities:
                potential_duplicates.append({
                    "base": entity_id,
                    "duplicates": similar_entities
                })
                checked_entities.update([entity_id] + similar_entities)
        
        cleanup_result["duplicates_found"] = len(potential_duplicates)
        
        for duplicate_group in potential_duplicates:
            duplicates_to_remove = duplicate_group["duplicates"]
            
            for duplicate_entity in duplicates_to_remove:
                try:
                    domain = duplicate_entity.split('.')[0]
                    await hass.services.async_call(
                        domain, "remove",
                        {"entity_id": duplicate_entity},
                        blocking=True
                    )
                    cleanup_result["duplicates_removed"] += 1
                    cleanup_result["cleaned_entities"].append(duplicate_entity)
                    _LOGGER.info("Removed duplicate entity: %s", duplicate_entity)
                except Exception as e:
                    error_msg = f"Failed to remove duplicate {duplicate_entity}: {str(e)}"
                    cleanup_result["cleanup_errors"].append(error_msg)
                    _LOGGER.error("❌ %s", error_msg)
        
        _LOGGER.info("Duplicate cleanup completed for %s: %d removed, %d errors", 
                    dog_name, cleanup_result["duplicates_removed"], len(cleanup_result["cleanup_errors"]))
        
        return cleanup_result
        
    except Exception as e:
        _LOGGER.error("Error during duplicate cleanup: %s", e)
        return {
            **cleanup_result,
            "error": str(e)
        }