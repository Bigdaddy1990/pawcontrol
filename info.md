<!-- Language / Sprache -->
[🇬🇧 English](#english) · [🇩🇪 Deutsch](#deutsch)

---

<a name="english"></a>
# 🐕 Paw Control – Home Assistant Companion for Multi-Dog Households

Paw Control is a custom HACS integration for reliable automation and monitoring
of dogs already represented inside Home Assistant. Configuration and runtime
logic follow Home Assistant's architecture guidelines: a config flow provisions
helpers and scripts, a shared `DataUpdateCoordinator` orchestrates module
adapters, and all HTTP calls reuse Home Assistant's managed aiohttp session.

## Feature Overview

### Guided Setup & Module Selection
- The multi-step config flow stores basic data per dog and activates modules
  such as Feeding, GPS, Garden or Visitor Mode, branching directly into the
  relevant detail dialogs (e.g. GPS or feeding parameters) where needed.
- Automatic suggestions from Zeroconf, DHCP, USB or HomeKit launch a discovery
  flow that merges profile selection, module assignment and external entities
  before the config entry is created.
- The module configuration assigns existing entities (persons, device trackers,
  door sensors, weather entity) and allows importing external API endpoints if a
  companion device is connected.
- Helpers such as `input_boolean`, `input_datetime` and counters are created
  automatically; missing assets can be added later in the options flow.

### Runtime Modules & Coordinator
- The `PawControlCoordinator` bundles all dog data and starts matching adapters
  per module (Feeding, Walk, GPS, Garden, Weather), so all platforms access the
  same data consistently.
- Module adapters cache results, use the device API client when needed and
  deliver structured payloads for the sensor platforms.

### Notifications & Webhooks
- The `PawControlNotificationManager` bundles push messages, person detection,
  callback logic and webhook handlers with rate limits, caching and optional
  signature verification.

### Visitor Mode & Temporary Dogs
- Visitor status is managed via service, switch and button; the data manager
  stores metadata such as visitor name or reduced alerts.

### Weather & Health Evaluation
- The `WeatherHealthManager` analyses forecast data from a configured weather
  entity, calculates health scores and suggests activity windows.

### Automation Building Blocks
- The dashboard generator creates and maintains Lovelace layouts
  asynchronously, differentiating at module level and optionally showing weather
  widgets.
- Additional platforms (sensors, switches, buttons, texts, selectors) read
  coordinated data and mirror helper states.

### Services & Diagnostics
- Service calls for Feeding, Walks, Garden Sessions, Health Logging and
  Notifications are documented in `services.yaml`, implemented in `services.py`
  and covered by service telemetry tests.
- Diagnostics provide setup flags, service guard metrics, notification rejection
  metrics and an aggregated error overview.

## Installation & Getting Started
1. **Add repository to HACS** (category Integration) and install Paw Control.
2. **Start config flow** (`Settings → Devices & Services → Add Integration`)
   and configure modules and assignments per dog.
3. **Optional steps**: adjust weather entity, door sensors and notification
   devices in the options flow; add a dashboard in Lovelace; configure webhook
   targets if external systems need to be connected.

### Setup – Step by Step
1. **Add integration:** Open `Settings → Devices & Services` and select
   *Paw Control*.
2. **Create dog(s):** Enter name, ID, size, weight and optional health data.
3. **Select modules:** Activate Feeding, GPS, Garden, Visitor Mode and Weather
   as required.
4. **Assign external entities:** GPS source (person/device tracker), optionally
   door sensors and weather entity.
5. **Review options:** Set dashboard generator, notifications, performance mode
   and data retention.
6. **Verify:** Check entities and send a test notification.

### Troubleshooting – Quick Check
1. **Setup fails:** Check `Settings → Devices & Services → Logs` for missing
   API endpoints or invalid entities.
2. **No entities visible:** Ensure at least one dog is fully configured.
3. **GPS without data:** The GPS source must be an active tracker or person with
   location updates.
4. **Notifications missing:** Check the selected notification service and send
   the test notification.
5. **Performance issues:** Enable performance mode or reduce active modules per
   dog.

## Quality & Support Status
- Docstrings and type annotations are enforced project-wide.
- CI enforces localization flag sync and TypedDict audits on every push.
- Resilience blueprints and System Health indicators surface guard/breaker
  status with colour-coded thresholds.

---

<a name="deutsch"></a>
# 🐕 Paw Control – Home Assistant Companion für Mehrfach-Hundehaushalte

Paw Control ist eine benutzerdefinierte HACS-Integration für zuverlässige
Automatisierung und Überwachung von Hunden, die bereits in Home Assistant
erfasst sind. Konfiguration und Laufzeitlogik folgen den Architekturrichtlinien
von Home Assistant: Ein Config Flow richtet Helfer und Skripte ein, ein
gemeinsamer `DataUpdateCoordinator` koordiniert Modul-Adapter, und alle
HTTP-Aufrufe nutzen die verwaltete aiohttp-Session von Home Assistant.

## Überblick über die Funktionen

### Geführte Einrichtung & Modulwahl
- Der mehrstufige Config Flow legt je Hund Stammdaten an und aktiviert Module
  wie Fütterung, GPS, Garten oder Besuchsmodus, verzweigt bei Bedarf direkt in
  die passenden Detaildialoge.
- Automatische Vorschläge aus Zeroconf, DHCP, USB oder HomeKit starten den
  Discovery-Flow, der Profilwahl, Modulzuordnung und externe Entitäten
  zusammenführt, bevor der Config Entry angelegt wird.
- Helfer wie `input_boolean`, `input_datetime` und Counter werden automatisch
  erzeugt; fehlende Assets lassen sich im Options-Flow nachpflegen.

### Laufzeitmodule & Koordinator
- Der `PawControlCoordinator` bündelt alle Hundedaten und startet pro Modul
  passende Adapter (Feeding, Walk, GPS, Garden, Weather).
- Die Modul-Adapter cachen Ergebnisse, nutzen bei Bedarf den Geräte-API-Client
  und liefern strukturierte Payloads für die Sensorplattformen.

### Benachrichtigungen & Webhooks
- Der `PawControlNotificationManager` bündelt Push-Nachrichten, Personen­
  erkennung, Rückfragen-Logik und Webhook-Handler mit Ratelimits, Caching und
  optionaler Signaturprüfung.

### Besuchsmodus & temporäre Hunde
- Besuchsstatus wird per Service, Switch und Button verwaltet; der
  Datenmanager speichert Metadaten wie Besuchername oder reduzierte Alarme.

### Wetter- und Gesundheitsauswertung
- Der `WeatherHealthManager` analysiert Forecast-Daten einer konfigurierten
  Wetter-Entity, berechnet Health-Scores und schlägt Aktivitätsfenster vor.

### Automations-Bausteine
- Der Dashboard-Generator erstellt und pflegt Lovelace-Layouts asynchron,
  differenziert auf Modulebene und blendet optional Wetter-Widgets ein.
- Zusätzliche Plattformen (Sensoren, Schalter, Buttons, Texte, Selektoren) lesen
  koordinierte Daten aus und spiegeln die Helper-States wider.

### Services & Diagnostik
- Service-Aufrufe für Feeding, Walks, Garden-Sessions, Health-Logging und
  Benachrichtigungen sind in `services.yaml` dokumentiert.
- Diagnostics liefern Setup-Flags, Service-Guard-Metriken, Notification-
  Rejection-Metriken und eine aggregierte Fehlerübersicht.

## Installation & Inbetriebnahme
1. **Repository zu HACS hinzufügen** (Kategorie Integration) und Paw Control
   installieren.
2. **Config Flow starten** (`Einstellungen → Geräte & Dienste → Integration
   hinzufügen`) und je Hund Module sowie Zuordnungen vornehmen.
3. **Optionale Schritte**: Wetter-Entity, Türsensoren und
   Benachrichtigungsgeräte im Options-Flow nachjustieren; Dashboard in Lovelace
   hinzufügen; Webhook-Ziele konfigurieren.

### Einrichtung – Schritt für Schritt
1. **Integration hinzufügen:** `Einstellungen → Geräte & Dienste` öffnen und
   *Paw Control* auswählen.
2. **Hund(e) anlegen:** Name, ID, Größe, Gewicht und optionale Gesundheitsdaten
   erfassen.
3. **Module wählen:** Feeding, GPS, Garten, Besuchsmodus und Wetter nach Bedarf
   aktivieren.
4. **Externe Entitäten zuordnen:** GPS-Quelle (Person/Gerätetracker), optional
   Türsensoren und Wetter-Entity auswählen.
5. **Optionen prüfen:** Dashboard-Generator, Benachrichtigungen,
   Performance-Modus und Datenaufbewahrung festlegen.
6. **Verifizieren:** Entitäten prüfen und eine Testbenachrichtigung senden.

### Fehlerbehebung – Schnellcheck
1. **Setup schlägt fehl:** `Einstellungen → Geräte & Dienste → Logs` auf
   fehlende API-Endpunkte oder ungültige Entitäten prüfen.
2. **Keine Entitäten sichtbar:** Sicherstellen, dass mindestens ein Hund
   vollständig konfiguriert ist.
3. **GPS ohne Daten:** GPS-Quelle muss ein aktiver Tracker oder eine Person mit
   Standortupdates sein.
4. **Benachrichtigungen fehlen:** Gewählten Notification-Service prüfen und
   Testbenachrichtigung senden.
5. **Leistungsprobleme:** Performance-Modus aktivieren oder aktive Module pro
   Hund reduzieren.

## Qualitäts- und Supportstatus
- Docstrings und Typannotationen werden projektweit erzwungen.
- CI erzwingt Lokalisierungs-Flag-Sync und TypedDict-Audits bei jedem Push.
- Resilience-Blueprints und System-Health-Indikatoren zeigen Guard/Breaker-
  Status mit farbcodierten Schwellenwerten.
