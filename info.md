# 🐕 Paw Control – Home Assistant Companion for Multi-Dog Households

Paw Control is a custom HACS integration that focuses on reliable automation
and monitoring for dogs that are already represented inside Home Assistant. The
integration keeps configuration and runtime logic aligned with Home
Assistant’s architecture guidelines: a config flow provisions helpers and
scripts, a shared `DataUpdateCoordinator` orchestrates module adapters, and all
HTTP calls reuse Home Assistant’s managed aiohttp session.

## Überblick über die Funktionen

### Geführte Einrichtung & Modulwahl
- Der mehrstufige Config Flow legt je Hund Stammdaten an, aktiviert Module wie
  Fütterung, GPS, Garten oder Besuchsmodus und verzweigt bei Bedarf direkt in
  die passenden Detaildialoge (z. B. GPS- oder Fütterungsparameter).
- Im Anschluss ordnet die Modulkonfiguration vorhandene Entitäten zu
  (Personen, Geräte-Tracker, Türsensoren, Wetter-Entity) und erlaubt den
  Import externer API-Endpunkte, falls ein Begleitgerät angebunden werden
  soll.
- Helfer wie `input_boolean`, `input_datetime` und Counter werden automatisch
  erzeugt; fehlende Assets lassen sich im Options-Flow nachpflegen.

### Laufzeitmodule & Koordinator
- Der `PawControlCoordinator` bündelt alle Hundedaten und startet pro Modul
  passende Adapter (Feeding, Walk, GPS, Garden, Weather). Dadurch greifen alle
  Plattformen konsistent auf dieselbe Datenbasis zu.
- Die Modul-Adapter cachen Ergebnisse, nutzen bei Bedarf den Geräte-API-Client
  und liefern strukturierte Payloads für die Sensorplattformen.
- Laufzeitmetriken für Statistik- und Besuchsflows werden per `perf_counter`
  erfasst; die aktuellen Benchmarks sind im Performance-Anhang dokumentiert.
  So lässt sich der aktuelle Bronze-Status der Async-Disziplin transparent nachvollziehen.

### Benachrichtigungen & Webhooks
- Der `PawControlNotificationManager` bündelt Push-Nachrichten, Personenerkennung,
  Rückfragen-Logik und Webhook-Handler mit Ratelimits, Caching und optionaler
  Signaturprüfung.
- Eigene Skripte, Buttons und Services (z. B. Testbenachrichtigungen) greifen
  auf dieselbe Infrastruktur zurück, wodurch Rückfragen oder Quittierungen für
  mehrere Benutzer synchron bleiben.

### Besuchsmodus & temporäre Hunde
- Besuchsstatus wird per Service, Switch und Button verwaltet; der
  Datenmanager speichert Metadaten wie Besuchername oder reduzierte Alarme und
  die Binary-Sensor-Plattform stellt den Status dar.
- Schritt-für-Schritt-Abläufe für Gäste-, Türsensor- und Benachrichtigungs-
  Workflows sind in der Produktionsdokumentation zusammengefasst.【F:docs/production_integration_documentation.md†L309-L321】

### Wetter- und Gesundheitsauswertung
- Der `WeatherHealthManager` analysiert Forecast-Daten einer konfigurierten
  Wetter-Entity, berechnet Health-Scores und schlägt Aktivitätsfenster vor; die
  Ergebnisse fließen über den Weather-Adapter in die Koordinator-Payload ein.
- Ausführliche Automationsbeispiele für wettergesteuerte Benachrichtigungen und
  Schutzmaßnahmen liefert der Weather-Automation-Guide.【F:docs/weather_integration_examples.md†L1-L150】

### Automations-Bausteine
- Der Dashboard-Generator erstellt und pflegt Lovelace-Layouts asynchron, die
  auf Modulebene differenzieren und optional Wetter-Widgets einblenden.
- Das Script-Management legt Benachrichtigungs-, Reset- und Testskripte pro Hund
  an und hält sie bei Moduländerungen aktuell.
- Zusätzliche Plattformen (Sensoren, Schalter, Buttons, Texte, Selektoren) lesen
  koordinierte Daten aus und spiegeln die Helper-States wider.
- Wettergesteuerte Automationen sowie Besucher-spezifische Dashboards lassen
  sich anhand der dokumentierten Rezepte direkt übernehmen.【F:docs/weather_integration_examples.md†L1-L150】【F:docs/production_integration_documentation.md†L309-L321】

### Asynchronität & Sitzungsverwaltung
- Alle HTTP-Helfer validieren über `ensure_shared_client_session`, dass nur die
  von Home Assistant verwaltete aiohttp-Session verwendet wird; die globalen
  Fixtures stellen mit `session_factory` konsistente aiohttp-Doubles bereit und
  Tests decken die Fehlerszenarien für Validator, Adapter, Notification-Manager
  und HTTP-Helfer ab. Ein Pre-Commit-Guard
  (`scripts/enforce_shared_session_guard.py`) verhindert neue `ClientSession()`-
  Instanzen – inklusive aliasierter `aiohttp.client`-Aufrufe – und entdeckt
  zusätzliche Pakete automatisch.【F:tests/conftest.py†L195-L242】【F:tests/unit/test_api_validator.py†L14-L72】【F:tests/unit/test_device_api.py†L96-L157】【F:tests/unit/test_module_adapters.py†L101-L233】【F:tests/unit/test_notifications.py†L1-L180】【F:tests/unit/test_http_client.py†L30-L72】【F:scripts/enforce_shared_session_guard.py†L1-L188】【F:tests/tooling/test_enforce_shared_session_guard.py†L1-L110】
- Blockierende Arbeiten wie GPX-Generierung, Dashboard-Dateizugriffe und die
  Kalorien-Neuberechnung im Notfallmodus werden mit `asyncio.to_thread`
  beziehungsweise `_offload_blocking` ausgelagert, sodass der Event Loop
  reaktionsfähig bleibt.
- Laufzeitstatistiken und Besuchsmodus-Workflows werden mit `perf_counter`
  profiliert; die gemessenen Werte landen sowohl in den Koordinator-Metriken als
  auch im Async-Audit – aktuell mit ~1.66 ms für Statistikzyklen und ~0.67 ms für
  Besucher-Updates –, wodurch CI-Tests Laufzeitregressionen <5 ms (Stats) bzw.
  <3 ms (Besuchsmodus) sofort melden.【F:custom_components/pawcontrol/coordinator.py†L360-L420】【F:custom_components/pawcontrol/coordinator_support.py†L160-L213】【F:custom_components/pawcontrol/data_manager.py†L360-L450】【F:docs/async_dependency_audit.md†L1-L120】【F:generated/perf_samples/latest.json†L1-L17】【F:tests/unit/test_data_manager.py†L1-L118】

## Installation & Inbetriebnahme
1. **Repository zu HACS hinzufügen** (Kategorie Integration) und Paw Control
   installieren.
2. **Config Flow starten** (`Einstellungen → Geräte & Dienste → Integration`)
   und je Hund Module sowie Zuordnungen vornehmen.
3. **Optionale Schritte**:
   - Wetter-Entity, Türsensoren, Benachrichtigungsgeräte im Options-Flow
     nachjustieren.
   - Dashboard in Lovelace hinzufügen oder Skripte in Automationen nutzen.
   - Webhook-Ziele samt Secret konfigurieren, wenn externe Systeme angebunden
     werden sollen.

## Qualitäts- und Supportstatus
- Docstrings und Typannotationen werden projektweit erzwungen; ein Skript
  überwacht die Ruff-Baseline für fehlende Docstrings.
- Der Async-Dependency-Audit dokumentiert alle synchronen Bibliotheken, die
  `_offload_blocking`-Messwerte und die gewählten Mitigationsstrategien.
- Unit-Tests decken die Session-Garantie und Kernadapter ab, benötigen jedoch
  weiterhin ein Home-Assistant-Test-Environment für vollständige Abdeckung.

### Support-Diagnostik
Das Diagnostics-Panel `setup_flags_panel` fasst Analytics-, Backup- und Debug-
Schalter mit lokalisierter Beschriftung zusammen, ergänzt Default-Werte sowie
die ausgehandelte Sprache, damit Support-Teams und Blueprint-Autoren den
Onboarding-Status ohne zusätzliche Parser übernehmen können.【F:custom_components/pawcontrol/diagnostics.py†L90-L214】【F:tests/components/pawcontrol/test_diagnostics.py†L288-L405】
Neben den aktivierten Zählern liefert der Block alle Quellenbezeichnungen aus
`SETUP_FLAG_SOURCE_LABELS` samt Übersetzungs-Keys. `strings.json` führt
dieselben Label- und Quellen-Texte unter `diagnostics.setup_flags_panel`, sodass
Übersetzungs-Workflows die Panels ohne manuelle Exporte nachpflegen können.【F:custom_components/pawcontrol/strings.json†L1396-L1407】

```json
{
  "title": "Setup flags",
  "title_default": "Setup flags",
  "description": "Analytics, backup, and debug logging toggles captured during onboarding and options flows.",
  "description_default": "Analytics, backup, and debug logging toggles captured during onboarding and options flows.",
  "language": "en",
  "flags": [
    {
      "key": "enable_analytics",
      "label": "Analytics telemetry",
      "label_default": "Analytics telemetry",
      "label_translation_key": "component.pawcontrol.diagnostics.setup_flags_panel_flag_enable_analytics",
      "enabled": true,
      "source": "system_settings",
      "source_label": "System settings",
      "source_label_default": "System settings",
      "source_label_translation_key": "component.pawcontrol.diagnostics.setup_flags_panel_source_system_settings"
    },
    {
      "key": "enable_cloud_backup",
      "label": "Cloud backup",
      "label_default": "Cloud backup",
      "label_translation_key": "component.pawcontrol.diagnostics.setup_flags_panel_flag_enable_cloud_backup",
      "enabled": false,
      "source": "default",
      "source_label": "Integration default",
      "source_label_default": "Integration default",
      "source_label_translation_key": "component.pawcontrol.diagnostics.setup_flags_panel_source_default"
    },
    {
      "key": "debug_logging",
      "label": "Debug logging",
      "label_default": "Debug logging",
      "label_translation_key": "component.pawcontrol.diagnostics.setup_flags_panel_flag_debug_logging",
      "enabled": true,
      "source": "options",
      "source_label": "Options flow",
      "source_label_default": "Options flow",
      "source_label_translation_key": "component.pawcontrol.diagnostics.setup_flags_panel_source_options"
    }
  ],
  "enabled_count": 2,
  "disabled_count": 1,
  "source_breakdown": {
    "system_settings": 1,
    "default": 1,
    "options": 1
  },
  "source_labels": {
    "options": "Options flow",
    "system_settings": "System settings",
    "advanced_settings": "Advanced settings",
    "config_entry": "Config entry defaults",
    "default": "Integration default"
  },
  "source_labels_default": {
    "options": "Options flow",
    "system_settings": "System settings",
    "advanced_settings": "Advanced settings",
    "config_entry": "Config entry defaults",
    "default": "Integration default"
  }
}
```

### System-Health-Resilienz & Blueprint-Automation
- Der System-Health-Endpunkt färbt Guard-Skip- und Breaker-Warnungen über
  farbcodierte Indikatoren ein und fasst Guard-, Breaker- und Gesamtstatus
  zusammen, sobald definierte Resilience-Schwellen überschritten werden. Tests
  prüfen Normal-, Warn- und Kritikalarm, deaktivierte Skript-Schwellen sowie
  Options-Fallbacks, damit Bereitschaftsteams im Frontend sofort kritische
  Zustände erkennen.【F:custom_components/pawcontrol/system_health.py†L40-L356】【F:tests/components/pawcontrol/test_system_health.py†L17-L330】
- Die neuen Options-Flow-Felder `resilience_skip_threshold` und
  `resilience_breaker_threshold` setzen Guard- und Breaker-Schwellen zentral und
  synchronisieren Skript, Diagnostics und System-Health ohne YAML-Anpassungen.【F:custom_components/pawcontrol/options_flow.py†L1088-L1143】【F:tests/unit/test_options_flow.py†L804-L852】【F:custom_components/pawcontrol/script_manager.py†L431-L820】
- Die Blueprint-Vorlage `resilience_escalation_followup` ruft das generierte
  Eskalationsskript samt aktiver Schwellenwerte auf, erlaubt optionale Pager-
  Aktionen und bietet getrennte manuelle Guard-/Breaker-Events sowie einen
  Watchdog, damit Runbooks ohne Duplikate auf Abruf reagieren können.【F:blueprints/automation/pawcontrol/resilience_escalation_followup.yaml†L1-L125】
- Diagnostics spiegeln die konfigurierten `manual_*`-Trigger, aggregieren die
  Blueprint-Konfiguration über `config_entries` und migrieren vorhandene
  Skript-Schwellen bei Bestandsinstallationen automatisch in den Optionen-
  Payload. Dadurch bleiben System-Health, Blueprint und Dokumentation
  synchronisiert.【F:custom_components/pawcontrol/script_manager.py†L238-L412】【F:custom_components/pawcontrol/options_flow.py†L700-L820】【F:tests/components/pawcontrol/test_diagnostics.py†L120-L208】

Paw Control konzentriert sich auf eine verlässliche Home-Assistant-Integration
statt auf proprietäre Cloud-Dienste. Funktionen, die noch in Arbeit sind (z. B.
Hardware-spezifische APIs), werden erst in der Dokumentation beworben, wenn sie
inklusive Tests ausgeliefert sind.
