<!-- .gemini/styleguide.md -->
# PawControl – HA-Styleguide für Gemini Reviews

**Domain:** `pawcontrol` • **Plattformen:** sensor, binary_sensor, button, switch, number, select, text, device_tracker, date, datetime. **Repo-Status:** vorhanden: `config_flow.py`, `options_flow.py`, `diagnostics.py`, `discovery.py`, `coordinator.py`, `services.yaml`; **fehlt:** `system_health.py` → Patch unten.

## Muss nach HA-Docs
1) **Config Flow + Options Flow**  
UI-Setup Pflicht. Unique-ID setzen. Reauth/Reconfigure unterstützen. OptionsFlow für spätere Änderungen bereitstellen. :contentReference[oaicite:1]{index=1}

2) **Koordinator-Architektur**  
`DataUpdateCoordinator` nutzen, `_async_setup` für einmalige Async-Initialisierung verwenden, unnötige Callbacks vermeiden. Entitäten von `CoordinatorEntity` ableiten. :contentReference[oaicite:2]{index=2}

3) **Entities korrekt registrieren**  
Jede Entität hat `unique_id`; `device_info` nur mit `unique_id` wirksam. State/Device-Class und `suggested_unit_of_measurement` sauber setzen. Unverfügbare Daten als `unavailable/unknown` abbilden. :contentReference[oaicite:3]{index=3}

4) **Diagnostics + System Health**  
Diagnostik mit Redaction sensibler Daten liefern. Zusätzlich `system_health.py` implementieren. :contentReference[oaicite:4]{index=4}

5) **Discovery im Manifest aktuell halten**  
Zeroconf/SSDP/DHCP/Bluetooth korrekt pflegen; neue `ServiceInfo`-Imports beachten. Für Bluetooth `connectable` passend wählen. :contentReference[oaicite:5]{index=5}

6) **Tests**  
100 % Testabdeckung für den Config-Flow inkl. Recovery-Pfade. :contentReference[oaicite:6]{index=6}

## Gemini-Review-Regeln für dieses Repo
- Blockierendes I/O im Event-Loop, veraltete Sync-APIs, fehlendes `_async_setup` call-out mit Fix-Diff. :contentReference[oaicite:7]{index=7}  
- Fehlende/instabile `unique_id`, unvollständige `device_info`, falsche State/Device-Class oder Units markieren. :contentReference[oaicite:8]{index=8}  
- Markiere fehlendes **System Health** als Pflicht-Nachbesserung. Diff unten nutzen. :contentReference[oaicite:9]{index=9}  
- Manifest-Discovery verifizieren; bei alten `ServiceInfo`-Imports Fix vorschlagen. :contentReference[oaicite:10]{index=10}

## Patches „ready to drop“

### 1) `system_health.py` hinzufügen
```python
# custom_components/pawcontrol/system_health.py
from __future__ import annotations
from typing import Any
from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

DOMAIN = "pawcontrol"

@callback
def async_register(hass: HomeAssistant, register: system_health.SystemHealthRegistration) -> None:
    register.async_register_info(system_health_info)

async def system_health_info(hass: HomeAssistant) -> dict[str, Any]:
    # Beispiel: erste Config-Entry prüfen
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    runtime = getattr(entry, "runtime_data", None)
    api = getattr(runtime, "api", None)
    return {
        "can_reach_backend": system_health.async_check_can_reach_url(
            hass, getattr(api, "base_url", "https://example.invalid")
        ),
        "remaining_quota": getattr(runtime, "remaining_quota", "unknown"),
    }
