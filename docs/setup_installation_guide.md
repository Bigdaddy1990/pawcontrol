# 🐕 Paw Control - Setup & Installation Guide für erweiterte Features

Dieser umfassende Guide führt Sie durch die Installation und Konfiguration der erweiterten Paw Control Features, einschließlich GPS-Tracking, Automatisierungen und Dashboard-Konfiguration.

## 📋 Inhaltsverzeichnis

1. [Voraussetzungen](#voraussetzungen)
2. [Installation](#installation)
3. [Grundkonfiguration](#grundkonfiguration)
4. [Erweiterte Features](#erweiterte-features)
5. [Dashboard-Setup](#dashboard-setup)
6. [Automatisierungen](#automatisierungen)
7. [Mobile App Integration](#mobile-app-integration)
8. [Troubleshooting](#troubleshooting)
9. [Performance-Optimierung](#performance-optimierung)

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
  - Türsensoren für automatische Walk-Erkennung
  - Waage für Gewichtsüberwachung
  - Kamera für Überwachung

### Unterstützte GPS-Tracker

| Tracker | Status | Features | Setup-Anleitung |
|---------|--------|----------|-----------------|
| Tractive GPS | ✅ Vollständig | Live-Tracking, Geofencing | [Setup →](#tractive-setup) |
| Fi Smart Dog Collar | ✅ Vollständig | GPS, Aktivität, Schlaf | [Setup →](#fi-setup) |
| Apple AirTag | ⚠️ Begrenzt | Standort-Updates | [Setup →](#airtag-setup) |
| Generic GPS Logger | ✅ Basis | GPS-Koordinaten | [Setup →](#generic-gps-setup) |
| Whistle GPS | 🔄 In Entwicklung | - | Bald verfügbar |

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
    notifications: true
    dashboard: true
    grooming: true
    medication: false  # Nur wenn benötigt
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
        entity: sensor.buddy_last_walk_hours
        icon: mdi:clock
      - type: action
        icon: mdi:play
        tap_action:
          action: call-service
          service: pawcontrol.gps_start_walk
          service_data:
            dog_id: "buddy"
```

## 🤖 Automatisierungen

### 1. Basis-Automatisierungen einrichten

Kopieren Sie die Automatisierungs-Templates in Ihre `automations.yaml`:

```yaml
# automations.yaml - Fügen Sie die Automatisierungen aus den Templates hinzu
# Wichtige Automatisierungen:
# - smart_walk_detection
# - feeding_schedule  
# - gps_tracking_automation
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
```

### 3. Widget-Konfiguration

```yaml
# iOS Widget Entities
# Konfigurieren Sie diese Entitäten für das Home Assistant Widget:
widget_entities:
  - sensor.buddy_name
  - binary_sensor.buddy_walk_in_progress
  - sensor.buddy_last_walk_hours
  - sensor.buddy_last_feeding_hours
  - button.buddy_start_walk
  - button.buddy_end_walk
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
```

#### Problem: Entitäten werden nicht erstellt

**Lösung:**
```bash
# 1. Integration neu laden
# Entwicklertools → YAML → Alle neu laden

# 2. Config Entry prüfen
# Einstellungen → Geräte & Dienste → Paw Control → Konfigurieren

# 3. Logs prüfen
# grep -i "pawcontrol" /config/home-assistant.log
```

### Debug-Modi aktivieren

```yaml
# configuration.yaml - Debug-Logging aktivieren
logger:
  default: info
  logs:
    custom_components.pawcontrol: debug
    pawcontrol: debug

# Erweiterte Diagnostics
# Entwicklertools → Dienste
service: pawcontrol.gps_generate_diagnostics
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

### 2. Datenbank-Optimierung

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
```

### 3. System-Monitoring

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

# Bei Updates: Backup erstellen
service: pawcontrol.backup_configuration
```

### Update-Prozess

1. **Backup erstellen**: Immer vor Updates
2. **HACS Updates prüfen**: Regelmäßig auf Updates prüfen
3. **Changelogs lesen**: Wichtige Änderungen beachten
4. **Konfiguration testen**: Nach Updates testen
5. **Performance prüfen**: Monitoring nach Updates

---

## 📞 Support und Community

- **GitHub Issues**: [Probleme melden](https://github.com/BigDaddy1990/pawcontrol/issues)
- **Home Assistant Community**: [Forum-Thread](https://community.home-assistant.io/)
- **Discord**: Paw Control Channel
- **Dokumentation**: [Wiki](https://github.com/BigDaddy1990/pawcontrol/wiki)

---

**🎉 Herzlichen Glückwunsch!** Sie haben erfolgreich Paw Control mit allen erweiterten Features eingerichtet. Ihr intelligentes Hundeverwaltungssystem ist jetzt bereit für den Einsatz!