from homeassistant.core import HomeAssistant

FEEDING_TYPE_MAP = {
    "Frühstück": "morning",
    "Mittagessen": "noon",
    "Abendessen": "evening",
    "Leckerli": "snack"
}

def get_feeding_helpers_config(feed_key: str):
    return {
        "input_datetime": {
            f"feed_{feed_key}_time": {
                "name": f"🍽️ {feed_key.capitalize()}szeit",
                "has_time": True
            }
        },
        "input_number": {
            f"feed_{feed_key}_tolerance": {
                "name": f"⏱️ Erinnerung nach (Min) für {feed_key}",
                "min": 5,
                "max": 180,
                "step": 5
            }
        },
        "input_boolean": {
            f"feed_{feed_key}_confirmed": {
                "name": f"✅ {feed_key.capitalize()} erledigt"
            }
        }
    }

async def create_feeding_helpers(hass: HomeAssistant) -> dict:
    feeding_selection = hass.states.get("input_select.pawcontrol_feeding_modes")
    if not feeding_selection:
        return {}

    selected = feeding_selection.state.split(",")
    config = {}

    for label in selected:
        label = label.strip()
        if not label or label not in FEEDING_TYPE_MAP:
            continue

        feed_key = FEEDING_TYPE_MAP[label]
        block = get_feeding_helpers_config(feed_key)

        for domain, entities in block.items():
            config.setdefault(domain, {}).update(entities)

    return config


from .schema import SETUP_SCHEMA

async def apply_setup_schema(hass):
    config_result = {}

    for key, schema in SETUP_SCHEMA.items():
        if schema["type"] == "bool":
            state = hass.states.get(f"input_boolean.pawcontrol_{key}")
            config_result[key] = state.state == "on" if state else False

        elif schema["type"] == "choice":
            state = hass.states.get(f"input_select.pawcontrol_{key}")
            config_result[key] = state.state if state else schema.get("default")

        elif schema["type"] == "multi_select":
            state = hass.states.get(f"input_select.pawcontrol_{key}")
            config_result[key] = [s.strip() for s in state.state.split(",")] if state else []

        elif schema["type"] == "multi_bool":
            result = {}
            for opt in schema["options"]:
                slug = opt.lower().replace(" ", "_")
                state = hass.states.get(f"input_boolean.pawcontrol_{key}_{slug}")
                result[slug] = state.state == "on" if state else False
            config_result[key] = result

        elif schema["type"] == "sensor_select":
            state = hass.states.get(f"input_select.pawcontrol_{key}")
            config_result[key] = state.state if state else None

        elif schema["type"] == "notify_target":
            state = hass.states.get(f"input_select.pawcontrol_{key}")
            config_result[key] = state.state if state else "notify.notify"

        elif schema["type"] == "list":
            # Nur Platzhalter – dynamische Verarbeitung nötig
            config_result[key] = []

    return config_result

from homeassistant.helpers.entity_registry import async_get as get_entity_registry

async def sync_feeding_helpers(hass: HomeAssistant) -> None:
    current_state = hass.states.get("input_select.pawcontrol_feeding_modes")
    if not current_state:
        return

    selected = [s.strip() for s in current_state.state.split(",") if s.strip()]
    selected_keys = [FEEDING_TYPE_MAP.get(s) for s in selected if s in FEEDING_TYPE_MAP]

    registry = await get_entity_registry(hass)
    all_entities = list(registry.entities.keys())

    for feed_key in FEEDING_TYPE_MAP.values():
        prefix = f"feed_{feed_key}"
        should_exist = feed_key in selected_keys

        for domain, suffix in [
            ("input_datetime", "_time"),
            ("input_number", "_tolerance"),
            ("input_boolean", "_confirmed"),
        ]:
            entity_id = f"{domain}.{prefix}{suffix}"

            # Erstellen falls nötig
            if should_exist and not hass.states.get(entity_id):
                if domain == "input_boolean":
                    hass.states.async_set(entity_id, "off")
                elif domain == "input_number":
                    hass.states.async_set(entity_id, 60, {"min": 5, "max": 180, "step": 5})
                elif domain == "input_datetime":
                    hass.states.async_set(entity_id, "07:00:00", {"has_time": True})

            # Löschen falls deaktiviert
            elif not should_exist and entity_id in all_entities:
                try:
                    await registry.async_remove(entity_id)
                    _LOGGER.info(f"Entfernt nicht mehr genutzten Helper: {entity_id}")
                except Exception as e:
                    _LOGGER.warning(f"Konnte {entity_id} nicht entfernen: {e}")

async def get_dog_list(hass: HomeAssistant) -> list[str]:
    state = hass.states.get("input_number.pawcontrol_dog_count")
    try:
        count = int(float(state.state)) if state else 1
    except:
        count = 1

    dogs = []
    for i in range(1, count + 1):
        name_state = hass.states.get(f"input_text.pawcontrol_dog_{i}_name")
        name = name_state.state.strip() if name_state else f"Hund{i}"
        if name:
            dogs.append(name)

    return dogs

async def sync_all_dog_helpers(hass: HomeAssistant) -> None:
    dogs = await get_dog_list(hass)
    feeding_modes_state = hass.states.get("input_select.pawcontrol_feeding_modes")
    active_modes = [s.strip().lower().replace(" ", "_") for s in feeding_modes_state.state.split(",")] if feeding_modes_state else []

    registry = await get_entity_registry(hass)
    all_entities = list(registry.entities.keys())

    def make_id(domain, base): return f"{domain}.{base}"

    for dog in dogs:
        slug = dog.lower().replace(" ", "_")

        for mode in active_modes:
            prefix = f"feed_{slug}_{mode}"
            helpers = [
                ("input_datetime", f"{prefix}_time", {"has_time": True}),
                ("input_number", f"{prefix}_tolerance", {"min": 5, "max": 180, "step": 5}),
                ("input_boolean", f"{prefix}_confirmed", {})
            ]

            for domain, entity, attrs in helpers:
                eid = make_id(domain, entity)
                if not hass.states.get(eid):
                    try:
                        hass.states.async_set(eid, "off" if domain == "input_boolean" else 60, attrs)
                    except:
                        _LOGGER.warning(f"Konnte {eid} nicht erstellen.")

        
        # Gesundheitsmodul (optional pro Hund)
        health_config = hass.states.get("input_text.pawcontrol_setup_dogs_health_config")
        try:
            import json
            health_enabled_dogs = json.loads(health_config.state) if health_config else {}
        except:
            health_enabled_dogs = {}

        if health_enabled_dogs.get(dog, False):
            health_helpers = [
                ("input_number", f"health_{slug}_weight", {"min": 1, "max": 100, "step": 0.1, "unit_of_measurement": "kg"}),
                ("input_text", f"health_{slug}_medications", {"max": 200}),
                ("input_text", f"health_{slug}_vaccinations", {"max": 200})
            ]

            for domain, entity, attrs in health_helpers:
                eid = make_id(domain, entity)
                if not hass.states.get(eid):
                    try:
                        hass.states.async_set(eid, 0 if domain == "input_number" else "", attrs)
                    except:
                        _LOGGER.warning(f"Gesundheits-Helper {eid} konnte nicht erstellt werden.")
    

    # Entferne verwaiste Helfer
    for entity in all_entities:
        if any(entity.startswith(f"{d}_{m}") for d in ["feed"] for m in active_modes):
            if not any(dog.lower().replace(" ", "_") in entity for dog in dogs):
                try:
                    await registry.async_remove(entity)
                    _LOGGER.info(f"Entfernt veralteten Hund-Helper: {entity}")
                except Exception as e:
                    _LOGGER.warning(f"Entfernung fehlgeschlagen: {entity} ({e})")

import yaml
import os

DASHBOARD_PATH = "dashboards/pawcontrol_generated_dashboard.yaml"

async def generate_dashboard_view(hass: HomeAssistant) -> None:
    dogs = await get_dog_list(hass)
    feeding_modes_state = hass.states.get("input_select.pawcontrol_feeding_modes")
    active_modes = [s.strip().lower().replace(" ", "_") for s in feeding_modes_state.state.split(",")] if feeding_modes_state else []

    def dog_card_block(name):
        slug = name.lower().replace(" ", "_")
        cards = [{"type": "custom:mushroom-title-card", "title": f"🐶 {name}"}]

        for mode in active_modes:
            cards.extend([
                {
                    "type": "custom:mushroom-entity-card",
                    "entity": f"input_datetime.feed_{slug}_{mode}_time",
                    "name": f"{mode.capitalize()} – Uhrzeit",
                    "secondary_info": "last-changed"
                },
                {
                    "type": "custom:mushroom-entity-card",
                    "entity": f"input_boolean.feed_{slug}_{mode}_confirmed",
                    "name": "Gefüttert?",
                    "tap_action": {"action": "toggle"}
                },
                {
                    "type": "custom:mushroom-entity-card",
                    "entity": f"input_number.feed_{slug}_{mode}_tolerance",
                    "name": "Toleranz (Min.)"
                }
            ])

        
        # Gassi-Modul UI
        gassi_config_state = hass.states.get("input_text.pawcontrol_setup_gassi_trigger_config")
        try:
            import json
            gassi_enabled = json.loads(gassi_config_state.state) if gassi_config_state else {}
        except:
            gassi_enabled = {}

        if name in gassi_enabled:
            cards.extend([
                {
                    "type": "custom:mushroom-entity-card",
                    "entity": f"input_boolean.gassi_{slug}_active",
                    "name": "Gassi gestartet?",
                    "icon": "mdi:dog",
                    "tap_action": {"action": "toggle"}
                },
                {
                    "type": "custom:mushroom-entity-card",
                    "entity": f"input_datetime.gassi_{slug}_last",
                    "name": "Letztes Gassi",
                    "icon": "mdi:calendar-clock"
                }
            ])
    
        return {
            "type": "vertical-stack",
            "cards": cards
        }

    view = {
        "title": "PawControl 🐾",
        "views": [{
            "title": "Hunde",
            "path": "pawcontrol",
            "icon": "mdi:dog",
            "type": "custom:masonry-layout",
            "cards": [dog_card_block(d) for d in dogs]
        }]
    }

    folder = hass.config.path("dashboards")
    os.makedirs(folder, exist_ok=True)
    path = hass.config.path(DASHBOARD_PATH)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(view, f, allow_unicode=True, sort_keys=False)

    _LOGGER.info(f"PawControl Dashboard generiert unter {path}")

async def register_dashboard_view(hass: HomeAssistant) -> None:
    mode = hass.states.get("input_select.pawcontrol_dashboard_mode")
    if not mode or mode.state != "vollständig":
        return

    dashboard_path = hass.config.path("dashboards/pawcontrol_generated_dashboard.yaml")
    if not os.path.exists(dashboard_path):
        _LOGGER.warning("Dashboard-Datei nicht gefunden, Ansicht kann nicht aktiviert werden.")
        return

    try:
        yaml_config = {
            "mode": "yaml",
            "title": "PawControl 🐾",
            "icon": "mdi:dog",
            "filename": "dashboards/pawcontrol_generated_dashboard.yaml",
            "show_in_sidebar": True,
            "require_admin": False
        }

        # Dashboard eintragen
        await hass.services.async_call(
            "frontend",
            "set_dashboard",
            {
                "url_path": "pawcontrol",
                **yaml_config
            },
            blocking=True
        )
        _LOGGER.info("PawControl Dashboard erfolgreich als UI-Ansicht registriert.")

    except Exception as e:
        _LOGGER.error(f"Fehler bei der Dashboard-Registrierung: {e}")
