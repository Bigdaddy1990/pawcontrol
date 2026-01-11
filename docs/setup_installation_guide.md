# 🐕 Paw Control - Setup & Installation Guide für erweiterte Features

Dieser umfassende Guide führt Sie durch die Installation und Konfiguration der erweiterten Paw Control Features, einschließlich GPS-Tracking, Garden Tracking, Automatisierungen und Dashboard-Konfiguration. Paw Control ist eine **Custom-Integration** und richtet sich am Platinum-Qualitätsstandard aus, erhält jedoch kein offizielles Platinum-Badge von Home Assistant.

## 📋 Inhaltsverzeichnis

1. [Voraussetzungen](#voraussetzungen)
2. [Installation](#installation)
3. [Grundkonfiguration](#grundkonfiguration)
4. [Erweiterte Features](#erweiterte-features)
5. [Garden Tracking Setup](#garden-tracking-setup)
6. [Dashboard-Setup](#dashboard-setup)
7. [Automatisierungen](#automatisierungen)
8. [Mobile App Integration](#mobile-app-integration)
9. [Troubleshooting](#troubleshooting)
10. [Performance-Optimierung](#performance-optimierung)
11. [Deinstallation & Aufräumen](#deinstallation--aufräumen)

## 🔧 Voraussetzungen

### Mindestanforderungen

- **Home Assistant:** Version 2025.8.0 oder höher
- **Python:** Version 3.12 oder höher
- **Speicherplatz:** Mindestens 100 MB freier Speicher
- **RAM:** Mindestens 2 GB verfügbarer Arbeitsspeicher
- **Internetverbindung:** Für GPS-Funktionen und Updates

### Empfohlene Hardware

- **Raspberry Pi 4** (4GB RAM) oder vergleichbar
- **GPS-Tracker** für Hunde (z.B. Tractive, Fi, Apple AirTag)
- **Smartphone** mit Home Assistant Mobile App
- **Smart Home Sensoren** (optional):
  - Türsensoren für automatische Walk- und Garden-Erkennung
  - Gartentür-Sensor für Garden Tracking
  - Waage für Gewichtsüberwachung
  - Kamera für Überwachung
  - Wetterstationen für Outdoor-Aktivitäten

### Unterstützte GPS-Tracker

| Tracker | Status | Features | Setup-Anleitung |
|---------|--------|----------|-----------------|
| Tractive GPS | ✅ Vollständig | Live-Tracking, Geofencing | [Setup →](#tractive-setup) |
| Fi Smart Dog Collar | ✅ Vollständig | GPS, Aktivität, Schlaf | [Setup →](#fi-setup) |
| Apple AirTag | ⚠️ Begrenzt | Standort-Updates | [Setup →](#airtag-setup) |
| Generic GPS Logger | ✅ Basis | GPS-Koordinaten | [Setup →](#generic-gps-setup) |
| Whistle GPS | 🔄 In Entwicklung | - | Bald verfügbar |

### Unterstützte Sensoren für Garden Tracking

| Sensor-Typ | Empfohlene Modelle | Zweck | Setup-Komplexität |
|------------|-------------------|-------|-------------------|
| Türsensor | Aqara, Zigbee, Z-Wave | Garden-Ein/Ausgang | ⭐ Einfach |
| Bewegungsmelder | PIR, Zigbee | Gartenaktivität | ⭐⭐ Mittel |
| Kamera | Frigate, Reolink | Visuelle Überwachung | ⭐⭐⭐ Komplex |
| Wetterdaten | OpenWeatherMap, local | Wetter-Integration | ⭐ Einfach |

## 📦 Installation

### Option 1: HACS Installation (Empfohlen)

1. **HACS öffnen** in Home Assistant
2. **Integrations** → **Explore & Download Repositories**
3. Nach **"Paw Control"** suchen
4. **Download** klicken
5. **Home Assistant neu starten**

### Option 2: Manuelle Installation

```bash
# In das Home Assistant Verzeichnis wechseln
cd /config

# Repository klonen
git clone https://github.com/BigDaddy1990/pawcontrol.git

# Integration ins custom_components Verzeichnis kopieren
cp -r pawcontrol/custom_components/pawcontrol custom_components/

# Home Assistant neu starten
```

### Option 3: Docker Installation

```dockerfile
# Fügen Sie zu Ihrer docker-compose.yml hinzu:
version: '3.8'
services:
  homeassistant:
    image: homeassistant/home-assistant:latest
    volumes:
      - ./pawcontrol:/config/custom_components/pawcontrol
      - ./config:/config
    # ... weitere Konfiguration
```

## ⚙️ Grundkonfiguration

### Schritt 1: Integration hinzufügen

1. **Einstellungen** → **Geräte & Dienste** öffnen
2. **Integration hinzufügen** klicken
3. Nach **"Paw Control"** suchen
4. Integration auswählen und einrichten

### Schritt 2: Ersten Hund konfigurieren

```yaml
# Beispiel-Konfiguration für den ersten Hund
dog_config:
  dog_id: "buddy"
  dog_name: "Buddy"
  dog_breed: "Golden Retriever"
  dog_age: 3
  dog_weight: 30.0
  dog_size: "medium"
  modules:
    walk: true
    feeding: true
    health: true
    gps: true
    garden: true           # NEW: Garden Tracking aktivieren
    notifications: true
    dashboard: true
    grooming: true
    medication: false      # Nur wenn benötigt
    training: true
```

### Schritt 3: Grundlegende Einstellungen

#### Geofencing konfigurieren
```yaml
geofence_settings:
  geofencing_enabled: true
  geofence_lat: 52.520008  # Ihre Heimkoordinaten
  geofence_lon: 13.404954
  geofence_radius_m: 150   # Radius in Metern
  geofence_alerts_enabled: true
  use_home_location: true  # HA-Koordinaten verwenden
```

#### Benachrichtigungen einrichten
```yaml
notifications:
  notifications_enabled: true
  quiet_hours_enabled: true
  quiet_start: "22:00"
  quiet_end: "07:00"
  reminder_repeat_min: 30
  priority_notifications: true
  notification_channels:
    - mobile
    - persistent
```

#### Garden Tracking Basis-Konfiguration
```yaml
garden_settings:
  garden_enabled: true
  auto_poop_detection: true      # Automatische Poop-Erkennung
  confirmation_required: true    # Push-Rückfragen aktivieren
  session_timeout: 1800         # 30 Min Session-Timeout
  weather_integration: true     # Wetter für Garden Sessions
  door_sensor_entity: "binary_sensor.garden_door"  # Optional
```

## 🚀 Erweiterte Features

### GPS-Tracking Setup

#### 1. GPS-Einstellungen optimieren

```yaml
gps_settings:
  gps_enabled: true
  gps_accuracy_filter: 50      # Mindestgenauigkeit in Metern
  gps_distance_filter: 10      # Mindestabstand zwischen Punkten
  gps_update_interval: 30      # Sekunden zwischen Updates
  auto_start_walk: false       # Manuelle Walk-Starts
  auto_end_walk: true          # Automatisches Ende bei Heimkehr
  route_recording: true        # Routen aufzeichnen
  route_history_days: 90       # Aufbewahrung der Routenhistorie
```

#### 2. Webhook für GPS-Tracking einrichten

```bash
# Webhook-URL für GPS-Tracker konfigurieren
# Format: https://ihr-ha-server.com/api/webhook/[WEBHOOK_ID]

# Beispiel für Tractive:
curl -X POST "https://ihr-ha-server.com/api/webhook/paw_control_gps" \
  -H "Content-Type: application/json" \
  -d '{
    "dog_id": "buddy",
    "latitude": 52.520008,
    "longitude": 13.404954,
    "accuracy": 5,
    "timestamp": "2025-08-17T10:30:00Z"
  }'
```

#### 3. GPS-Services nutzen

```yaml
# Services für GPS-Steuerung
services:
  # Walk starten
  - service: pawcontrol.gps_start_walk
    data:
      dog_id: "buddy"
      label: "Morgenspaziergang"

  # Walk beenden
  - service: pawcontrol.gps_end_walk
    data:
      dog_id: "buddy"
      notes: "Schöner Spaziergang im Park"
      rating: 5

  # Position manuell setzen
  - service: pawcontrol.gps_post_location
    data:
      dog_id: "buddy"
      latitude: 52.520008
      longitude: 13.404954
      accuracy_m: 5
```

### Datenquellen-Integration

#### 1. Person-Entitäten verknüpfen

```yaml
data_sources:
  person_entities:
    - person.owner_1
    - person.owner_2
  device_trackers:
    - device_tracker.owner_phone
    - device_tracker.dog_gps_tracker
  door_sensor: binary_sensor.front_door
  garden_door_sensor: binary_sensor.garden_door  # NEW: Garden-spezifisch
  weather: weather.home
  calendar: calendar.family_events
  auto_discovery: true
  fallback_tracking: true
```

#### 2. Türsensor für Walk-Erkennung

```yaml
# Binary Sensor für Haustür
binary_sensor:
  - platform: template
    sensors:
      front_door_walk_detection:
        friendly_name: "Walk Detection"
        value_template: >
          {% set door_open = is_state('binary_sensor.front_door', 'on') %}
          {% set person_away = is_state('person.owner', 'not_home') %}
          {% set last_walk = states('sensor.buddy_last_walk_hours') | float %}
          {{ door_open and person_away and last_walk > 2 }}
        icon_template: >
          {% if is_state('binary_sensor.front_door_walk_detection', 'on') %}
            mdi:walk
          {% else %}
            mdi:door
          {% endif %}
```

### Health-Monitoring

#### 1. Gewichtsüberwachung

```yaml
# Template Sensor für Gewichtstrends
sensor:
  - platform: template
    sensors:
      buddy_weight_trend:
        friendly_name: "Buddy Weight Trend"
        value_template: >
          {% set current = states('sensor.buddy_weight') | float %}
          {% set previous = state_attr('sensor.buddy_weight', 'previous_value') | float %}
          {% if current > previous + 0.5 %}
            increasing
          {% elif current < previous - 0.5 %}
            decreasing
          {% else %}
            stable
          {% endif %}
        icon_template: >
          {% set trend = states('sensor.buddy_weight_trend') %}
          {% if trend == 'increasing' %}
            mdi:trending-up
          {% elif trend == 'decreasing' %}
            mdi:trending-down
          {% else %}
            mdi:trending-neutral
          {% endif %}

# Automation für Gewichtsalerts
automation:
  - alias: "Weight Change Alert"
    trigger:
      - platform: state
        entity_id: sensor.buddy_weight
    condition:
      - condition: template
        value_template: >
          {% set old = trigger.from_state.state | float %}
          {% set new = trigger.to_state.state | float %}
          {{ (new - old) | abs > 1.0 }}
    action:
      - service: notify.mobile_app_phone
        data:
          title: "⚖️ Gewichtsänderung erkannt"
          message: >
            Buddy's Gewicht hat sich von {{ trigger.from_state.state }}kg
            auf {{ trigger.to_state.state }}kg geändert.
```

#### 2. Medikations-Erinnerungen

```yaml
# Input für Medikationsplan
input_datetime:
  buddy_morning_meds:
    name: "Buddy Morgen Medikation"
    has_time: true
    has_date: false
    initial: "08:00:00"

  buddy_evening_meds:
    name: "Buddy Abend Medikation"
    has_time: true
    has_date: false
    initial: "20:00:00"

# Automation für Medikations-Erinnerungen
automation:
  - alias: "Medication Reminder"
    trigger:
      - platform: time
        at: input_datetime.buddy_morning_meds
        id: "morning"
      - platform: time
        at: input_datetime.buddy_evening_meds
        id: "evening"
    condition:
      - condition: state
        entity_id: input_boolean.medication_reminders_enabled
        state: "on"
    action:
      - service: pawcontrol.send_medication_reminder
        data:
          dog_id: "buddy"
          medication: "{{ trigger.id }}_medication"
      - service: notify.mobile_app_phone
        data:
          title: "💊 Medikation Zeit"
          message: "Zeit für Buddy's {{ trigger.id }} Medikation!"
          data:
            actions:
              - action: "MEDICATION_GIVEN"
                title: "Gegeben"
              - action: "SNOOZE_1H"
                title: "1h später"
```

## 🌱 Garden Tracking Setup

Das Garden Tracking System überwacht automatisch Gartenbesuche, protokolliert Aktivitäten und bietet intelligente Poop-Erkennung mit Push-Rückfragen.

### 1. Garden Tracking Konfiguration

#### Basis-Einrichtung

```yaml
# Garden Tracking Konfiguration
garden_tracking:
  enabled: true
  auto_poop_detection: true        # Automatische Poop-Rückfragen
  confirmation_required: true      # Push-Bestätigungen aktivieren
  session_timeout_minutes: 30      # Session-Timeout
  weather_integration: true        # Wetter-Daten integrieren
  activity_types:                  # Verfügbare Aktivitätstypen
    - general                      # Allgemeine Aktivität
    - poop                         # Geschäft erledigen
    - play                         # Spielen
    - sniffing                     # Schnüffeln
    - digging                      # Graben
    - resting                      # Ausruhen
```

#### Türsensor für automatische Garden-Erkennung

```yaml
# Garden Door Sensor Setup
binary_sensor:
  - platform: template
    sensors:
      garden_door_detection:
        friendly_name: "Garden Door Detection"
        device_class: door
        value_template: >
          {{ is_state('binary_sensor.garden_door', 'on') }}
        icon_template: >
          {% if is_state('binary_sensor.garden_door', 'on') %}
            mdi:door-open
          {% else %}
            mdi:door-closed
          {% endif %}

# Garden Entry Detection
      garden_entry_detection:
        friendly_name: "Garden Entry Detection"
        value_template: >
          {% set door_open = is_state('binary_sensor.garden_door', 'on') %}
          {% set door_open_time = (as_timestamp(now()) - as_timestamp(states.binary_sensor.garden_door.last_changed)) / 60 %}
          {% set is_daytime = now().hour >= 6 and now().hour <= 22 %}
          {% set weather_ok = not is_state('weather.home', 'rainy') %}
          {{ door_open and door_open_time > 0.5 and is_daytime and weather_ok }}
        icon_template: >
          {% if is_state('binary_sensor.garden_entry_detection', 'on') %}
            mdi:garden
          {% else %}
            mdi:home
          {% endif %}
```

### 2. Garden Services einrichten

#### Service-Aufrufe für Garden Tracking

```yaml
# Garden Session Services
services:
  # Garden Session starten
  start_garden_session:
    service: pawcontrol.start_garden_session
    data:
      dog_id: "buddy"
      detection_method: "manual"  # oder "door_sensor", "auto"
      weather_conditions: "{{ states('weather.home') }}"
      temperature: "{{ states('sensor.outdoor_temperature') | float }}"

  # Garden Session beenden
  end_garden_session:
    service: pawcontrol.end_garden_session
    data:
      dog_id: "buddy"
      notes: "Schöne Zeit im Garten"
      activities:
        - type: "play"
          duration_seconds: 300
          location: "Rasen"
          notes: "Ball gespielt"
          confirmed: true

  # Garden Aktivität hinzufügen
  add_garden_activity:
    service: pawcontrol.add_garden_activity
    data:
      dog_id: "buddy"
      activity_type: "poop"  # general, poop, play, sniffing, digging, resting
      duration_seconds: 60
      location: "Lieblingsstelle"
      notes: "Normaler Poop"
      confirmed: true

  # Poop-Bestätigung
  confirm_garden_poop:
    service: pawcontrol.confirm_garden_poop
    data:
      dog_id: "buddy"
      confirmed: true  # oder false
      quality: "good"  # excellent, good, normal, soft, loose, watery
      size: "normal"   # small, normal, large
      location: "Hinten links"
```

### 3. Garden Entities und Sensoren

Nach der Einrichtung werden automatisch folgende Entitäten erstellt:

#### Garden Sensoren
```yaml
# Automatisch erstellte Garden Sensoren
sensor.buddy_garden_time_today:           # Heutige Gartenzeit in Minuten
sensor.buddy_garden_sessions_today:       # Anzahl Gartensessions heute
sensor.buddy_garden_poop_count_today:     # Poop-Events heute
sensor.buddy_last_garden_session:         # Zeitpunkt der letzten Session
sensor.buddy_garden_activities_count:     # Gesamtanzahl Gartenaktivitäten
sensor.buddy_avg_garden_duration:         # Durchschnittliche Session-Dauer
sensor.buddy_garden_stats_weekly:         # Wöchentliche Gartenstatistiken
sensor.buddy_favorite_garden_activities:  # Lieblings-Gartenaktivitäten
```

#### Garden Binary Sensoren
```yaml
# Garden Status Sensoren
binary_sensor.buddy_garden_session_active:  # Aktive Gartensession
binary_sensor.buddy_in_garden:              # Derzeit im Garten
binary_sensor.buddy_garden_poop_pending:    # Poop-Bestätigung ausstehend
```

#### Garden Buttons
```yaml
# Garden Control Buttons
button.buddy_start_garden_session:      # Garden Session starten
button.buddy_end_garden_session:        # Garden Session beenden
button.buddy_log_garden_activity:       # Gartenaktivität protokollieren
button.buddy_confirm_garden_poop:       # Garden Poop bestätigen
```

### 4. Garden Automatisierungen

#### Automatische Garden-Erkennung

```yaml
automation:
  - alias: "Automatic Garden Detection"
    description: "Erkennt automatisch, wenn Buddy in den Garten geht"
    trigger:
      - platform: state
        entity_id: binary_sensor.garden_door
        to: "on"
        for: "00:00:30"  # 30 Sekunden offen
    condition:
      - condition: state
        entity_id: binary_sensor.buddy_garden_session_active
        state: "off"
      - condition: time
        after: "06:00:00"
        before: "22:00:00"
      - condition: template
        value_template: "{{ not is_state('weather.home', 'rainy') }}"
    action:
      # Benachrichtigung mit Bestätigung
      - service: notify.mobile_app_phone
        data:
          title: "🌱 Garten-Erkennung"
          message: "Buddy ist in den Garten gegangen!"
          data:
            tag: "garden_detection"
            actions:
              - action: "START_GARDEN_SESSION"
                title: "✅ Gartensession starten"
              - action: "NOT_GARDEN"
                title: "❌ Kein Gartengang"
            timeout: 60  # 1 Minute für Antwort

      # Auto-start nach 1 Minute ohne Antwort
      - delay: "00:01:00"
      - condition: state
        entity_id: binary_sensor.buddy_garden_session_active
        state: "off"
      - service: pawcontrol.start_garden_session
        data:
          dog_id: "buddy"
          detection_method: "door_sensor"
          weather_conditions: "{{ states('weather.home') }}"
          temperature: "{{ states('sensor.outdoor_temperature') | float }}"

  - alias: "Handle Garden Detection Response"
    description: "Verarbeitet Antworten auf Garden-Erkennungs-Benachrichtigungen"
    trigger:
      - platform: event
        event_type: mobile_app_notification_action
        event_data:
          action: "START_GARDEN_SESSION"
        id: "start_session"
      - platform: event
        event_type: mobile_app_notification_action
        event_data:
          action: "NOT_GARDEN"
        id: "not_garden"
    action:
      - choose:
          - conditions:
              - condition: template
                value_template: "{{ trigger.id == 'start_session' }}"
            sequence:
              - service: pawcontrol.start_garden_session
                data:
                  dog_id: "buddy"
                  detection_method: "manual_confirmed"
                  weather_conditions: "{{ states('weather.home') }}"
                  temperature: "{{ states('sensor.outdoor_temperature') | float }}"
          - conditions:
              - condition: template
                value_template: "{{ trigger.id == 'not_garden' }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "🏠 Garten-Erkennung"
                  message: "Gartengang als 'Nicht im Garten' markiert."
                  data:
                    tag: "garden_detection"
```

#### Intelligente Poop-Erkennung

```yaml
automation:
  - alias: "Garden Poop Detection"
    description: "Fragt nach 3 Minuten im Garten nach Poop"
    trigger:
      - platform: state
        entity_id: binary_sensor.buddy_garden_session_active
        to: "on"
        for: "00:03:00"  # Nach 3 Minuten im Garten
    condition:
      - condition: template
        value_template: "{{ states('sensor.buddy_garden_poop_count_today') | int == 0 }}"
      - condition: time
        after: "06:00:00"
        before: "22:00:00"
    action:
      - service: notify.mobile_app_phone
        data:
          title: "💩 Poop Check"
          message: "Hat Buddy im Garten sein Geschäft erledigt?"
          data:
            tag: "garden_poop_check"
            actions:
              - action: "CONFIRM_GARDEN_POOP_YES"
                title: "✅ Ja, hatte Poop"
              - action: "CONFIRM_GARDEN_POOP_NO"
                title: "❌ Nein, kein Poop"
            timeout: 300  # 5 Minuten Timeout

  - alias: "Handle Garden Poop Confirmation"
    description: "Verarbeitet Poop-Bestätigungen aus Benachrichtigungen"
    trigger:
      - platform: event
        event_type: mobile_app_notification_action
        event_data:
          action: "CONFIRM_GARDEN_POOP_YES"
        id: "poop_yes"
      - platform: event
        event_type: mobile_app_notification_action
        event_data:
          action: "CONFIRM_GARDEN_POOP_NO"
        id: "poop_no"
    action:
      - choose:
          - conditions:
              - condition: template
                value_template: "{{ trigger.id == 'poop_yes' }}"
            sequence:
              - service: pawcontrol.confirm_garden_poop
                data:
                  dog_id: "buddy"
                  confirmed: true
                  quality: "normal"
                  size: "normal"
                  location: "Garden"
              - service: notify.mobile_app_phone
                data:
                  title: "✅ Poop bestätigt"
                  message: "Buddy's Garten-Poop wurde protokolliert."
                  data:
                    tag: "garden_poop_check"
          - conditions:
              - condition: template
                value_template: "{{ trigger.id == 'poop_no' }}"
            sequence:
              - service: pawcontrol.confirm_garden_poop
                data:
                  dog_id: "buddy"
                  confirmed: false
              - service: notify.mobile_app_phone
                data:
                  title: "ℹ️ Poop verneint"
                  message: "Kein Poop im Garten notiert."
                  data:
                    tag: "garden_poop_check"
```

#### Garden Session Auto-End

```yaml
automation:
  - alias: "Garden Session Auto End"
    description: "Beendet Gartensession automatisch bei Türschließung"
    trigger:
      - platform: state
        entity_id: binary_sensor.garden_door
        to: "off"
        for: "00:02:00"  # 2 Minuten geschlossen
    condition:
      - condition: state
        entity_id: binary_sensor.buddy_garden_session_active
        state: "on"
    action:
      - service: pawcontrol.end_garden_session
        data:
          dog_id: "buddy"
          notes: "Automatisch beendet - Tür geschlossen"
      - service: notify.mobile_app_phone
        data:
          title: "🏠 Gartensession beendet"
          message: >
            Buddy's Gartensession automatisch beendet.
            Dauer: {{ states('sensor.buddy_garden_time_today') }} Minuten.
          data:
            tag: "garden_session_end"
```

### 5. Garden Dashboard Komponenten

#### Garden Tracking Card

```yaml
# Garden Tracking Dashboard Card
type: vertical-stack
cards:
  # Garden Status
  - type: horizontal-stack
    cards:
      - type: custom:mushroom-entity-card
        entity: binary_sensor.buddy_garden_session_active
        name: "Garten Status"
        icon: "mdi:flower"
        icon_color: >
          {% if is_state('binary_sensor.buddy_garden_session_active', 'on') %}
            green
          {% else %}
            grey
          {% endif %}
      - type: custom:mushroom-entity-card
        entity: sensor.buddy_garden_time_today
        name: "Heute im Garten"
        icon: "mdi:clock"
      - type: custom:mushroom-entity-card
        entity: sensor.buddy_garden_poop_count_today
        name: "Poop Events"
        icon: "mdi:poop"

  # Garden Session aktiv (conditional)
  - type: conditional
    conditions:
      - entity: binary_sensor.buddy_garden_session_active
        state: "on"
    card:
      type: entities
      title: "🌱 Aktuelle Gartensession"
      entities:
        - entity: sensor.buddy_garden_time_today
          name: "Session-Dauer"
        - entity: sensor.buddy_garden_activities_count
          name: "Aktivitäten"
        - entity: sensor.buddy_garden_poop_count_today
          name: "Poop Events heute"
      footer:
        type: buttons
        entities:
          - entity: button.buddy_log_garden_activity
            name: "Aktivität protokollieren"
            tap_action:
              action: call-service
              service: pawcontrol.add_garden_activity
              service_data:
                dog_id: "buddy"
                activity_type: "play"
                location: "Garten"
          - entity: button.buddy_end_garden_session
            name: "Session beenden"
            tap_action:
              action: call-service
              service: pawcontrol.end_garden_session
              service_data:
                dog_id: "buddy"
                notes: "Manuell beendet"

  # Garden Quick Actions
  - type: horizontal-stack
    cards:
      - type: custom:mushroom-entity-card
        entity: button.buddy_start_garden_session
        name: "Garten Start"
        icon: "mdi:play"
        tap_action:
          action: call-service
          service: pawcontrol.start_garden_session
          service_data:
            dog_id: "buddy"
            detection_method: "manual"
      - type: custom:mushroom-entity-card
        entity: button.buddy_confirm_garden_poop
        name: "Poop bestätigen"
        icon: "mdi:check"
        tap_action:
          action: call-service
          service: pawcontrol.confirm_garden_poop
          service_data:
            dog_id: "buddy"
            confirmed: true
            quality: "normal"
            size: "normal"

  # Garden Statistics
  - type: custom:apexcharts-card
    header:
      title: "Garden Aktivität (7 Tage)"
    graph_span: 7d
    series:
      - entity: sensor.buddy_garden_time_today
        name: "Gartenzeit (Min)"
        type: column
      - entity: sensor.buddy_garden_sessions_today
        name: "Sessions"
        type: line
```

## 📱 Dashboard-Setup

### Schritt 1: Dashboard-Datei erstellen

Erstellen Sie eine neue Dashboard-Datei in `/config/dashboards/paw_control.yaml`:

```yaml
# Kopieren Sie den Dashboard-Code aus den Automation Templates
# Pfad: /config/dashboards/paw_control.yaml
```

### Schritt 2: Dashboard in Home Assistant registrieren

```yaml
# configuration.yaml
lovelace:
  dashboards:
    paw-control:
      mode: yaml
      title: Paw Control
      icon: mdi:dog
      show_in_sidebar: true
      filename: dashboards/paw_control.yaml
```

### Schritt 3: Custom Cards installieren

Erforderliche HACS-Cards:
- **Mushroom Cards**: Moderne UI-Komponenten
- **ApexCharts Card**: Für Diagramme und Statistiken
- **Auto-Entities**: Dynamische Entitätslisten
- **Card-Mod**: Für CSS-Anpassungen

```bash
# HACS → Frontend → Explore & Download Repositories
# Suchen und installieren:
# - mushroom
# - apexcharts-card
# - auto-entities
# - lovelace-card-mod
```

### Schritt 4: Mobile Dashboard optimieren

```yaml
# Mobile-optimierte Karten
mobile_optimized_cards:
  - type: custom:mushroom-chips-card
    chips:
      - type: entity
        entity: binary_sensor.buddy_walk_in_progress
        icon: mdi:walk
      - type: entity
        entity: binary_sensor.buddy_garden_session_active
        icon: mdi:flower
      - type: entity
        entity: sensor.buddy_last_walk_hours
        icon: mdi:clock
      - type: action
        icon: mdi:play
        tap_action:
          action: call-service
          service: pawcontrol.gps_start_walk
          service_data:
            dog_id: "buddy"
      - type: action
        icon: mdi:garden
        tap_action:
          action: call-service
          service: pawcontrol.start_garden_session
          service_data:
            dog_id: "buddy"
            detection_method: "manual"
```

## 🤖 Automatisierungen

### 1. Basis-Automatisierungen einrichten

Kopieren Sie die Automatisierungs-Templates in Ihre `automations.yaml`:

```yaml
# automations.yaml - Fügen Sie die Automatisierungen aus den Templates hinzu
# Wichtige Automatisierungen:
# - smart_walk_detection
# - smart_garden_detection
# - feeding_schedule
# - gps_tracking_automation
# - garden_poop_detection
# - health_monitoring
# - weather_walk_planning
```

### 2. Notification Action Handlers

```yaml
# Notification Actions Script
script:
  handle_walk_notification:
    alias: "Handle Walk Notification"
    sequence:
      - choose:
          - conditions:
              - condition: template
                value_template: "{{ action == 'START_WALK' }}"
            sequence:
              - service: pawcontrol.gps_start_walk
                data:
                  dog_id: "{{ dog_id | default('buddy') }}"
          - conditions:
              - condition: template
                value_template: "{{ action == 'SNOOZE_30' }}"
            sequence:
              - delay: "00:30:00"
              - service: script.send_walk_reminder
                data:
                  dog_id: "{{ dog_id | default('buddy') }}"

  handle_garden_notification:
    alias: "Handle Garden Notification"
    sequence:
      - choose:
          - conditions:
              - condition: template
                value_template: "{{ action == 'START_GARDEN' }}"
            sequence:
              - service: pawcontrol.start_garden_session
                data:
                  dog_id: "{{ dog_id | default('buddy') }}"
                  detection_method: "manual_confirmed"
          - conditions:
              - condition: template
                value_template: "{{ action == 'CONFIRM_POOP' }}"
            sequence:
              - service: pawcontrol.confirm_garden_poop
                data:
                  dog_id: "{{ dog_id | default('buddy') }}"
                  confirmed: true
                  quality: "normal"
                  size: "normal"
```

### 3. Erweiterte Logik für Walk-Erkennung

```yaml
# Template für intelligente Walk-Erkennung
template:
  - trigger:
      - platform: state
        entity_id: binary_sensor.front_door
        to: "on"
      - platform: state
        entity_id: device_tracker.owner_phone
        from: "home"
    sensor:
      - name: "Walk Probability"
        state: >
          {% set door_open = is_state('binary_sensor.front_door', 'on') %}
          {% set owner_away = is_state('device_tracker.owner_phone', 'not_home') %}
          {% set time_ok = now().hour >= 6 and now().hour <= 22 %}
          {% set last_walk = states('sensor.buddy_last_walk_hours') | float %}
          {% set weather_ok = not is_state('weather.home', 'rainy') %}

          {% set probability = 0 %}
          {% if door_open %}{% set probability = probability + 30 %}{% endif %}
          {% if owner_away %}{% set probability = probability + 25 %}{% endif %}
          {% if time_ok %}{% set probability = probability + 20 %}{% endif %}
          {% if last_walk > 4 %}{% set probability = probability + 15 %}{% endif %}
          {% if weather_ok %}{% set probability = probability + 10 %}{% endif %}

          {{ probability }}
        unit_of_measurement: "%"

  # Template für Garden-Erkennung
  - trigger:
      - platform: state
        entity_id: binary_sensor.garden_door
        to: "on"
    sensor:
      - name: "Garden Entry Probability"
        state: >
          {% set door_open = is_state('binary_sensor.garden_door', 'on') %}
          {% set time_ok = now().hour >= 6 and now().hour <= 22 %}
          {% set weather_ok = not is_state('weather.home', 'rainy') %}
          {% set last_garden = states('sensor.buddy_last_garden_session') %}
          {% set garden_active = is_state('binary_sensor.buddy_garden_session_active', 'off') %}

          {% set probability = 0 %}
          {% if door_open %}{% set probability = probability + 40 %}{% endif %}
          {% if time_ok %}{% set probability = probability + 25 %}{% endif %}
          {% if weather_ok %}{% set probability = probability + 20 %}{% endif %}
          {% if garden_active %}{% set probability = probability + 15 %}{% endif %}

          {{ probability }}
        unit_of_measurement: "%"
```

## 📱 Mobile App Integration

### 1. Mobile App Konfiguration

```yaml
# configuration.yaml
mobile_app:
  # Automatische Konfiguration über Home Assistant App

# Actionable Notifications einrichten
ios: # oder android:
  push:
    categories:
      - name: walk_reminder
        identifier: walk_reminder
        actions:
          - identifier: START_WALK
            title: "Walk starten"
            activationMode: background
            authenticationRequired: false
          - identifier: SNOOZE_30
            title: "30min später"
            activationMode: background
            authenticationRequired: false

      - name: garden_detection
        identifier: garden_detection
        actions:
          - identifier: START_GARDEN_SESSION
            title: "Gartensession starten"
            activationMode: background
            authenticationRequired: false
          - identifier: NOT_GARDEN
            title: "Kein Gartengang"
            activationMode: background
            authenticationRequired: false

      - name: garden_poop_check
        identifier: garden_poop_check
        actions:
          - identifier: CONFIRM_GARDEN_POOP_YES
            title: "Ja, hatte Poop"
            activationMode: background
            authenticationRequired: false
          - identifier: CONFIRM_GARDEN_POOP_NO
            title: "Nein, kein Poop"
            activationMode: background
            authenticationRequired: false

      - name: feeding_reminder
        identifier: feeding_reminder
        actions:
          - identifier: MARK_FED
            title: "Als gefüttert markieren"
            activationMode: background
            authenticationRequired: false
          - identifier: SNOOZE_15
            title: "15min später"
            activationMode: background
            authenticationRequired: false
```

### 2. Location Tracking

```yaml
# Standort-Tracking für bessere Walk-Erkennung
# In der Home Assistant Mobile App:
# Einstellungen → App-Konfiguration → Location-Zones

# Zone für Hundepark
zone:
  - name: Hundepark
    latitude: 52.525
    longitude: 13.410
    radius: 100
    icon: mdi:pine-tree

  - name: Tierarzt
    latitude: 52.515
    longitude: 13.400
    radius: 50
    icon: mdi:medical-bag

  # NEW: Garden Zone
  - name: Garden
    latitude: 52.520008  # Ihre Gartenkoordinaten
    longitude: 13.404954
    radius: 20
    icon: mdi:flower
```

### 3. Widget-Konfiguration

```yaml
# iOS Widget Entities
# Konfigurieren Sie diese Entitäten für das Home Assistant Widget:
widget_entities:
  - sensor.buddy_name
  - binary_sensor.buddy_walk_in_progress
  - binary_sensor.buddy_garden_session_active
  - sensor.buddy_last_walk_hours
  - sensor.buddy_last_feeding_hours
  - sensor.buddy_garden_time_today
  - button.buddy_start_walk
  - button.buddy_end_walk
  - button.buddy_start_garden_session
  - button.buddy_end_garden_session
```

## 🔧 Troubleshooting

### Häufige Probleme und Lösungen

#### Problem: GPS-Tracking funktioniert nicht

**Lösung:**
```bash
# 1. Integration-Logs prüfen
# Einstellungen → System → Logs → Filter: pawcontrol

# 2. GPS-Konfiguration prüfen
# Entwicklertools → Dienste → pawcontrol.gps_generate_diagnostics

# 3. Webhook testen
curl -X POST "https://ihr-ha-server.com/api/webhook/paw_control_gps" \
  -H "Content-Type: application/json" \
  -d '{"dog_id": "buddy", "latitude": 52.52, "longitude": 13.40}'
```

#### Problem: Garden Tracking funktioniert nicht

**Lösung:**
```bash
# 1. Garden Manager Status prüfen
# Entwicklertools → Dienste
service: pawcontrol.start_garden_session
data:
  dog_id: "buddy"
  detection_method: "manual"

# 2. Türsensor testen
# Entwicklertools → Zustände → binary_sensor.garden_door

# 3. Garden Services testen
service: pawcontrol.add_garden_activity
data:
  dog_id: "buddy"
  activity_type: "play"
  location: "Test-Bereich"
```

#### Problem: Benachrichtigungen kommen nicht an

**Lösung:**
```yaml
# 1. Mobile App Konfiguration prüfen
# 2. Notification Service testen
service: notify.mobile_app_phone
data:
  title: "Test"
  message: "Paw Control Test-Nachricht"

# 3. Quiet Hours prüfen
# Einstellungen → Paw Control → Notifications → Quiet Hours

# 4. Garden Notification testen
service: notify.mobile_app_phone
data:
  title: "Garden Test"
  message: "Garden Tracking Test"
  data:
    actions:
      - action: "TEST_ACTION"
        title: "Test Button"
```

#### Problem: Entitäten werden nicht erstellt

**Lösung:**
```bash
# 1. Integration neu laden
# Entwicklertools → YAML → Alle neu laden

# 2. Config Entry prüfen
# Einstellungen → Geräte & Dienste → Paw Control → Konfigurieren

# 3. Garden Module aktiviert prüfen
# Einstellungen → Paw Control → Module → Garden: enabled

# 4. Logs prüfen
# grep -i "pawcontrol" /config/home-assistant.log
```

### Debug-Modi aktivieren

```yaml
# configuration.yaml - Debug-Logging aktivieren
logger:
  default: info
  logs:
    custom_components.pawcontrol: debug
    custom_components.pawcontrol.garden_manager: debug
    pawcontrol: debug

# Erweiterte Diagnostics
# Entwicklertools → Dienste
service: pawcontrol.gps_generate_diagnostics
data:
  dog_id: "buddy"

# Garden-spezifische Diagnostics
service: pawcontrol.garden_generate_diagnostics
data:
  dog_id: "buddy"
```

### Performance-Probleme beheben

```yaml
# Performance-Monitoring aktivieren
# Entwicklertools → Dienste
service: pawcontrol.performance_monitor_start

# Speicher-Verwendung optimieren
gps_settings:
  route_history_days: 30      # Reduzieren für weniger Speicher
  gps_update_interval: 60     # Längere Intervalle
  route_recording: false      # Deaktivieren wenn nicht benötigt

garden_settings:
  session_timeout: 900        # 15 Min statt 30 Min
  auto_poop_detection: false  # Deaktivieren wenn nicht benötigt
```

## ⚡ Performance-Optimierung

### 1. GPS-Performance optimieren

```yaml
# Optimierte GPS-Einstellungen für verschiedene Szenarien

# Hohe Genauigkeit (mehr Batterie/Daten):
high_accuracy_gps:
  gps_accuracy_filter: 10
  gps_distance_filter: 5
  gps_update_interval: 15
  route_recording: true

# Ausgewogene Einstellungen (empfohlen):
balanced_gps:
  gps_accuracy_filter: 50
  gps_distance_filter: 10
  gps_update_interval: 30
  route_recording: true

# Batterie-schonend:
battery_saving_gps:
  gps_accuracy_filter: 100
  gps_distance_filter: 20
  gps_update_interval: 60
  route_recording: false
```

### 2. Garden Tracking Performance optimieren

```yaml
# Optimierte Garden-Einstellungen

# Hohe Aktivitäts-Aufzeichnung:
high_activity_garden:
  session_timeout: 3600       # 60 Min Sessions
  auto_poop_detection: true
  confirmation_required: true
  weather_integration: true
  activity_history_days: 365

# Ausgewogene Einstellungen (empfohlen):
balanced_garden:
  session_timeout: 1800       # 30 Min Sessions
  auto_poop_detection: true
  confirmation_required: true
  weather_integration: true
  activity_history_days: 90

# Ressourcen-schonend:
minimal_garden:
  session_timeout: 900        # 15 Min Sessions
  auto_poop_detection: false
  confirmation_required: false
  weather_integration: false
  activity_history_days: 30
```

### 3. Datenbank-Optimierung

```yaml
# recorder.yaml - Datenbank-Aufbewahrung optimieren
recorder:
  purge_keep_days: 30
  include:
    domains:
      - sensor
      - binary_sensor
      - device_tracker
    entity_globs:
      - sensor.buddy_*
      - binary_sensor.buddy_*
      - device_tracker.buddy_*
  exclude:
    entity_globs:
      - sensor.*_debug
      - sensor.*_diagnostic
      - sensor.*_garden_raw*  # Raw Garden-Daten ausschließen
```

### 4. System-Monitoring

```yaml
# System-Monitoring Dashboard
system_monitor:
  resources:
    - type: memory_use_percent
    - type: processor_use
    - type: disk_use_percent
      arg: /config

# Performance-Alerts
automation:
  - alias: "Performance Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.memory_use_percent
        above: 85
    action:
      - service: notify.mobile_app_phone
        data:
          title: "⚠️ System Performance"
          message: "Hohe Speichernutzung erkannt: {{ states('sensor.memory_use_percent') }}%"

  - alias: "Garden Performance Monitor"
    trigger:
      - platform: state
        entity_id: sensor.buddy_garden_sessions_today
    condition:
      - condition: template
        value_template: "{{ states('sensor.buddy_garden_sessions_today') | int > 10 }}"
    action:
      - service: notify.mobile_app_phone
        data:
          title: "📊 Garden Performance"
          message: "Hohe Garden-Aktivität heute: {{ states('sensor.buddy_garden_sessions_today') }} Sessions"
```

## 📝 Wartung und Updates

### Regelmäßige Wartungsaufgaben

```bash
# Wöchentlich: Logs bereinigen
find /config -name "*.log" -mtime +7 -delete

# Monatlich: GPS-Daten bereinigen
# Entwicklertools → Dienste
service: pawcontrol.route_history_purge
data:
  older_than_days: 90

# Monatlich: Garden-Daten bereinigen
service: pawcontrol.garden_history_purge
data:
  older_than_days: 90

# Bei Updates: Backup erstellen
service: pawcontrol.backup_configuration
```

### Update-Prozess

1. **Backup erstellen**: Immer vor Updates
2. **HACS Updates prüfen**: Regelmäßig auf Updates prüfen
3. **Changelogs lesen**: Wichtige Änderungen beachten
4. **Konfiguration testen**: Nach Updates testen
5. **Performance prüfen**: Monitoring nach Updates
6. **Garden Features testen**: Garden Tracking nach Updates validieren

### Garden Tracking spezifische Wartung

```yaml
# Garden Tracking Wartungsautomation
automation:
  - alias: "Garden Data Maintenance"
    trigger:
      - platform: time
        at: "02:00:00"  # Täglich um 2 Uhr
    condition:
      - condition: template
        value_template: "{{ now().day == 1 }}"  # Ersten des Monats
    action:
      # Garden-Statistiken neu berechnen
      - service: pawcontrol.recalculate_garden_stats
        data:
          dog_id: "buddy"
      # Alte Garden-Sessions archivieren
      - service: pawcontrol.archive_old_garden_sessions
        data:
          older_than_days: 90
```

---

## 🧹 Deinstallation & Aufräumen

Sollten Sie Paw Control entfernen wollen – beispielsweise bei einem Gerätewechsel oder nach Tests – gehen Sie in dieser Reihenfolge vor, um Rückstände zu vermeiden:

1. **Integration aus Home Assistant entfernen**
   - Öffnen Sie *Einstellungen → Geräte & Dienste*.
   - Wählen Sie **Paw Control** und klicken Sie auf **Konfiguration entfernen**.
   - Bestätigen Sie den Dialog. Home Assistant entfernt daraufhin alle Plattformen und beendet Hintergrundaufgaben.
2. **Automationen, Szenen und Skripte prüfen**
   - Löschen oder deaktivieren Sie Automationen/Skripte, die auf `pawcontrol.*`-Dienste zugreifen.
   - Entfernen Sie Lovelace-Karten oder Dashboards, die ausschließlich Paw-Control-Entitäten anzeigen.
3. **Erzeugte Helfer bereinigen**
   - Navigieren Sie zu *Einstellungen → Geräte & Dienste → Helfer*.
   - Filtern Sie nach "Paw Control" oder nach den automatisch erzeugten Helfer-Namen (`input_datetime.pawcontrol_*`, `input_boolean.pawcontrol_*`).
   - Löschen Sie nicht mehr benötigte Helfer, sofern Sie diese nicht weiterverwenden möchten.
4. **Optionale Dateien & Backups aufräumen**
   - Entfernen Sie exportierte Dashboards oder Skripte im `config/www`-Verzeichnis, falls vorhanden.
   - Löschen Sie gesicherte Diagnosepakete (`/config/.storage/pawcontrol_*`) nach der Archivierung.
5. **Home Assistant neu starten (empfohlen)**
   - Ein Neustart stellt sicher, dass zwischengespeicherte Daten, Service-Registrierungen und Scheduler sauber entfernt werden.

> 💡 **Tipp:** Wenn Sie Paw Control später erneut installieren, beginnen Sie mit einer frischen Konfiguration. Importieren Sie keine veralteten YAML-Sicherungen ohne vorherige Prüfung.

---

## 📞 Support und Community

- **GitHub Issues**: [Probleme melden](https://github.com/BigDaddy1990/pawcontrol/issues)
- **Home Assistant Community**: [Forum-Thread](https://community.home-assistant.io/)
- **Discord**: Paw Control Channel
- **Dokumentation**: [Wiki](https://github.com/BigDaddy1990/pawcontrol/wiki)

### Garden Tracking spezifischer Support

- **Garden Tracking Issues**: [Label: garden-tracking](https://github.com/BigDaddy1990/pawcontrol/issues?q=label%3Agarden-tracking)
- **Sensor Setup Hilfe**: [Sensor Configuration Guide](https://github.com/BigDaddy1990/pawcontrol/wiki/Sensor-Setup)
- **Automation Templates**: [Garden Automations Sammlung](https://github.com/BigDaddy1990/pawcontrol/wiki/Garden-Automations)

---

**🎉 Herzlichen Glückwunsch!** Sie haben erfolgreich Paw Control mit allen erweiterten Features inklusive Garden Tracking eingerichtet. Ihr intelligentes Hundeverwaltungssystem ist jetzt bereit für den vollständigen Einsatz!

## 🌱 Garden Tracking Features Überblick

Mit dem Garden Tracking System haben Sie jetzt:

✅ **Automatische Garden-Erkennung** über Türsensoren
✅ **Intelligente Poop-Rückfragen** nach 3 Minuten
✅ **Aktivitäts-Protokollierung** (Spielen, Schnüffeln, Graben, Ruhen)
✅ **Wetter-Integration** für optimale Garten-Sessions
✅ **Vollautomatisierte Benachrichtigungen** mit Actionable Buttons
✅ **Umfassende Statistiken** und Verlaufs-Tracking
✅ **Session-Management** mit Start/End-Automatik

**🚀 Ihr Smart Home ist jetzt auch Smart Garden ready!**
