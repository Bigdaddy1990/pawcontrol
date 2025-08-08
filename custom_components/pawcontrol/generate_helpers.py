def get_helpers_for_module(module, dog_id, dog_config):
    """Liefert eine Liste von Helper-Configs für ein Modul und einen Hund."""
    if module == "feeding":
        return [
            {"type": "input_boolean", "entity_id": f"input_boolean.pawcontrol_{dog_id}_fed_breakfast", "name": "Frühstück gefüttert", "icon": "mdi:food-apple", "initial": False},
            {"type": "input_boolean", "entity_id": f"input_boolean.pawcontrol_{dog_id}_fed_lunch", "name": "Mittag gefüttert", "icon": "mdi:food", "initial": False},
            {"type": "input_boolean", "entity_id": f"input_boolean.pawcontrol_{dog_id}_fed_dinner", "name": "Abend gefüttert", "icon": "mdi:food-variant", "initial": False},
            {"type": "input_datetime", "entity_id": f"input_datetime.pawcontrol_{dog_id}_last_feeding", "name": "Letzte Fütterung", "icon": "mdi:clock", "has_date": True, "has_time": True},
            {"type": "input_number", "entity_id": f"input_number.pawcontrol_{dog_id}_daily_food_amount", "name": "Futtermenge täglich", "icon": "mdi:weight", "min": 50, "max": 2000, "step": 10, "mode": "slider", "unit_of_measurement": "g", "initial": 500},
            {"type": "counter", "entity_id": f"counter.pawcontrol_{dog_id}_meals_today", "name": "Mahlzeiten heute", "icon": "mdi:counter", "initial": 0},
        ]
    if module == "walk":
        return [
            {"type": "input_boolean", "entity_id": f"input_boolean.pawcontrol_{dog_id}_walk_in_progress", "name": "Spaziergang läuft", "icon": "mdi:dog-service", "initial": False},
            {"type": "counter", "entity_id": f"counter.pawcontrol_{dog_id}_walks_today", "name": "Spaziergänge heute", "icon": "mdi:counter", "initial": 0},
            {"type": "input_datetime", "entity_id": f"input_datetime.pawcontrol_{dog_id}_last_walk", "name": "Letzter Spaziergang", "icon": "mdi:clock", "has_date": True, "has_time": True},
            {"type": "input_number", "entity_id": f"input_number.pawcontrol_{dog_id}_walk_distance_today", "name": "Distanz heute", "icon": "mdi:map-marker-distance", "min": 0, "max": 20, "step": 0.1, "mode": "slider", "unit_of_measurement": "km", "initial": 0},
        ]
    if module == "health":
        return [
            {"type": "input_number", "entity_id": f"input_number.pawcontrol_{dog_id}_weight", "name": "Gewicht", "icon": "mdi:weight", "min": 1, "max": 90, "step": 0.1, "mode": "box", "unit_of_measurement": "kg", "initial": dog_config.get("dog_weight", 20)},
            {"type": "input_number", "entity_id": f"input_number.pawcontrol_{dog_id}_temperature", "name": "Temperatur", "icon": "mdi:thermometer", "min": 36, "max": 42, "step": 0.1, "mode": "box", "unit_of_measurement": "°C", "initial": 38.5},
            {"type": "input_text", "entity_id": f"input_text.pawcontrol_{dog_id}_symptoms", "name": "Symptome", "icon": "mdi:alert", "min": 0, "max": 100, "initial": ""},
        ]
    # Hier kannst du beliebig weitere Module ergänzen
    return []
