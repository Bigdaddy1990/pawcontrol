from __future__ import annotations
import logging
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.persistent_notification import create as pn_create
from homeassistant.helpers import issue_registry as ir

_LOGGER = logging.getLogger(__name__)
INSTALL_ISSUE = "install_helper"

INSTALL_TEXT = (
    "🧩 <b>Paw Control – Installationshilfe</b>\n"
    "1) Öffne <i>Einstellungen → Geräte & Dienste → Integrationen</i> und füge <b>Paw Control</b> hinzu.\n"
    "2) Wähle Hunde, Module und Benachrichtigungen im Einrichtungsdialog.\n"
    "3) Optional: Lege im UI ein Dashboard an oder nutze die vorgeschlagenen Karten (siehe README).\n"
    "4) Prüfe Reparatur-Hinweise für fehlende Sensoren/Geräte.\n"
    "Mehr Infos im README der Integration."
)

def create_install_issue(hass: HomeAssistant, entry: ConfigEntry) -> None:
    ir.async_create_issue(
        hass,
        domain="pawcontrol",
        issue_id=f"{entry.entry_id}_{INSTALL_ISSUE}",
        is_fixable=False,
        severity=ir.IssueSeverity.INFO,
        translation_key=None,
        learn_more_url="https://github.com/Bigdaddy1990/paw_control#readme",
    )

async def show_install_help(hass: HomeAssistant, entry: ConfigEntry) -> None:
    pn_create(hass, INSTALL_TEXT, title="Paw Control – Installationshilfe")

def register_install_service(hass: HomeAssistant, entry: ConfigEntry) -> None:
    async def _svc(call: ServiceCall):
        await show_install_help(hass, entry)
    # idempotent register
    try:
        hass.services.async_remove("pawcontrol", "show_install_help")
    except Exception:
        pass
    hass.services.async_register("pawcontrol", "show_install_help", _svc)
