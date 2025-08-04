"""Gesundheitsmodul für Paw Control – Sensoren, Helper, Setup/Teardown."""

from .const import *

async def setup_health(hass, entry):
    """Initialisiert Gesundheits-Sensoren und Helper."""
    dog = entry.data[CONF_DOG_NAME]
    # Haupt-Sensor für Gesundheitsstatus
    sensor_id = f"sensor.{dog}_health"
    hass.states.async_set(
        sensor_id,
        DEFAULT_HEALTH_STATUS,
        {
            "friendly_name": f"{dog} Gesundheit",
            "symptoms": "",
            "medication": "",
            "weight": entry.data.get(CONF_DOG_WEIGHT, 0),
            "weight_history": [],
        }
    )
    # Helper für Symptome, Medikamente etc.
    symptom_id = f"input_text.{dog}_symptoms"
    med_id = f"input_text.{dog}_medication"
    weight_id = f"input_number.{dog}_weight"

    # Helper anlegen, falls nicht vorhanden
    if not hass.states.get(symptom_id):
        await hass.services.async_call(
            "input_text", "create",
            {"name": f"{dog} Symptome", "entity_id": symptom_id, "max": 120},
            blocking=True,
        )
    if not hass.states.get(med_id):
        await hass.services.async_call(
            "input_text", "create",
            {"name": f"{dog} Medikamente", "entity_id": med_id, "max": 120},
            blocking=True,
        )
    if not hass.states.get(weight_id):
        await hass.services.async_call(
            "input_number", "create",
            {"name": f"{dog} Gewicht", "entity_id": weight_id, "min": 0, "max": 150, "step": 0.1},
            blocking=True,
        )

async def teardown_health(hass, entry):
    """Entfernt alle Gesundheits-Sensoren und Helper."""
    dog = entry.data[CONF_DOG_NAME]
    sensor_id = f"sensor.{dog}_health"
    symptom_id = f"input_text.{dog}_symptoms"
    med_id = f"input_text.{dog}_medication"
    weight_id = f"input_number.{dog}_weight"

    hass.states.async_remove(sensor_id)
    # Helper entfernen, falls sie existieren
    for helper, domain in [
        (symptom_id, "input_text"),
        (med_id, "input_text"),
        (weight_id, "input_number"),
    ]:
        if hass.states.get(helper):
            await hass.services.async_call(
                domain, "remove",
                {"entity_id": helper},
                blocking=True,
            )

async def ensure_helpers(hass, opts):
    """Stellt sicher, dass alle Health-Helper existieren."""
    dog = opts[CONF_DOG_NAME]
    symptom_id = f"input_text.{dog}_symptoms"
    med_id = f"input_text.{dog}_medication"
    weight_id = f"input_number.{dog}_weight"
    for eid, domain, params in [
        (symptom_id, "input_text", {"name": f"{dog} Symptome", "max": 120}),
        (med_id, "input_text", {"name": f"{dog} Medikamente", "max": 120}),
        (weight_id, "input_number", {"name": f"{dog} Gewicht", "min": 0, "max": 150, "step": 0.1}),
    ]:
        if not hass.states.get(eid):
            await hass.services.async_call(domain, "create", {**params, "entity_id": eid}, blocking=True)
