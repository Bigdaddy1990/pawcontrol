<!-- .gemini/styleguide.md -->
# Paw Control – Home Assistant Integrations-Styleguide

Ziel: saubere, UI-konfigurierbare Integration mit stabilen Entitäten, korrektem Async und Tests. Fokus auf Quality-Scale-Kriterien. (Config Flow, Tests, Devices, Diagnostics). :contentReference[oaicite:1]{index=1}

## Musskriterien

1) **UI-Setup via Config Flow**  
`config_flow.py`, `manifest.json` mit `"config_flow": true`. In der Flow-Logik Unique-ID setzen, Duplikate verhindern, Reauth/Reconfigure unterstützen. :contentReference[oaicite:2]{index=2}

2) **Options/Reconfigure Flow**  
Nutzende müssen Einstellungen später in der UI ändern können. Implementiere `OptionsFlow` bzw. Reconfigure-Flow. :contentReference[oaicite:3]{index=3}

3) **Entitäten & Geräte korrekt registrieren**  
Jede Entität braucht `unique_id`; Geräteinfo vollständig befüllen (Hersteller, Modell, HW/SW-Version, Konfig-URL). Nutze Entity- und Device-Registry APIs. :contentReference[oaicite:4]{index=4}

4) **Koordinator-Architektur**  
Polling/Bündelung mit `DataUpdateCoordinator` + `CoordinatorEntity`. `_async_setup` nutzen, unnötige Callbacks vermeiden, sinnvolles `update_interval`. :contentReference[oaicite:5]{index=5}

5) **Async-Sauberkeit**  
Kein Blocking-I/O im Event-Loop, Threads korrekt nutzen; neue async-APIs verwenden (`async_register_static_paths`, `dt_util.async_get_time_zone`). :contentReference[oaicite:6]{index=6}

6) **Übersetzungen**  
`strings.json` definieren, UI-Texte unter `config.*`. Für Custom-Integrationen `translations/<lang>.json` pflegen (BCP47). Core nutzt Lokalise. :contentReference[oaicite:7]{index=7}

7) **Diagnostics & System Health**  
Diagnostik mit Redaction sensibler Daten bereitstellen und System-Health implementieren. :contentReference[oaicite:8]{index=8}

8) **Discovery**  
Wenn passend, Zeroconf/SSDP/DHCP hinterlegen und Flows aus Discovery starten; ServiceInfo-Imports aktuell halten. :contentReference[oaicite:9]{index=9}

9) **Branding**  
Logos/Icons in `home-assistant/brands` pflegen; HACS fordert Marken-Assets. :contentReference[oaicite:10]{index=10}

## Entitätsregeln

- **Device/State-Class, Units** korrekt setzen; Sensor-Validierungen beachten. EntityDescription nutzen. :contentReference[oaicite:11]{index=11}  
- **Registry-Eigenschaften** nur bei gesetzter `unique_id` wirksam. Disabled-Flags respektieren. :contentReference[oaicite:12]{index=12}

## Tests

- **100 % Testabdeckung für den Config-Flow** inkl. Fehlerpfade und Recovery. :contentReference[oaicite:13]{index=13}  
- **Pytest-Setup**: `pytest-homeassistant-custom-component` oder `pytest-homeassistant`, Standard-Fixtures (`hass`, `MockConfigEntry`), Teststruktur gemäß Dev-Docs. :contentReference[oaicite:14]{index=14}

## Quality Scale Zielbild

Anstreben: **Bronze→Silver**. Erfülle die Regeln iterativ: Config-Flow, Geräte, Diagnostik, Reconfigure, Tests, Doku. :contentReference[oaicite:15]{index=15}

## Review-Heuristik für Gemini

Kurz, klar, Fix-Vorschlag als Diff. Priorität: Sicherheit/Logik > Performance > UX > Style.

- Kein YAML-Setup für neue Integrationen empfehlen. UI-Flows only. :contentReference[oaicite:16]{index=16}
- Blockierendes I/O, falsch genutzte Threads, veraltete Sync-APIs markieren. :contentReference[oaicite:17]{index=17}
- Fehlende `unique_id`/Device-Info, falsche Device/State-Classes, fehlerhafte Units call-out. :contentReference[oaicite:18]{index=18}
- Koordinator nicht genutzt oder falsch konfiguriert → Vorschlag auf `DataUpdateCoordinator` + `CoordinatorEntity`. :contentReference[oaicite:19]{index=19}
- Fehlende Reconfigure/Options-Flows und Diagnostics/System-Health monieren. :contentReference[oaicite:20]{index=20}
- Discovery-Keys fehlen bei discovery-fähigen Geräten. :contentReference[oaicite:21]{index=21}

## PR-Erwartungen

Kleine PRs, klare Motivation, Risiken, Rollback, Migrationsschritte. Tests und Übersetzungen im selben PR aktualisieren. Ziel: „ship small, ship often“.  
