"""Setup coordinator - angepasst für Helper-Integration."""
import logging
from homeassistant.core import HomeAssistant
from .helpers.config import ConfigHelper
from .helpers.entity import EntityHelper

_LOGGER = logging.getLogger(__name__)

class SetupCoordinator:
    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self.dog_configs = []

    async def async_setup(self):
        _LOGGER.info("🐾 PawControl SetupCoordinator: Starte vollständige Initialisierung")

        # 1. Konfiguration auslesen über ConfigHelper
        config_helper = ConfigHelper(self.hass, None)  # Entry wird später gesetzt
        self.dog_configs = await config_helper.get_all_configured_dogs()
        
        if not self.dog_configs:
            _LOGGER.warning("Keine Hunde im Setup definiert – Setup wird abgebrochen.")
            return

        # 2. Installation aller Module + Helper pro Hund
        for dog_config in self.dog_configs:
            dog_name = dog_config.get("dog_name", "").lower().replace(" ", "_")
            entity_helper = EntityHelper(self.hass, dog_name)
            await entity_helper.setup_all_entities()

        _LOGGER.info("✅ PawControl Setup abgeschlossen.")
