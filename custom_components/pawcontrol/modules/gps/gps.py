"""GPS-Modul für Paw Control – Verwaltung, Helper, Setup/Teardown."""

from homeassistant.helpers.entity import Entity

from .const import *
from .utils import call_service

async def setup_gps(hass, entry):
    """Initialisiert GPS-Sensor und zugehörige Helper."""
    dog = entry.data[CONF_DOG_NAME]
    sensor_id = f"sensor.{dog}_gps_location"
    helper_id = f"input_boolean.{dog}_gps_active"

    # Helper für GPS-Status anlegen (falls nicht vorhanden)
    if not hass.states.get(helper_id):
        await call_service(
            hass,
            "input_boolean",
            "create",
            {"name": f"{dog} GPS aktiv", "entity_id": helper_id},
        )

    # Sensor für GPS-Position initialisieren (Platzhalter – hier kommt echte Logik oder device_tracker rein)
    hass.states.async_set(sensor_id, DEFAULT_GPS_LOCATION, {"friendly_name": f"{dog} GPS-Position"})

async def teardown_gps(hass, entry):
    """Entfernt GPS-Sensor und zugehörige Helper."""
    dog = entry.data[CONF_DOG_NAME]
    sensor_id = f"sensor.{dog}_gps_location"
    helper_id = f"input_boolean.{dog}_gps_active"

    # GPS-Helper entfernen
    if hass.states.get(helper_id):
        await call_service(hass, "input_boolean", "remove", {"entity_id": helper_id})
    # GPS-Sensor entfernen
    hass.states.async_remove(sensor_id)

async def ensure_helpers(hass, opts):
    """Stellt sicher, dass GPS-Helper existieren (nachträgliche Reparatur)."""
    dog = opts[CONF_DOG_NAME]
    helper_id = f"input_boolean.{dog}_gps_active"
    if not hass.states.get(helper_id):
        await call_service(
            hass,
            "input_boolean",
            "create",
            {"name": f"{dog} GPS aktiv", "entity_id": helper_id},
        )
