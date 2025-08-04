
import logging
from homeassistant.core import HomeAssistant
from .modules.setup.installation_manager import InstallationManager
from .modules.setup.config_helpers import get_all_configured_dogs
from .modules.activity.automation_generator import generate_all_automations

_LOGGER = logging.getLogger(__name__)

class SetupCoordinator:
    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self.dog_configs = []

    async def async_setup(self):
        _LOGGER.info("🐾 PawControl SetupCoordinator: Starte vollständige Initialisierung")

        # 1. Konfiguration auslesen
        self.dog_configs = await get_all_configured_dogs(self.hass)
        if not self.dog_configs:
            _LOGGER.warning("Keine Hunde im Setup definiert – Setup wird abgebrochen.")
            return

        # 2. Installation aller Module + Helper pro Hund
        for dog in self.dog_configs:
            await InstallationManager.setup_dog_modules(self.hass, dog)

        # 3. Automationen neu generieren (Reminder, Reset, etc.)
        await generate_all_automations(self.hass, self.dog_configs)

        # 4. Optional: Bereinigung veralteter Helper
        await InstallationManager.cleanup_obsolete_helpers(self.hass, self.dog_configs)

        _LOGGER.info("✅ PawControl Setup abgeschlossen.")
