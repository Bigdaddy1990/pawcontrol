# Erweiterte Fassung – pawcontrol

# 🐶 pawcontrol - Home Assistant Integration

## 🎯 Hauptfeatures im Überblick

| Kategorie                | Beschreibung |
|--------------------------|--------------|
| 🧠 **Setup per UI**      | Einfache Konfiguration pro Hund – inkl. Name, Türsensor, Push-Gerät |
| 🚪 **Türsensor-Erkennung** | Automatische Erkennung, wenn Hund durch die Tür geht |
| 📲 **Push-Rückfrage**     | Nachricht an gewähltes Gerät: „Hat er gemacht?" – Antwort mit ✅ / ❌ |
| 🔄 **Quittierungs-Logik** | Antwort auf einem Gerät löscht die Nachricht auf allen anderen |
| 📊 **Dashboard-Integration** | Lovelace-fertiges YAML-Layout enthalten |
| 🔃 **Tagesreset**          | Alle Zähler (Fütterung, Draußen) werden täglich um 23:59 Uhr zurückgesetzt |
| 🐾 **Mehrhundelogik**     | Unterstützung für mehrere Hunde mit eigenen Sensoren und Werten |
| 🧪 **Besuchshund-Modus**  | Temporärer Hundebesuch? Kein Problem – einfach aktivieren |
| 📦 **HACS-kompatibel**    | Installation als Custom Repository in HACS möglich |

### 🔧 Funktionsübersicht

| Feature | Beschreibung |
|---------|--------------|
| 🍽️ **Fütterung** | Erinnerungen für Frühstück, Mittag, Abend, Leckerli |
| 🚪 **Türsensor-Tracking** | „Draußen"-Protokoll mit Rückfragen |
| 📲 **Push-Logik** | Nachricht an anwesende Person(en) oder manuelle Geräte |
| 📅 **Tagesstatistik** | Counter pro Aktion + automatischer Reset |
| 🧍 **Besucherhunde** | Optionaler Besuchsmodus & Statusanzeige |
| 🧠 **Adminpanel** | Zentrale Übersicht, manuelle Steuerung, Push-Test |
| 📊 **Dashboard** | Mushroom-fähig, responsiv, Chip + Template-Karten |
| 💬 **Rückfragen** | „Hund schon gefüttert?" via Notification |
| 🔁 **Flexibel** | Beliebig viele Hunde, jede Funktion einzeln abschaltbar |

## 🎯 Features im Detail

### 🔔 Push & Benachrichtigungen
- **Dynamische Personenerkennung**: Automatische Benachrichtigung via `person.*` Entitäten wenn `state == home`
- **Fallback-System**: Statisch konfigurierte Geräte (`mobile_app_*`) als Backup
- **Interaktive Rückfragen**: Benachrichtigungen mit Titel, Nachricht und Bestätigungsoptionen
- **Multi-User Support**: Unterstützung für mehrere Haushaltsbenutzer
- **Flexible Konfiguration**: Wählbar zwischen Personen-basiert oder Geräte-basiert
- **Test-Funktion**: Benachrichtigungs-Test per Button oder Service

### 🍽️ Fütterung & Rückfragen
- **Vier Mahlzeiten**: Frühstück, Mittag, Abend, Snack – einzeln aktivierbar
- **Intelligente Rückfragen**: Automatische Erinnerungen für jede Fütterung
- **Status-Tracking**: Erkennung per `input_boolean`-Toggle pro Mahlzeit
- **Zeitgesteuerte Erinnerungen**: `input_datetime` für geplante Benachrichtigungen (geplant)
- **Fütterungs-Counter**: Separate Zähler für jede Mahlzeit
- **Überfütterungs-Schutz**: Warnung bei zu häufiger Fütterung
- **Tagesübersicht**: Vollständige Übersicht aller Fütterungen

### 🚪 Gartengang & Aktivitäts-Tracking
- **Türsensor-Integration**: Automatische Erkennung "Hund war draußen?"
- **Manuelle Erfassung**
- **Rückfrage-System**: Automatische Bestätigung via Push-Benachrichtigung
- **Aktivitäts-Counter**
- **Zeitstempel-Tracking** für Aktivitäten 
- **Dauer-Messung** Aufenthaltszeit im Garten

### 💩 Geschäfte & Gesundheits-Tracking
- **Kot-Tracking**: Separater Counter für Geschäfte
- **Gesundheits-Monitoring**: Unregelmäßigkeiten erkennen
- **Tierarzt-Erinnerungen**: Automatische Benachrichtigungen bei Auffälligkeiten
- **Wetter-Integration**: Berücksichtigung von Wetterbedingungen (geplant)

### 📊 Statistik & Auswertung
- **Umfassende Counter für**:
  - Jede Fütterungsart (Frühstück, Mittag, Abend, Snack)
  - Gassigang-Häufigkeit
  - Kot-Zeiten und -Häufigkeit
  - Besondere Ereignisse
- **Automatischer Reset**: Täglicher Reset um benutzergewählte Zeit
- **Historische Daten**: Langzeit-Statistiken für Gesundheits-Trends
- **Sensor für letzte Aktivität**: Zeitstempel der letzten Aktion
- **Wöchentliche/Monatliche Zusammenfassungen**: Trend-Analyse

### 🧾 Automatisierung & Skripte
- **Auto-generierte Skripte**:
  - Rückfrage-Skripte mit `notify`-Service
  - Individuelle Reset-Skripte pro Hund
  - Push-Test-Skripte für jeden Hund
- **Service-Integration**: Nahtlose Integration in Home Assistant Automationen
- **Zeitgesteuerte Aktionen**: Automatische Erinnerungen basierend auf Uhrzeiten
- **Bedingte Logik**: Intelligente Benachrichtigungen basierend auf Hundestatus

### 🧩 Erweiterbarkeit & Flexibilität
- **Multi-Hund Support**
- **Besucherhund-Modus**: Temporärer Modus für Gäste-Hunde (Hunde-Sitting)
- **Geräte-Flexibilität**: Wählbar zwischen Personen-basiert oder statischer Geräteliste
- **Modularer Aufbau**: Einzelne Features aktivierbar/deaktivierbar
- **Custom Entities**: Unterstützung für benutzerdefinierte Entitäten
- **Integration Ready**: Vorbereitet für weitere Sensoren (Futterschale, Wasserspender, etc.)

### 🖥️ Dashboard & Benutzeroberfläche
- **Mushroom-Kompatibilität**: Optimiert für Mushroom-Cards (Chips, Templates)
- **Lovelance Installationsanleitung*
- **Automatisches Dashboard**: Alle Entitäten werden automatisch angezeigt
- **Responsive Design**: Optimiert für Desktop und Mobile
- **Konfigurationspanel**: Zentrale Übersicht und Schnellsteuerung
- **Anpassbare Layouts**: Verschiedene Dashboard-Varianten
- **Status-Indikatoren**: Visuelle Darstellung des Hundestatus
- **Schnellaktionen**: Ein-Klick-Buttons für häufige Aktionen

### 🌐 GitHub & HACS-Integration
- **Vollständige HACS-Kompatibilität**:
  - `manifest.json` mit korrekter Versionierung
  - `hacs.json` mit Domain-Spezifikationen
  - Automatische Update-Erkennung
- **GitHub Actions Workflow**:
  - `release.yml` für automatische Releases
  - `validate.yml` für Code-Qualität
  - `hacs.yml` für HACS-Validierung
- **Dokumentation**:
  - Ausführliche README mit Installationsanleitung
  - Screenshots und Beispiele
  - Konfigurationshandbuch
- **Community Features**:
  - Issue-Templates
  - Contribution Guidelines
  - Codeowner-Spezifikation

### 🔧 Technische Features
- **Config Flow**: Benutzerfreundliche Einrichtung über UI
- **Entity Registry**: Saubere Entitäts-Verwaltung
- **Error Handling**: Robuste Fehlerbehandlung
- **Logging**: Umfassendes Logging für Debugging
- **Localization**: Mehrsprachige Unterstützung (DE/EN)
- **Device Integration**: Proper Device-Gruppierung
- **Service Schemas**: Validierte Service-Aufrufe

### 🛡️ Sicherheit & Datenschutz
- **Lokale Verarbeitung**: Keine Cloud-Abhängigkeiten
- **Sichere Konfiguration**: Validierte Eingaben
- **Backup-Kompatibilität**: Alle Daten in Home Assistant-Backups enthalten
- **Privacy-First**: Keine externen Datenübertragungen

### 🔧 Setup & Installation
- **🐶 Automatische Setup-Skript-Erstellung**
- **⏳ Verzögerter Start**: Vermeidet Race Conditions beim Skriptaufruf
- **🧠 Robuste Fehlerbehandlung**
- **🛠️ UI-basierte Konfiguration**
- **📦 Integriertes Setup**

### 🐕 Besuchshund-Modul
- **Flexible Aktivierung**
- **Separate Verwaltung**: Eigene Dashboard-Blöcke mit getrennter Statistik
- **Isolierte Rückfragen**: Unabhängiges Tracking ohne Vermischung der Daten
- **Gäste-optimiert**: Ideal für temporäre Hundebesuche mit vollständiger Funktionalität

### 💬 Intelligente Rückfragen
- **Türsensor-Integration**: Automatische Erkennung von Türbewegungen
- **Kontextuelle Fragen**: „War der Hund draußen?" nach Türöffnung
- **Geschäft-Tracking**: Optionale Nachfrage über erledigte Geschäfte
- **Multi-Device-Synchronisation**: Antwort auf einem Gerät löscht Benachrichtigungen auf allen anderen
- **Quittierungs-System**: Vollständige Rückmeldungslogik mit Status-Updates

### 📱 Mobile-First Design
- **Mushroom UI-Optimierung**: Perfekt abgestimmt auf moderne Card-Layouts
- **Timeline-Integration**: Chronologische Darstellung aller Aktivitäten
- **Responsive Statusanzeige**: Optimiert für verschiedene Bildschirmgrößen
- **Touch-optimierte Buttons**: Große, gut erreichbare Bedienelemente
- **Schnellzugriff-Panel**: Wichtigste Funktionen sofort verfügbar

### 🐶 Erweiterte Mehrhundeverwaltung
- **Skalierbare Architektur**
- **Automatische Entitätserstellung**: Zähler, Fütterungszeiten, Statistiken pro Hund
- **Individuelle Konfiguration**: Jeder Hund mit eigenen Einstellungen und Türsensoren
- **Visuelle Unterscheidung**: Farben, Icons und Layouts pro Hund anpassbar
- **Getrennte Historien**: Separate für Wochen-/Monatsstatistiken

### 📊 Dashboard & Automatisierung
- **Dynamische UI-Generierung**: Automatische Dashboard-Erstellung je Hund
- **Besuchshund-Separation**: Separate Bereiche für temporäre Gäste
- **Notification-Actions**: Interaktive Rückfragen direkt aus Benachrichtigungen
- **Zeitgesteuerte Automationen**: Inkl. Reset-Automationen und Erinnerungen
- **Anpassbare Layouts**: Verschiedene Dashboard-Varianten für unterschiedliche Bedürfnisse

### ✅ Vollständige Setup-Integration
- **UI-basiertes Onboarding**: Komplette Einrichtung über Home Assistant Interface
- **Automatische Helper-Erstellung**: werden automatisch angelegt
- **Intelligenter Tagesreset**: Konfigurierbare Reset-Zeit (Standard: 23:59 Uhr)
- **Flexible Sensorkonfiguration**: Türsensor-Auswahl und -Konfiguration im Setup
- **Erweiterbares System**

### 🧠 Erweiterte Konfiguration
- **Umfassender Config Flow**: 
  - Individuelle Namensvergabe pro pawcontrol
  - Multi-Device Push-Gerät-Auswahl
  - Türsensor-Integration
  - Personen-Tracking Ein/Aus-Schalter
  - Automatische Dashboard-Erstellung (optional)
- **Validierung & Fehlerbehandlung**: Robuste Eingabevalidierung mit hilfreichen Fehlermeldungen
- **Backup & Migration**: Vollständige Konfiguration in Home Assistant-Backups enthalten

---

# 🔧 Ergänzungen & technische Spezifikation (ohne Löschung des Originals)

> Ziel: Für **jede Funktion** die nötige **Codebasis, Entities/Helper, Config-Optionen, Abhängigkeiten, Trigger/Scheduler** und **optionale Blueprints** auflisten. Außerdem: **minimale, lauffähige** Code-Skelette für die in der Struktur genannten Dateien (Domain: `pawcontrol`).

## Inhaltsverzeichnis
1. Architektur & Konventionen
2. Globale Abhängigkeiten & Manifest
3. Config Flow & OptionsFlow (Schlüssel & Validierung)
4. Services & Service-Schemas
5. Interne Scheduler/Trigger (kein YAML nötig)
6. Module (Funktion → Codebasis/Entities/Configs/Abhängigkeiten)
   - Push & Benachrichtigungen
   - Fütterung
   - Türsensor/Gartengang & Aktivität
   - Geschäfte (Kot) & Gesundheit
   - Statistik & Tagesreset
   - Besuchshund-Modus
   - Dashboard
7. Optionale Blueprints (YAML)
8. Minimaler Code: Datei-Skelette (`__init__.py`, `manifest.json`, `const.py`, `config_flow.py`, `helpers.py`, `dashboard.py`, `sensor.py`, `binary_sensor.py`, `button.py`, `services.yaml`, `strings.json`, `translations`)
9. GitHub Actions & HACS
10. Definition of Done & Test-Checkliste

---

## 1) Architektur & Konventionen

- **Domain**
- **Config Entries**: Einrichtung/Änderungen **ohne Neustart**; OptionsFlow mit Lazy-Validation
- **Idempotente Sync-Logik**: erzeugt/entfernt nur, was gebraucht wird
- **Entitäten schlank**: Rechenwerte als Template-/Trigger-Sensoren; „Helper“ vorzugsweise als **eigene Integration-Entities** (Number/Select/Text/Button/Sensor). (Reine `input_*`-Helpers sind in HA UI-basiert; innerhalb der Integration ersetzen wir sie durch eigene Plattform-Entities.)
- **Mehrhundelogik**: `dog_id` (Slug), `unique_id`-Schema: `pawcontrol.{dog_id}.{module}.{purpose}`
- **Soft-Dependencies**: `person.*`, `device_tracker.*`, `notify.*`, `calendar.*`, `weather.*` → optional, Pfade inaktiv, keine Exceptions
- **Zeit**: lokale Zeit; Scheduler über `async_track_time_change` / `async_call_later`

---

## 2) Globale Abhängigkeiten & `manifest.json`

**Abhängigkeiten (optional, weich)**: `mobile_app`, `person`, `zone`, `calendar`  
**After-Dependencies**: `http`, `cloud` (falls benötigt für mobile actions)

**Beispiel `manifest.json`:**
```json
{
  "domain": "pawcontrol",
  "name": "pawcontrol",
  "version": "1.0.0",
  "documentation": "https://github.com/<user>/pawcontrol",
  "issue_tracker": "https://github.com/<user>/pawcontrol/issues",
  "codeowners": ["@<user>"],
  "config_flow": true,
  "iot_class": "local_polling",
  "requirements": [],
  "dependencies": [],
  "after_dependencies": ["mobile_app", "person", "zone", "calendar"]
}
```

---

## 3) Config Flow & Options (Schlüssel)

**Grundstruktur**:
- **Hunde**: Liste aus `[{ dog_id, name, color/icon (optional) }]`
- **Module je Hund**: `feeding`, `walk`, `health`, `poop`, `notifications`, `dashboard`, `visitor`
- **Quellen**: Türsensor (`binary_sensor.*`), GPS (`device_tracker.*`/`person.*`), Notify-Fallback (`notify.*`), Kalender (`calendar.*`), Wetter (`weather.*`)
- **Benachrichtigung**: Quiet Hours, Wiederholung/Snooze, Priorität: Personen-basiert → Fallback Gerät(e)
- **Reset-Zeit**: Standard 23:59, konfigurierbar

**Option Keys (Beispiele)**:
```yaml
dogs: 
  - dog_id: "rex"
    name: "Rex"
    modules:
      feeding: true
      walk: true
      health: false
      poop: true
      notifications: true
      dashboard: true
      visitor: false
    sources:
      door_sensor: binary_sensor.terrassentuer_contact
      person_entities: [person.denny]
      device_trackers: [device_tracker.phone_denny]   # optional
      notify_fallback: notify.mobile_app_dennys_iphone
      calendar: calendar.hund_events
      weather: weather.home
notifications:
  quiet_hours: { start: "22:00:00", end: "07:00:00" }
  reminder_repeat_min: 30
  snooze_min: 15
reset_time: "23:59:00"
dashboard:
  mode: "full"  # full|cards
```

---

## 4) Services & Schemas

**Services (Auszug):**
- `pawcontrol.start_walk`, `pawcontrol.end_walk`, `pawcontrol.walk_now`
- `pawcontrol.feed_dog`
- `pawcontrol.log_poop`
- `pawcontrol.log_health_data`, `pawcontrol.log_medication`, `pawcontrol.start_grooming`
- `pawcontrol.toggle_visitor_mode`, `pawcontrol.notify_test`
- `pawcontrol.daily_reset`, `pawcontrol.generate_report`, `pawcontrol.sync_setup`

**`services.yaml` (vollständiges Minimalbeispiel unten in Abschnitt 8)**

---

## 5) Interne Scheduler/Trigger

- **Daily Reset**: `async_track_time_change(..., hour=23, minute=59, second=0)`
- **Report** (optional): z. B. 23:55
- **Reminder**: Feeding/Walk/Medication – Zeitfenster, Snooze, Quiet Hours
- **Türsensor/GPS**: Event-Trigger → Start/Ende Walk, Inaktivitäts-Timeout

---

## 6) Module – Mapping: Codebasis, Entities, Configs, Abhängigkeiten

### 6.1 Push & Benachrichtigungen
- **Codebasis**: `helpers.py` (NotificationRouter), `__init__.py` (Service-Calls), `services.yaml`
- **Entities (pro Hund, Integration-eigen)**:
  - `button.pawcontrol_{dog}_notify_test`
  - `switch.pawcontrol_{dog}_notifications_enabled` *(optional)*
- **Configs**: `notifications.quiet_hours`, `notifications.reminder_repeat_min`, `notifications.snooze_min`, Quellen (`person_entities`, `notify_fallback`)
- **Abhängigkeiten**: `mobile_app`, `person`
- **Services**: `notify_test`, interne Router-Funktion (Person anwesend? → passendes `notify.mobile_app_*`)
- **Trigger/Scheduler**: Reminder-Planung über Scheduler
- **Optional Blueprints**: Generic Push Test / Acknowledge Pattern

### 6.2 Fütterung
- **Codebasis**: `services.yaml` (`feed_dog`), `sensor.py` (letzte Mahlzeit), `button.py` (Schnellaktion „Gefüttert“), `helpers.py` (Reminder-Planer)
- **Entities (pro Hund)**:
  - `sensor.pawcontrol_{dog}_last_feeding` (Zeitstempel/Typ)
  - `button.pawcontrol_{dog}_mark_fed`
  - `binary_sensor.pawcontrol_{dog}_is_hungry` (Template/Trigger)
- **Configs**: aktivierte Mahlzeiten, Zeiten (OptionsFlow), Reminder-Parameter (global)
- **Abhängigkeiten**: optional `calendar`
- **Services**: `feed_dog`
- **Trigger/Scheduler**: Zeitfenster-Reminder pro aktiver Mahlzeit
- **Optional Blueprints**: „Feeding Reminder (generic)“

### 6.3 Türsensor/Gartengang & Aktivität (Walk)
- **Codebasis**: `helpers.py` (door/GPS-Logic), `sensor.py` (letzter Walk, Dauer), `binary_sensor.py` (needs_walk)
- **Entities (pro Hund)**:
  - `sensor.pawcontrol_{dog}_last_walk` (datetime)
  - `sensor.pawcontrol_{dog}_last_walk_duration_min` (number)
  - `sensor.pawcontrol_{dog}_last_walk_distance_m` (number, optional GPS)
  - `binary_sensor.pawcontrol_{dog}_needs_walk` (trigger-template)
  - `button.pawcontrol_{dog}_start_walk`, `button.pawcontrol_{dog}_end_walk`
- **Configs**: Türsensor, GPS/Tracker, Distanz-Schwellen, Auto-Ende Timeout
- **Abhängigkeiten**: `binary_sensor.*` (Tür), `device_tracker.*` / `person.*`
- **Services**: `start_walk`, `end_walk`, `walk_now`
- **Trigger/Scheduler**: Tür-Event, Distanzänderung, Inaktivitäts-Timeout

### 6.4 Geschäfte (Poop) & Gesundheit
- **Codebasis**: `services.yaml`, `sensor.py` (Zähler, letzter Eintrag), `helpers.py` (Erinnerungen)
- **Entities (pro Hund)**:
  - `sensor.pawcontrol_{dog}_poop_count_today`
  - `sensor.pawcontrol_{dog}_last_poop`
  - **Gesundheit** (optional): `sensor.pawcontrol_{dog}_weight`, `sensor.pawcontrol_{dog}_vaccine_status`, `sensor.pawcontrol_{dog}_medication_due`
  - `select.pawcontrol_{dog}_grooming_type`, `sensor.pawcontrol_{dog}_last_grooming`, `number.pawcontrol_{dog}_grooming_interval_days`
- **Configs**: Medikation-Zeiten, Grooming-Intervalle, Health-Tracking an/aus
- **Abhängigkeiten**: optional `calendar`
- **Services**: `log_poop`, `log_health_data`, `log_medication`, `start_grooming`
- **Trigger/Scheduler**: Medikation/Grooming-Fälligkeit

### 6.5 Statistik & Tagesreset
- **Codebasis**: `helpers.py` (Scheduler + Tagesreset), `sensor.py` (Counter als Integration-Entities)
- **Entities (pro Hund)**:
  - `sensor.pawcontrol_{dog}_feeding_count_today_*` (breakfast/lunch/dinner/snack)
  - `sensor.pawcontrol_{dog}_walk_count_today`
  - `sensor.pawcontrol_{dog}_poop_count_today`
  - `sensor.pawcontrol_{dog}_last_action`
- **Configs**: Reset-Zeit
- **Services**: `daily_reset`, `generate_report`
- **Trigger/Scheduler**: Reset 23:59, optional Report 23:55

### 6.6 Besuchshund-Modus
- **Codebasis**: `__init__.py` (Mode-Flag), `sensor.py` (separate Zähler), `dashboard.py` (separate Sektion)
- **Entities (global/je Hund)**:
  - `switch.pawcontrol_{dog}_visitor_mode`
- **Configs**: aktiv/aus
- **Services**: `toggle_visitor_mode`
- **Trigger/Scheduler**: —

### 6.7 Dashboard
- **Codebasis**: `dashboard.py` (Renderer), optionale YAML-Vorlagen
- **Entities**: nutzt die oben definierten
- **Configs**: Modus `full|cards`, Hundereihenfolge, Anzeigeoptionen
- **Abhängigkeiten**: Mushroom (nur Anzeige), Wetter/Kalender (optional)
- **Services**: —

---

## 7) Optionale Blueprints (YAML)

### 7.1 Feeding Reminder (generic)
```yaml
blueprint:
  name: pawcontrol – Feeding Reminder (generic)
  domain: automation
  input:
    dog_entity:
      name: Hund (Sensor letzte Fütterung)
      selector: { entity: { domain: sensor } }
    notify_target:
      name: Notify Service
      selector: { text: {} }
    meal_time:
      name: Mahlzeit Uhrzeit
      selector: { time: {} }
    snooze_min:
      name: Snooze (Minuten)
      default: 15
      selector: { number: { min: 5, max: 120, step: 5 } }

trigger:
  - platform: time
    at: !input meal_time

condition: []

action:
  - service: !input notify_target
    data:
      message: "Fütterung fällig für {{ state_attr(!input dog_entity, 'friendly_name') or 'Hund' }}."
      data:
        actions:
          - action: "FED_NOW"
            title: "Gefüttert"
          - action: "SNOOZE"
            title: "Später"
mode: restart
```

### 7.2 Walk Missing Reminder
```yaml
blueprint:
  name: pawcontrol – Walk Missing Reminder
  domain: automation
  input:
    last_walk_sensor:
      name: Letzter Walk (Sensor)
      selector: { entity: { domain: sensor } }
    notify_target:
      name: Notify Service
      selector: { text: {} }
    hours_threshold:
      name: Stunden seit letztem Walk
      default: 8
      selector: { number: { min: 1, max: 48, step: 1 } }

trigger:
  - platform: time_pattern
    hours: "/1"

condition:
  - condition: template
    value_template: >
      {% set last = states(!input last_walk_sensor) %}
      {% if last in ['unknown','unavailable','none',''] %} false
      {% else %}
        {{ (now() - as_datetime(last)).total_seconds() > ( !input hours_threshold * 3600 ) }}
      {% endif %}

action:
  - service: !input notify_target
    data:
      message: "Lange kein Spaziergang mehr. Bitte prüfen."
mode: restart
```

> Blueprints sind optional – Kernlogik läuft intern ohne YAML.

---

## 8) Minimaler Code (Skelette) – **Domain: `pawcontrol`**

### 8.1 `custom_components/pawcontrol/const.py`
```python
DOMAIN = "pawcontrol"
PLATFORMS = ["sensor", "binary_sensor", "button"]
CONF_DOGS = "dogs"
CONF_NOTIFICATIONS = "notifications"
CONF_RESET_TIME = "reset_time"

DEFAULT_RESET_TIME = "23:59:00"
ATTR_DOG_ID = "dog_id"
```

### 8.2 `custom_components/pawcontrol/__init__.py`
```python
from __future__ import annotations
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN, PLATFORMS
from .helpers import pawcontrolCoordinator, register_services, schedule_core_tasks

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coord = pawcontrolCoordinator(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coord
    await coord.async_setup()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    register_services(hass)
    schedule_core_tasks(hass, entry)
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    return True

async def _options_updated(hass: HomeAssistant, entry: ConfigEntry):
    coord: pawcontrolCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coord.async_reload_options()

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
```

### 8.3 `custom_components/pawcontrol/manifest.json`
*(siehe Abschnitt 2)*

### 8.4 `custom_components/pawcontrol/config_flow.py`
```python
from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from .const import DOMAIN, CONF_DOGS, CONF_NOTIFICATIONS, CONF_RESET_TIME

class pawcontrolConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="pawcontrol", data={}, options=user_input)

        schema = vol.Schema({
            vol.Required(CONF_DOGS): list,
            vol.Optional(CONF_NOTIFICATIONS, default={}): dict,
            vol.Optional(CONF_RESET_TIME, default="23:59:00"): str
        })
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return pawcontrolOptionsFlow(config_entry)

class pawcontrolOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry):
        self.entry = entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.entry.options or {}
        schema = vol.Schema({
            vol.Optional(CONF_DOGS, default=options.get(CONF_DOGS, [])): list,
            vol.Optional(CONF_NOTIFICATIONS, default=options.get(CONF_NOTIFICATIONS, {})): dict,
            vol.Optional(CONF_RESET_TIME, default=options.get(CONF_RESET_TIME, "23:59:00")): str,
        })
        return self.async_show_form(step_id="init", data_schema=schema)
```

### 8.5 `custom_components/pawcontrol/helpers.py`
```python
from __future__ import annotations
import logging
from datetime import time
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.event import async_track_time_change
from .const import DOMAIN, CONF_DOGS, CONF_RESET_TIME

_LOGGER = logging.getLogger(__name__)

class pawcontrolCoordinator:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self.hass = hass
        self.entry = entry
        self.options = entry.options

    async def async_setup(self):
        # place for future setup, e.g. creating runtime stores
        return

    async def async_reload_options(self):
        self.options = self.entry.options
        _LOGGER.debug("Options reloaded: %s", self.options)

def register_services(hass: HomeAssistant):
    async def handle_notify_test(call: ServiceCall):
        msg = call.data.get("message", "pawcontrol: Test")
        target = call.data.get("target")
        if target:
            await hass.services.async_call("notify", target.split(".")[1], {"message": msg}, blocking=False)

    hass.services.async_register(DOMAIN, "notify_test", handle_notify_test)

def schedule_core_tasks(hass: HomeAssistant, entry: ConfigEntry):
    reset_str = (entry.options or {}).get(CONF_RESET_TIME, "23:59:00")
    h, m, s = [int(x) for x in reset_str.split(":")]
    @callback
    def _daily_reset(now=None):
        hass.bus.async_fire(f"{DOMAIN}_daily_reset")
    async_track_time_change(hass, _daily_reset, hour=h, minute=m, second=s)
```

### 8.6 `custom_components/pawcontrol/dashboard.py`
```python
def render_dashboard(dogs: list[str], mode: str = "full") -> str:
    # Rückgabe eines Lovelace-Abschnitts als YAML-String
    cards = []
    for dog in dogs:
        cards.append({
            "type": "entities",
            "title": f"Hund: {dog}",
            "entities": [
                f"sensor.pawcontrol_{dog}_last_walk",
                f"sensor.pawcontrol_{dog}_last_feeding",
                f"binary_sensor.pawcontrol_{dog}_needs_walk"
            ]
        })
    return {"type": "vertical-stack", "cards": cards}
```

### 8.7 `custom_components/pawcontrol/sensor.py`
```python
from __future__ import annotations
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.const import DEVICE_CLASS_TIMESTAMP
from .const import DOMAIN

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    dogs = [d.get("dog_id") for d in (entry.options or {}).get("dogs", [])]
    entities = []
    for dog in dogs:
        entities.append(LastActionSensor(hass, dog))
        entities.append(LastWalkSensor(hass, dog))
        entities.append(LastFeedingSensor(hass, dog))
    async_add_entities(entities, update_before_add=False)

class BaseDogSensor(SensorEntity):
    _attr_has_entity_name = True
    def __init__(self, hass: HomeAssistant, dog_id: str, name_suffix: str):
        self.hass = hass
        self._dog = dog_id
        self._attr_unique_id = f"{DOMAIN}.{dog_id}.sensor.{name_suffix}"
        self._attr_name = name_suffix.replace("_", " ").title()
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, dog_id)}, name=f"Hund {dog_id}", manufacturer="pawcontrol")

class LastActionSensor(BaseDogSensor):
    def __init__(self, hass, dog_id): super().__init__(hass, dog_id, "last_action")
    @property
    def native_value(self): return self.hass.states.get(f"sensor.{DOMAIN}_{self._dog}_last_action", None)

class LastWalkSensor(BaseDogSensor):
    device_class = DEVICE_CLASS_TIMESTAMP
    def __init__(self, hass, dog_id): super().__init__(hass, dog_id, "last_walk")
    @property
    def native_value(self): return self.hass.states.get(f"sensor.{DOMAIN}_{self._dog}_last_walk", None)

class LastFeedingSensor(BaseDogSensor):
    device_class = DEVICE_CLASS_TIMESTAMP
    def __init__(self, hass, dog_id): super().__init__(hass, dog_id, "last_feeding")
    @property
    def native_value(self): return self.hass.states.get(f"sensor.{DOMAIN}_{self._dog}_last_feeding", None)
```

### 8.8 `custom_components/pawcontrol/binary_sensor.py`
```python
from __future__ import annotations
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from datetime import timedelta, datetime
from .const import DOMAIN

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    dogs = [d.get("dog_id") for d in (entry.options or {}).get("dogs", [])]
    entities = [NeedsWalkBinarySensor(hass, dog) for dog in dogs]
    async_add_entities(entities, update_before_add=False)

class NeedsWalkBinarySensor(BinarySensorEntity):
    _attr_has_entity_name = True
    def __init__(self, hass: HomeAssistant, dog_id: str):
        self.hass = hass
        self._dog = dog_id
        self._attr_unique_id = f"{DOMAIN}.{dog_id}.binary_sensor.needs_walk"
        self._attr_name = "Needs Walk"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, dog_id)}, name=f"Hund {dog_id}")
    @property
    def is_on(self):
        st = self.hass.states.get(f"sensor.{DOMAIN}_{self._dog}_last_walk")
        if not st or not st.state or st.state in ("unknown","unavailable"): return False
        try:
            last = datetime.fromisoformat(st.state.replace("Z","+00:00"))
            return (datetime.now(last.tzinfo) - last) > timedelta(hours=8)
        except Exception:
            return False
```

### 8.9 `custom_components/pawcontrol/button.py`
```python
from __future__ import annotations
from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from datetime import datetime, timezone
from .const import DOMAIN

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    dogs = [d.get("dog_id") for d in (entry.options or {}).get("dogs", [])]
    entities = []
    for dog in dogs:
        entities += [MarkFedButton(hass, dog), StartWalkButton(hass, dog), EndWalkButton(hass, dog), NotifyTestButton(hass, dog)]
    async_add_entities(entities, update_before_add=False)

class BaseDogButton(ButtonEntity):
    _attr_has_entity_name = True
    def __init__(self, hass: HomeAssistant, dog_id: str, name_suffix: str):
        self.hass = hass
        self._dog = dog_id
        self._attr_unique_id = f"{DOMAIN}.{dog_id}.button.{name_suffix}"
        self._attr_name = name_suffix.replace("_", " ").title()
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, dog_id)}, name=f"Hund {dog_id}")

class MarkFedButton(BaseDogButton):
    def __init__(self, hass, dog_id): super().__init__(hass, dog_id, "mark_fed")
    async def async_press(self):
        self.hass.states.async_set(f"sensor.{DOMAIN}_{self._dog}_last_feeding", datetime.now(timezone.utc).isoformat())

class StartWalkButton(BaseDogButton):
    def __init__(self, hass, dog_id): super().__init__(hass, dog_id, "start_walk")
    async def async_press(self):
        self.hass.states.async_set(f"sensor.{DOMAIN}_{self._dog}_last_walk", datetime.now(timezone.utc).isoformat())

class EndWalkButton(BaseDogButton):
    def __init__(self, hass, dog_id): super().__init__(hass, dog_id, "end_walk")
    async def async_press(self):
        # could compute duration if start known
        pass

class NotifyTestButton(BaseDogButton):
    def __init__(self, hass, dog_id): super().__init__(hass, dog_id, "notify_test")
    async def async_press(self):
        await self.hass.services.async_call(DOMAIN, "notify_test", {"message": f"Test: {self._dog}"})
```

### 8.10 `custom_components/pawcontrol/services.yaml`
```yaml
notify_test:
  name: Benachrichtigungs-Test
  description: Sende eine Testnachricht
  fields:
    message:
      required: false
      example: "pawcontrol Test"
      selector:
        text:
sync_setup:
  name: Setup synchronisieren
  description: Erzeugt/entfernt alle Entitäten gemäß Optionen
start_walk:
  name: Walk starten
  fields:
    dog_id:
      selector: { text: {} }
end_walk:
  name: Walk beenden
  fields:
    dog_id:
      selector: { text: {} }
feed_dog:
  name: Füttern
  fields:
    dog_id: { selector: { text: {} } }
    meal_type:
      selector: { select: { options: ["breakfast","lunch","dinner","snack"] } }
log_poop:
  name: Geschäft protokollieren
  fields:
    dog_id: { selector: { text: {} } }
```

### 8.11 `custom_components/pawcontrol/strings.json`
```json
{
  "title": "pawcontrol",
  "config": {
    "step": {
      "user": { "title": "pawcontrol einrichten" }
    }
  }
}
```

### 8.12 `custom_components/pawcontrol/translations/de.json`
```json
{
  "title": "pawcontrol",
  "config": {
    "step": {
      "user": { "title": "pawcontrol einrichten" }
    },
    "abort": { "single_instance_allowed": "Nur eine Instanz erlaubt." }
  }
}
```

### 8.13 `custom_components/pawcontrol/translations/en.json`
```json
{
  "title": "Dog System",
  "config": {
    "step": {
      "user": { "title": "Setup Dog System" }
    },
    "abort": { "single_instance_allowed": "Only one instance allowed." }
  }
}
```

---

## 9) GitHub Actions & HACS

**`.github/workflows/validate.yml`**: hassfest, ruff, pytest
**`.github/workflows/release.yml`**: Tag → Release (Zip)  
**`hacs.json`** (Repo-Wurzel):
```json
{ "name": "pawcontrol", "render_readme": true }
```

---

## 10) Definition of Done & Test-Checkliste

- Config Flow & OptionsFlow decken Hunde/Module/Quellen ab
- Services registriert, minimal getestet (notify_test, feed_dog, start/end_walk)
- Scheduler aktiv (Daily Reset)
- Entities erscheinen je Hund, unique_id stabil
- Keine Fehler bei fehlenden optionalen Quellen (Soft-Dependencies)
- Dashboard-Renderer erzeugt Entities ohne Exceptions
- HACS-Metadaten korrekt, CI-Grundchecks grün
