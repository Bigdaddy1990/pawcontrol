# Paw Control

## Schnelle Installation (HACS)
1. Öffne **HACS → Integrations → Custom repositories** und füge dieses Repository hinzu.
2. Suche nach **Paw Control** und installiere die Integration.
3. Gehe zu **Einstellungen → Geräte & Dienste → Integrationen** und richte **Paw Control** ein.
4. Optional: Starte den Service `pawcontrol.show_install_help` für eine Schritt-für-Schritt-Anleitung im UI.

---
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
8. GitHub Actions & HACS
9. Definition of Done & Test-Checkliste

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


## 8) GitHub Actions & HACS

**`.github/workflows/validate.yml`**: hassfest, ruff/flake8, pytest  
**`.github/workflows/release.yml`**: Tag → Release (Zip)  
**`hacs.json`** (Repo-Wurzel):
```json
{ "name": "pawcontrol", "render_readme": true }
```

---

## 9) Definition of Done & Test-Checkliste

- Config Flow & OptionsFlow decken Hunde/Module/Quellen ab
- Services registriert, minimal getestet (notify_test, feed_dog, start/end_walk)
- Scheduler aktiv (Daily Reset)
- Entities erscheinen je Hund, unique_id stabil
- Keine Fehler bei fehlenden optionalen Quellen (Soft-Dependencies)
- Dashboard-Renderer erzeugt Entities ohne Exceptions
- HACS-Metadaten korrekt, CI-Grundchecks grün


---

# Paw Control - Vollständige Setup-Konfiguration

## 🐕 MODUL 1: Grundlegende Hundedaten (ERFORDERLICH)

### Basis-Informationen
- **Hundename** *(Pflichtfeld)*
  - Validierung: 2-30 Zeichen, Buchstaben/Zahlen/Umlaute/Leerzeichen/Bindestriche
  - Pattern: `^[a-zA-ZäöüÄÖÜß0-9\s\-_.]+$`
  - Muss mit Buchstaben beginnen

### Physische Eigenschaften
- **Hunderasse** *(Optional)*
  - Freitext-Eingabe (max. 100 Zeichen)
  - Dropdown mit häufigen Rassen vorschlagen

- **Alter** *(Optional)*
  - Bereich: 0-25 Jahre
  - Eingabe in Jahren (Decimal für Welpen: 0.5, 1.5 etc.)

- **Gewicht** *(Optional)*
  - Bereich: 0.5-100 kg
  - Schritte: 0.1 kg
  - Standard: 15 kg

- **Größenkategorie** *(Optional)*
  - Optionen: ["Toy" (1-6kg), "Klein" (6-12kg), "Mittel" (12-27kg), "Groß" (27-45kg), "Riesig" (45-90kg)]
  - Auto-Suggestion basierend auf Gewicht

### Gesundheits-Basisdaten
- **Standard-Gesundheitsstatus** *(Optional)*
  - Optionen: ["Ausgezeichnet", "Sehr gut", "Gut", "Normal", "Unwohl", "Krank"]
  - Standard: "Gut"

- **Standard-Stimmung** *(Optional)*
  - Optionen: ["😊 Fröhlich", "😐 Neutral", "😟 Traurig", "😠 Ärgerlich", "😰 Ängstlich", "😴 Müde"]
  - Standard: "😊 Fröhlich"

- **Aktivitätslevel** *(Optional)*
  - Optionen: ["Sehr niedrig", "Niedrig", "Normal", "Hoch", "Sehr hoch"]
  - Standard: "Normal"
  - Beeinflusst Kalorien- und Spaziergang-Berechnungen

---

## 🍽️ MODUL 2: Fütterungseinstellungen (OPTIONAL)

### Fütterungszeiten
- **Frühstück aktivieren** *(Boolean, Standard: true)*
  - **Frühstückszeit** *(Zeit, Standard: 09:00)*
  
- **Mittagessen aktivieren** *(Boolean, Standard: false)*
  - **Mittagszeit** *(Zeit, Standard: 13:00)*
  
- **Abendessen aktivieren** *(Boolean, Standard: true)*
  - **Abendzeit** *(Zeit, Standard: 17:00)*
  
- **Snacks aktivieren** *(Boolean, Standard: false)*
  - **Snack-Zeiten** *(Mehrfach-Auswahl)*

### Fütterungsmengen
- **Tägliche Futtermenge** *(Optional)*
  - Bereich: 50-2000g
  - Standard: Auto-Berechnung basierend auf Gewicht (2.5% Körpergewicht)
  
- **Anzahl Mahlzeiten pro Tag** *(Optional)*
  - Bereich: 1-5
  - Standard: 2
  - Beeinflusst Portionsgrößen-Berechnung

- **Standard-Futtertyp** *(Optional)*
  - Optionen: ["Trockenfutter", "Nassfutter", "BARF", "Selbstgekocht", "Gemischt"]
  - Standard: "Trockenfutter"

### Fütterungs-Erinnerungen
- **Automatische Fütterungs-Erinnerungen** *(Boolean, Standard: true)*
- **Erinnerungszeit vor Mahlzeit** *(Minuten, Standard: 30)*
- **Snooze-Zeit bei Erinnerungen** *(Minuten, Standard: 10)*


## 🏥 MODUL 3: Gesundheitsüberwachung (OPTIONAL)

### Gesundheits-Tracking
- **Erweiterte Gesundheitsüberwachung aktivieren** *(Boolean, Standard: false)*
- **Gewichtsverlauf speichern** *(Boolean, Standard: true)*
- **Temperatur-Tracking aktivieren** *(Boolean, Standard: false)*
- **Activity-Logger aktivieren** *(Boolean, Standard: true)*

### Gesundheits-Parameter


### Notfall-Erkennung  
- **Automatische Notfall-Erkennung** *(Boolean, Standard: false)*

### Medikations-Management
- **Medikations-Erinnerungen aktivieren** *(Boolean, Standard: false)*
- **Standard-Medikationen** *(Multi-Entry, Optional)*
  - **Medikament-Name** *(Text)*
  - **Dosierung** *(Text)*
  - **Häufigkeit** *(Optionen: "Täglich", "2x täglich", "3x täglich", "Wöchentlich", "Nach Bedarf")*
  - **Zeiten** *(Zeit-Auswahl je nach Häufigkeit)*

### Tierarzt-Integration
- **Tierarzt-Kontakt** *(Optional)*
  - **Name** *(Text)*
  - **Telefon** *(Text)*
  - **E-Mail** *(Text, Optional)*
  - **Adresse** *(Text, Optional)*

- **Regelmäßige Checkup-Erinnerungen** *(Boolean, Standard: false)*
  - **Checkup-Intervall** *(Monate, Standard: 12)*
  - **Nächster Termin** *(Datum, Optional)*

---

## 🔔 MODUL 4: Benachrichtigungssystem (OPTIONAL)

### Benachrichtigungs-Grundeinstellungen
- **Benachrichtigungen aktivieren** *(Boolean, Standard: true)*
- **Benachrichtigungstyp** *(Auswahl)*
  - "Persistent Notifications" (Standard)
  - "Mobile App Notifications"
  - "Both"

### Mobile App Konfiguration
- **Mobile App Integration** *(Multi-Select)*
  - **Person-Entity für Benachrichtigungen** *(Entity-Auswahl)*
  - **Mobile App Service Name** *(Auto-Detection oder Manual)*
  - **Fallback bei Abwesenheit** *(Boolean, Standard: true)*

### Actionable Notifications
- **Actionable Notifications aktivieren** *(Boolean, Standard: false)*
- **Action-Button-Konfiguration** *(Advanced)*
  - Fütterungs-Actions: "Gefüttert ✅", "10 Min später ⏰"
  - Walk-Actions: "Gassi starten 🚶", "Später 🕐"

### Benachrichtigungs-Kategorien
**Fütterungs-Benachrichtigungen**
- **Aktiviert** *(Boolean, Standard: true)*
- **Vorlaufzeit** *(Minuten, Standard: 30)*
- **Wiederholungen bei ignoriert** *(Number, 0-5, Standard: 2)*
- **Wiederholungs-Intervall** *(Minuten, Standard: 15)*

**Spaziergang-Benachrichtigungen**
- **Aktiviert** *(Boolean, Standard: true)*
- **Erinnerungsintervall** *(Stunden, Standard: 8)*
- **Wetterbasierte Anpassungen** *(Boolean, Standard: false)*

**Gesundheits-Benachrichtigungen**
- **Aktiviert** *(Boolean, Standard: true)*
- **Notfall-Benachrichtigungen** *(Boolean, Standard: true)*
- **Medikations-Erinnerungen** *(Boolean, Standard: false)*

**GPS-Benachrichtigungen**
- **Geofence-Alerts** *(Boolean, Standard: false)*
- **Signal-Verlust-Alerts** *(Boolean, Standard: false)*
- **Signal-Verlust-Schwelle** *(Minuten, Standard: 10)*

### Zeitbasierte Benachrichtigungs-Steuerung
- **Nachtmodus aktivieren** *(Boolean, Standard: true)*
- **Ruhezeiten** *(Zeitbereich)*
  - **Start** *(Zeit, Standard: 22:00)*
  - **Ende** *(Zeit, Standard: 07:00)*
- **Nur Notfälle in Ruhezeiten** *(Boolean, Standard: true)*

---

## 🤖 MODUL 5: Automatisierungssystem (OPTIONAL)

### Basis-Automatisierung
- **Automatisierungs-Manager aktivieren** *(Boolean, Standard: false)*
- **Automatisierungs-Update-Intervall** *(Minuten, Standard: 5)*

### Fütterungs-Automatisierung
- **Fütterungs-Erinnerungen aktivieren** *(Boolean, Standard: true)*
- **Meilenstein-Benachrichtigungen** *(Boolean, Standard: false)*
- **Meilenstein-Schwellen** *(Multi-Number)*
  - Standard: [5, 10, 25, 50, 100]

### Aktivitäts-Automatisierung
- **Walk-Meilenstein-Feiern** *(Boolean, Standard: false)*
- **Aktivitäts-Level-Monitoring** *(Boolean, Standard: false)*
- **Inaktivitäts-Alerts** *(Boolean, Standard: false)*
- **Inaktivitäts-Schwelle** *(Stunden, Standard: 24)*

### Gesundheits-Automatisierung
- **Automatische Gesundheits-Alerts** *(Boolean, Standard: false)*
- **Stimmungsänderungs-Tracking** *(Boolean, Standard: false)*
- **Gewichtsänderungs-Alerts** *(Boolean, Standard: false)*
- **Gewichtsänderungs-Schwelle** *(%, Standard: 5)*

### Besucher-Modus-Automatisierung
- **Automatischer Besuchermodus** *(Boolean, Standard: false)*
- **Besuchererkennung-Methode** *(Optionen)*
  - "Manual Toggle"
  - "Person Detection"
  - "Door Sensor"
  - "Calendar Integration"

### Wartungs-Automatisierung
- **Tägliche Berichte generieren** *(Boolean, Standard: false)*
- **Berichts-Zeit** *(Zeit, Standard: 23:30)*
- **Wöchentliche Zusammenfassungen** *(Boolean, Standard: false)*
- **System-Gesundheitschecks** *(Boolean, Standard: true)*
- **Check-Intervall** *(Minuten, Standard: 30)*

### Notfall-Automatisierung
- **Automatisches Notfall-Protokoll** *(Boolean, Standard: false)*
- **Notfall-Kontakt-Integration** *(Boolean, Standard: false)*
- **Eskalations-Stufen** *(Advanced)*

---

## 📊 MODUL 6: Dashboard und Visualisierung (OPTIONAL)

### Dashboard-Erstellung
- **Automatisches Dashboard erstellen** *(Boolean, Standard: true)*
- **Dashboard-Name** *(Text, Standard: "PawControl")*
- **Dashboard-Pfad** *(Text, Standard: "pawcontrol")*

### Dashboard-Module
**Übersichts-Karten**
- **Status-Übersichtskarte** *(Boolean, Standard: true)*
- **Tages-Zusammenfassung** *(Boolean, Standard: true)*
- **Quick-Action-Buttons** *(Boolean, Standard: true)*

**GPS-Module** *(Wenn GPS aktiviert)*
- **Live-GPS-Karte** *(Boolean, Standard: true)*
- **Route-Verlauf** *(Boolean, Standard: false)*
- **Geofence-Visualisierung** *(Boolean, Standard: false)*

**Gesundheits-Module** *(Wenn Gesundheit aktiviert)*
- **Gesundheits-Status-Karte** *(Boolean, Standard: true)*
- **Gewichtsverlaufs-Graph** *(Boolean, Standard: false)*
- **Medikations-Übersicht** *(Boolean, Standard: false)*

**Aktivitäts-Module**
- **Walk-Statistiken** *(Boolean, Standard: true)*
- **Fütterungs-Status** *(Boolean, Standard: true)*
- **Aktivitäts-Verlauf** *(Boolean, Standard: false)*

### UI-Anpassungen
- **Card-Typ-Präferenz** *(Optionen)*
  - "Mushroom Cards" (Standard, modern)
  - "Standard Entity Cards"
  - "Picture Entity Cards"
  - "Custom Cards"

- **Farbschema** *(Optional)*
  - "Auto" (Standard)
  - "Light"
  - "Dark"

### Mobile Dashboard
- **Mobile-optimierte Ansicht** *(Boolean, Standard: true)*
- **Schnellzugriff-Panel** *(Boolean, Standard: true)*

---


## 📍 MODUL 7: GPS-Tracking-System (OPTIONAL)

### GPS-Grundkonfiguration
- **GPS-Tracking aktivieren** *(Boolean, Standard: false)*
- **GPS-Update-Intervall** *(Sekunden)*
  - Optionen: [30, 60, 120, 300, 600]
  - Standard: 60

### GPS-Quellen-Konfiguration
- **Primäre GPS-Quelle** *(Required wenn GPS aktiviert)*
  - Optionen:
    - "Manual" - Manuelle Eingabe
    - "Device Tracker" - Bestehender device_tracker
    - "Person Entity" - Person-Entity
    - "Smartphone" - Mobile App GPS
    - "Tractive" - Tractive GPS-Halsband
    - "Webhook" - GPS via Webhook
    - "MQTT" - GPS via MQTT-Stream

#### Device Tracker Konfiguration
- **Device Tracker Entity** *(Required bei Device Tracker)*
  - Entity-Auswahl aus vorhandenen device_tracker

#### Person Entity Konfiguration  
- **Person Entity** *(Required bei Person Entity)*
  - Entity-Auswahl aus vorhandenen Person-Entities

#### Smartphone Konfiguration
- **Mobile App Name** *(Required bei Smartphone)*
- **GPS-Genauigkeits-Schwelle** *(Meter, Standard: 50)*

#### Tractive Konfiguration
- **Tractive Device ID** *(Required bei Tractive)*
- **Tractive API Key** *(Required bei Tractive)*
- **Update-Frequenz** *(Sekunden, Standard: 120)*

#### Webhook Konfiguration
- **Webhook ID** *(Required bei Webhook)*
- **Webhook Secret** *(Optional)*
- **Expected JSON Format** *(Auswahl: Standard, Custom)*

#### MQTT Konfiguration
- **MQTT Topic** *(Required bei MQTT)*
- **MQTT Payload Format** *(JSON Path Konfiguration)*

### Heimbereich-Konfiguration
- **Heimkoordinaten** *(Optional)*
  - Auto-Detection bei erstem GPS-Update
  - Manuelle Eingabe: Latitude, Longitude
  
- **Heimbereich-Radius** *(Meter)*
  - Bereich: 10-1000m
  - Standard: 50m

### Geofencing-Einstellungen
- **Geofencing aktivieren** *(Boolean, Standard: false)*
- **Geofence-Konfigurationen** *(Multi-Entry)*
  - **Name** *(Text)*
  - **Center-Koordinaten** *(Lat, Lon)*
  - **Radius** *(10-10000m)*
  - **Typ** *(Optionen: "Safe Zone", "Restricted Area", "Point of Interest")*
  - **Benachrichtigung bei Eintritt** *(Boolean)*
  - **Benachrichtigung bei Verlassen** *(Boolean)*

### Automatische Spaziergang-Erkennung
- **Auto-Walk-Detection aktivieren** *(Boolean, Standard: false)*
- **Bewegungs-Schwelle** *(Meter)*
  - Bereich: 1-50m
  - Standard: 3m
  
- **Stillstands-Zeit** *(Sekunden)*
  - Bereich: 60-1800 Sekunden
  - Standard: 300 Sekunden
  
- **Walk-Detection-Distanz** *(Meter)*
  - Bereich: 5-200m  
  - Standard: 10m
  
- **Minimale Walk-Dauer** *(Minuten)*
  - Bereich: 1-60 Minuten
  - Standard: 5 Minuten

- **Sensitivität** *(Optional)*
  - Optionen: ["Niedrig", "Mittel", "Hoch"]
  - Standard: "Mittel"
  - Beeinflusst Bewegungs-Detection-Parameter

### Route-Tracking
- **Detaillierte Route aufzeichnen** *(Boolean, Standard: true)*
- **Route-Punkte-Limit** *(Number)*
  - Bereich: 10-1000
  - Standard: 100
  
- **GPS-Punkt-Speicher-Intervall** *(Sekunden)*
  - Bereich: 5-300
  - Standard: 30

### Kalorien-Berechnung
- **Kalorien-Berechnung aktivieren** *(Boolean, Standard: true)*
- **Aktivitäts-Intensitäts-Multiplikatoren** *(Advanced)*
  - Langsam: 0.7 (Standard)
  - Normal: 1.0 (Standard) 
  - Schnell: 1.4 (Standard)

---

## ⚙️ MODUL 8: Erweiterte Service-Konfiguration (OPTIONAL)

### Script-Services-Aktivierung
- **Erweiterte Script-Services aktivieren** *(Boolean, Standard: false)*
- **Service-Statistik-Tracking** *(Boolean, Standard: true)*

### Fütterungs-Services
- **feed_dog Service** *(Boolean, Standard: true)*
- **Automatische Portionsgrößen-Berechnung** *(Boolean, Standard: true)*
- **Fütterungs-Logging-Level** *(Optionen: "Basic", "Detailed", "Full")*

### Aktivitäts-Services
- **walk_dog Service** *(Boolean, Standard: true)*
- **play_with_dog Service** *(Boolean, Standard: true)*
- **start_training_session Service** *(Boolean, Standard: false)*
- **Wetterintegration für Spaziergänge** *(Boolean, Standard: false)*
- **Wetter-Entity** *(Entity-Auswahl, falls aktiviert)*

### Gesundheits-Services
- **perform_health_check Service** *(Boolean, Standard: false)*
- **mark_medication_given Service** *(Boolean, Standard: false)*
- **record_vet_visit Service** *(Boolean, Standard: false)*
- **Gesundheitsdaten-Export** *(Boolean, Standard: false)*

### Pflege-Services
- **start_grooming_session Service** *(Boolean, Standard: false)*
- **Pflegeerinnerungen** *(Boolean, Standard: false)*
- **Pflege-Intervall** *(Wochen, Standard: 4)*

### System-Services
- **activate_emergency_mode Service** *(Boolean, Standard: true)*
- **toggle_visitor_mode Service** *(Boolean, Standard: true)*
- **daily_reset Service** *(Boolean, Standard: true)*
- **generate_report Service** *(Boolean, Standard: false)*

---

## 🔧 MODUL 9: System-Integration und Hardware (OPTIONAL)

### Home Assistant Integration
- **HA-Restart-Persistence** *(Boolean, Standard: true)*
- **State-Backup-Intervall** *(Stunden, Standard: 24)*
- **Entity-Naming-Prefix** *(Text, Standard: Hundename)*

### Hardware-Integration
**Sensoren-Integration**
- **Gewichts-Sensor Integration** *(Boolean, Standard: false)*
- **Gewichts-Sensor Entity** *(Entity-Auswahl)*
- **Temperatur-Sensor Integration** *(Boolean, Standard: false)*
- **Temperatur-Sensor Entity** *(Entity-Auswahl)*

**Smart Home Integration**
- **Türsensoren für Outside-Detection** *(Boolean, Standard: false)*
- **Türsensor-Entities** *(Multi-Entity-Auswahl)*
- **Kamera-Integration für Überwachung** *(Boolean, Standard: false)*
- **Kamera-Entities** *(Multi-Entity-Auswahl)*

**IoT-Device Integration**
- **MQTT-Broker für IoT-Geräte** *(Boolean, Standard: false)*
- **MQTT-Broker-Konfiguration** *(Host, Port, Username, Password)*
- **Custom-Device-Endpoints** *(Multi-Entry, Advanced)*

### Externe API-Integration
- **Wetterservice-Integration** *(Boolean, Standard: false)*
- **Wetterservice-Typ** *(Optionen: "OpenWeatherMap", "Weather.com", "Home Assistant Weather")*
- **API-Key** *(Text, falls erforderlich)*

- **Veterinär-Software-Integration** *(Boolean, Standard: false)*
- **Vet-Software-API-Endpoint** *(URL, Advanced)*
- **API-Credentials** *(Username/Password oder API-Key)*

---

## 📦 MODUL 10: Datenverwaltung und Backup (OPTIONAL)

### Daten-Retention
- **Aktivitätsdaten-Aufbewahrung** *(Tage)*
  - Optionen: [30, 90, 180, 365, "Unbegrenzt"]
  - Standard: 90 Tage

- **GPS-Routen-Aufbewahrung** *(Anzahl Routen)*
  - Bereich: 5-100
  - Standard: 20

- **Gesundheitsdaten-Aufbewahrung** *(Tage)*
  - Standard: 365 Tage

### Backup-Konfiguration
- **Automatische Backups aktivieren** *(Boolean, Standard: false)*
- **Backup-Intervall** *(Optionen: "Täglich", "Wöchentlich", "Monatlich")*
- **Backup-Speicherort** *(Pfad, Standard: "/config/paw_control_backups")*
- **Backup-Anzahl-Limit** *(Number, Standard: 10)*

### Datenexport
- **Export-Funktionen aktivieren** *(Boolean, Standard: false)*
- **Export-Formate** *(Multi-Select)*
  - CSV
  - JSON  
  - PDF-Reports
  - GPX (für GPS-Routen)

### Datenschutz und Sicherheit
- **Daten-Anonymisierung bei Export** *(Boolean, Standard: true)*
- **GPS-Daten-Verschlüsselung** *(Boolean, Standard: false)*
- **Backup-Verschlüsselung** *(Boolean, Standard: false)*

---

## 🚀 MODUL 11: Performance und Wartung (OPTIONAL)

### Performance-Optimierung
- **Memory-Management** *(Optionen: "Conservative", "Balanced", "Performance")*
- **Update-Intervall-Optimierung** *(Boolean, Standard: true)*
- **Entity-Cleanup bei Neustart** *(Boolean, Standard: true)*

### Logging und Debugging
- **Debug-Logging aktivieren** *(Boolean, Standard: false)*
- **Log-Level** *(Optionen: "DEBUG", "INFO", "WARNING", "ERROR")*
- **GPS-Trace-Logging** *(Boolean, Standard: false)*
- **Service-Call-Logging** *(Boolean, Standard: false)*

### System-Monitoring
- **Performance-Monitoring** *(Boolean, Standard: false)*
- **Memory-Usage-Tracking** *(Boolean, Standard: false)*
- **Entity-Health-Monitoring** *(Boolean, Standard: true)*

### Update-Management
- **Auto-Update-Checks** *(Boolean, Standard: true)*
- **Beta-Features aktivieren** *(Boolean, Standard: false)*
- **Update-Benachrichtigungen** *(Boolean, Standard: true)*

---

## 🎯 MODUL 12: Experteneinstellungen (ADVANCED)

### GPS-Advanced-Konfiguration
- **Custom-GPS-Provider-Settings** *(JSON-Konfiguration)*
- **Coordinate-System-Transformation** *(Boolean, Standard: false)*
- **GPS-Drift-Correction** *(Boolean, Standard: true)*
- **Signal-Noise-Filtering** *(Boolean, Standard: true)*

### Service-Custom-Konfiguration
- **Custom-Service-Timeouts** *(Sekunden-Mapping)*
- **Retry-Logic-Konfiguration** *(Advanced)*
- **Error-Handling-Strategien** *(Advanced)*

### Entity-Management
- **Entity-ID-Patterns** *(Template-Konfiguration)*
- **Custom-Icon-Mappings** *(JSON)*
- **Entity-State-Templates** *(YAML)*

### Integration-Hooks
- **Pre/Post-Service-Hooks** *(Script-Referenzen)*
- **Custom-Automation-Trigger** *(YAML)*
- **Event-Bus-Integration** *(Advanced)*

---

## ✅ ZUSAMMENFASSUNG DER SETUP-KATEGORIEN

### ERFORDERLICHE KONFIGURATION
1. **Hundename** (Pflichtfeld)

### MODULARE OPTIONAL-KONFIGURATION
1. **Hundedaten-Erweiterung** (9 Parameter)
2. **Fütterungssystem** (15 Parameter)  
3. **GPS-Tracking-System** (35+ Parameter)
4. **Gesundheitsüberwachung** (18 Parameter)
5. **Benachrichtigungssystem** (25 Parameter)
6. **Automatisierungssystem** (20 Parameter)
7. **Dashboard-System** (15 Parameter)
8. **Service-Konfiguration** (20 Parameter)
9. **Hardware-Integration** (15 Parameter)
10. **Datenverwaltung** (12 Parameter)
11. **Performance-Tuning** (10 Parameter)
12. **Experteneinstellungen** (15 Parameter)

### GESAMT-PARAMETER-ANZAHL
- **Erforderlich**: 1 Parameter
- **Optional**: 200+ Parameter
- **Total**: 200+ konfigurierbare Einstellungen

### SETUP-FLOW-EMPFEHLUNG
1. **Quick Setup** (5 Min): Nur Grunddaten + GPS-Quelle
2. **Standard Setup** (15 Min): + Fütterung + Benachrichtigungen 
3. **Advanced Setup** (30 Min): + Gesundheit + Automatisierung
4. **Expert Setup** (60+ Min): Vollständige Konfiguration aller Module

Dieses Setup-System ermöglicht eine vollständige Anpassung von einer Basis-Hundeverfolgung bis hin zu einem professionellen Tierpflege-Management-System auf Enterprise-Niveau.

---

### Medikations-Mapping (ab v15)
- Konfiguration **pro Hund** im **Options-Flow → medication_mapping**.
- Für jeden Hund stehen **Slots 1..3** zur Verfügung; jeweils Mehrfachauswahl der Mahlzeiten (**Frühstück/Mittag/Abend**).
- Die früheren Switches `switch.pawcontrol_*_medication_*_at_*` sind **entfernt**.

---

## GPS-Setup – kompatibel zu *PawTracker*-Beispielen
Die Integration akzeptiert die in den Guides verwendeten Services **auch unter `pawtracker.*`** (Alias).
Beispiele aus den Markdown-Dateien funktionieren daher direkt (z. B. `pawtracker.setup_automatic_gps`, `pawtracker.update_gps_simple`).



### Geofencing & Medien-Export
- Sicherheitszonen (leave/enter) mit Events + Benachrichtigungen. Schneller Toggle via Service `pawcontrol.toggle_geofence_alerts`.
- Routen-Export optional direkt ins **/media/pawcontrol_routes** (Media Browser) – setze `to_media: true` beim Service `pawcontrol.gps_export_last_route`.
- Auto-Profile (bewegungsbasiert): `sensor.pawcontrol_*_gps_profile` zeigt aktuelles Profil (`battery_saver`/`high_accuracy`).



### Beispiele & Services
- Beispiele unter `examples/gps_automation_examples.yaml` (aus den bereitgestellten Guides).
- Neue Services: `pawcontrol.gps_pause_tracking`, `pawcontrol.gps_resume_tracking`.


### Blueprints
- Siehe `blueprints/automation/pawcontrol/` für fertige Automations-Vorlagen.

- Beispiel-Dashboard: `dashboards/pawcontrol_dashboard.yaml` (DOG_ID im YAML ersetzen).

- Blueprint: `blueprints/automation/pawcontrol/medication_every_x_hours.yaml` – erinnert alle X Stunden.

- Optionen: **Medikations-Zuordnung** – pro Hund Multi-Select, welche Slots zu welchen Mahlzeiten gehören.

- Siehe `docs/SETUP_CONFIGURATION.md`
- Siehe `docs/ERWEITERT_KOMPLETT.md`
- Siehe `docs/ANALYSE_1.md`
- Siehe `docs/GPS_INTEGRATION_GUIDE.md`
- Siehe `docs/GPS_UPDATE_README.md`
- Siehe `docs/AUTOMATIC_GPS_TRACKING.md`

![Paw Control](assets/logo.png)

- Optionen: **Hunde verwalten** – schnelle Eingabe als `id:name` je Zeile.

## Schnellstart
- HACS installieren → Paw Control hinzufügen → Optionen öffnen → **Hunde verwalten** ausfüllen.

- Optionen: **Module aktivieren** – Multi-Select für GPS / Feeding / Health / Walk.

- **Geräte-Trigger**: Für jeden Hund in den Automationen verfügbar – Start/Ende Spaziergang, Sicherheitszone betreten/verlassen.

- Optionen: **Erinnerungen & Benachrichtigungen** – Notify-Ziel, Intervall, Snooze, optional Auto-Erinnerung.

- Optionen: **Medikamente – Zuordnung je Slot** – pro Hund Slot 1–3 den Mahlzeiten (Frühstück/Mittag/Abend) zuordnen.
