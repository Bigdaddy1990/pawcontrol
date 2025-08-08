"""HelperFactory für PawControl – Vollständig dynamisches Helper-Management."""

from homeassistant.helpers.storage import Store
import logging

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = "pawcontrol_helpers"

class HelperFactory:
    """Zentrale Factory für alle Helper-Entities pro Hund und Modul."""

    def __init__(self, hass):
        self.hass = hass
        self._stores = {}  # Pro Hund ein Store
        self._created_helpers = {}  # dog_id: {entity_id: config}

    async def async_initialize(self, dog_id):
        if dog_id not in self._stores:
            self._stores[dog_id] = Store(
                self.hass, STORAGE_VERSION, f"{STORAGE_KEY_PREFIX}_{dog_id}")
        data = await self._stores[dog_id].async_load()
        self._created_helpers[dog_id] = data.get("helpers", {}) if data else {}

    async def sync_helpers(self, dog_id: str, helpers: list[dict]):
        """Synchronisiert alle benötigten Helper für einen Hund."""
        await self.async_initialize(dog_id)
        existing = set(self._created_helpers.get(dog_id, {}))
        needed = set(h["entity_id"] for h in helpers)
        to_remove = existing - needed
        to_add = needed - existing

        for entity_id in to_remove:
            await self._remove_helper(dog_id, entity_id)
        for h in helpers:
            if h["entity_id"] in to_add:
                await self._create_helper(dog_id, h)
        await self._save_helpers(dog_id)

    async def _create_helper(self, dog_id: str, h: dict):
        entity_id = h["entity_id"]
        config = h.copy()
        self._created_helpers.setdefault(dog_id, {})[entity_id] = config
        # Virtuelle Entity im State-Backend erzeugen
        state = h.get("initial", None)
        attributes = {
            "friendly_name": h.get("name"),
            "icon": h.get("icon", "mdi:help-circle"),
        }
        # Typ-spezifische Attribute
        if h["type"] == "input_number":
            attributes.update({k: h[k] for k in ("min", "max", "step", "mode") if k in h})
            if "unit_of_measurement" in h:
                attributes["unit_of_measurement"] = h["unit_of_measurement"]
        if h["type"] == "input_select":
            attributes["options"] = h["options"]
        if h["type"] == "input_text":
            attributes["min"] = h.get("min", 0)
            attributes["max"] = h.get("max", 100)
        if h["type"] == "input_datetime":
            attributes["has_date"] = h.get("has_date", True)
            attributes["has_time"] = h.get("has_time", True)
        self.hass.states.async_set(entity_id, state, attributes)
        _LOGGER.info(f"Helper erstellt: {entity_id} ({config['type']})")

    async def _remove_helper(self, dog_id: str, entity_id: str):
        if entity_id in self._created_helpers.get(dog_id, {}):
            del self._created_helpers[dog_id][entity_id]
            self.hass.states.async_remove(entity_id)
            _LOGGER.info(f"Helper entfernt: {entity_id}")

    async def _save_helpers(self, dog_id):
        await self._stores[dog_id].async_save({"helpers": self._created_helpers[dog_id]})

    async def remove_all_helpers(self, dog_id):
        """Entfernt alle Helper eines Hundes."""
        for entity_id in list(self._created_helpers.get(dog_id, {})):
            await self._remove_helper(dog_id, entity_id)
        await self._save_helpers(dog_id)
