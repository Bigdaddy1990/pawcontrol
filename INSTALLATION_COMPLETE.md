# 🐕 Paw Control - Vollständige Installationsanleitung

## Version 1.1.0 - Mit allen Verbesserungen

### ✅ Voraussetzungen

- **Home Assistant:** 2024.1.0 oder neuer
- **Python:** 3.11 oder neuer
- **Speicherplatz:** ~10 MB
- **Optional:** HACS für einfache Installation

---

## 📦 Installationsmethoden

### Methode 1: HACS Installation (Empfohlen)

1. **HACS öffnen** in Home Assistant
2. **Drei Punkte** oben rechts → **Custom repositories**
3. **Repository URL:** `https://github.com/BigDaddy1990/pawcontrol`
4. **Category:** Integration
5. **Add** klicken
6. **Paw Control** in HACS suchen und installieren
7. **Home Assistant neu starten**

### Methode 2: Manuelle Installation

```bash
# 1. In Home Assistant config Ordner wechseln
cd /config

# 2. Custom Components Ordner erstellen (falls nicht vorhanden)
mkdir -p custom_components

# 3. Integration herunterladen
cd custom_components
git clone https://github.com/BigDaddy1990/pawcontrol.git pawcontrol

# 4. Oder ZIP Download
wget https://github.com/BigDaddy1990/pawcontrol/archive/main.zip
unzip main.zip
mv pawcontrol-main pawcontrol
rm main.zip
```

### Methode 3: Automatisches Deployment Script

```bash
# Download und Ausführung des Deploy Scripts
curl -sSL https://raw.githubusercontent.com/BigDaddy1990/pawcontrol/main/deploy.sh | bash
```

---

## ⚙️ Konfiguration

### Schritt 1: Integration hinzufügen

1. **Einstellungen** → **Geräte & Dienste**
2. **Integration hinzufügen** (+ Button)
3. **"Paw Control"** suchen
4. **Installieren** klicken

### Schritt 2: Hunde konfigurieren

Im Setup-Wizard:

```yaml
Anzahl der Hunde: 1-10
Pro Hund:
  - ID: eindeutige_id (z.B. "rex")
  - Name: Anzeigename
  - Rasse: Optional
  - Alter: in Jahren
  - Gewicht: in kg
  - Größe: small/medium/large/xlarge
```

### Schritt 3: Module aktivieren

Wählen Sie die gewünschten Module:
- ✅ **Walk Tracking** - Spaziergänge verfolgen
- ✅ **Feeding Management** - Fütterungen verwalten
- ✅ **Health Tracking** - Gesundheitsdaten
- ✅ **GPS Tracking** - Standortverfolgung
- ✅ **Notifications** - Benachrichtigungen
- ✅ **Dashboard** - Übersichts-Dashboard
- ✅ **Grooming** - Pflege-Tracking
- ✅ **Medication** - Medikamenten-Erinnerungen
- ✅ **Training** - Trainings-Sessions

### Schritt 4: Datenquellen (Optional)

```yaml
Türsensor: binary_sensor.haustuer
Personen: person.owner
Device Tracker: device_tracker.phone
Kalender: calendar.familie
Wetter: weather.home
```

### Schritt 5: Benachrichtigungen

```yaml
Benachrichtigungsdienst: notify.mobile_app
Ruhezeiten: 22:00 - 07:00
Erinnerungsintervall: 30 Minuten
Snooze-Dauer: 15 Minuten
```

---

## 🎯 Erste Schritte nach Installation

### 1. Dashboard einrichten

Fügen Sie diese Karte zu Ihrem Dashboard hinzu:

```yaml
type: vertical-stack
cards:
  - type: entities
    title: 🐕 Rex Status
    entities:
      - sensor.rex_last_walk
      - sensor.rex_last_feeding
      - sensor.rex_activity_level
      - sensor.rex_calories_burned_today
      - binary_sensor.rex_needs_walk
      - binary_sensor.rex_is_hungry
  
  - type: horizontal-stack
    cards:
      - type: button
        name: Spaziergang starten
        icon: mdi:dog-side
        tap_action:
          action: call-service
          service: pawcontrol.start_walk
          service_data:
            dog_id: rex
      
      - type: button
        name: Fütterung
        icon: mdi:food-drumstick
        tap_action:
          action: call-service
          service: pawcontrol.feed_dog
          service_data:
            dog_id: rex
            meal_type: dinner
            portion_g: 200
```

### 2. Erste Automation

```yaml
automation:
  - alias: "Paw Control - Spaziergang Erinnerung"
    trigger:
      - platform: time_pattern
        hours: "/4"  # Alle 4 Stunden
    condition:
      - condition: state
        entity_id: binary_sensor.rex_needs_walk
        state: "on"
    action:
      - service: notify.mobile_app
        data:
          title: "🐕 Zeit für einen Spaziergang!"
          message: "Rex wartet seit {{ states('sensor.rex_hours_since_walk') }} Stunden"
          data:
            actions:
              - action: "START_WALK"
                title: "Spaziergang starten"
```

### 3. Services testen

Developer Tools → Services:

```yaml
service: pawcontrol.walk_dog
data:
  dog_id: rex
  duration_min: 30
  distance_m: 1500
```

---

## 🔧 Fehlerbehebung

### Problem: Integration wird nicht gefunden

**Lösung:**
```bash
# Cache löschen
rm -rf /config/.storage/core.entity_registry
# Home Assistant neu starten
ha core restart
```

### Problem: Services funktionieren nicht

**Lösung:**
1. Logs prüfen: Settings → System → Logs
2. Debug aktivieren:
```yaml
logger:
  default: info
  logs:
    custom_components.pawcontrol: debug
```

### Problem: Entitäten fehlen

**Lösung:**
```yaml
service: pawcontrol.sync_setup
data: {}
```

---

## 📊 Verfügbare Entitäten

Pro Hund werden folgende Entitäten erstellt:

### Sensoren
- `sensor.[dog_id]_last_walk` - Letzter Spaziergang
- `sensor.[dog_id]_last_feeding` - Letzte Fütterung
- `sensor.[dog_id]_walk_duration` - Spaziergang Dauer
- `sensor.[dog_id]_walk_distance` - Spaziergang Distanz
- `sensor.[dog_id]_walks_today` - Spaziergänge heute
- `sensor.[dog_id]_activity_level` - Aktivitätslevel
- `sensor.[dog_id]_calories_burned_today` - Kalorien verbrannt
- `sensor.[dog_id]_weight` - Gewicht
- `sensor.[dog_id]_last_grooming` - Letzte Pflege

### Binary Sensoren
- `binary_sensor.[dog_id]_needs_walk` - Braucht Spaziergang
- `binary_sensor.[dog_id]_is_hungry` - Ist hungrig
- `binary_sensor.[dog_id]_needs_grooming` - Braucht Pflege
- `binary_sensor.[dog_id]_walk_in_progress` - Spaziergang läuft

### Buttons
- `button.[dog_id]_start_walk` - Spaziergang starten
- `button.[dog_id]_end_walk` - Spaziergang beenden
- `button.[dog_id]_feed` - Füttern
- `button.[dog_id]_quick_walk` - Schneller Spaziergang

---

## 🎨 Lovelace Dashboard Beispiel

Vollständiges Dashboard in `examples/dashboard.yaml`:

```yaml
title: Paw Control
views:
  - title: Übersicht
    cards:
      - type: picture-entity
        entity: sensor.rex_activity_level
        image: /local/images/rex.jpg
        show_state: true
        show_name: true
        
      - type: statistics-graph
        title: Aktivität diese Woche
        entities:
          - sensor.rex_walks_today
        stat_types:
          - mean
          - max
        period:
          rolling_window:
            duration:
              days: 7
```

---

## 🚀 Erweiterte Features

### GPS Tracking aktivieren

```yaml
service: pawcontrol.update_gps_location
data:
  dog_id: rex
  latitude: !secret home_latitude
  longitude: !secret home_longitude
```

### Medikamenten-Erinnerungen

```yaml
service: pawcontrol.log_medication
data:
  dog_id: rex
  medication_name: "Herzmedikament"
  dose: "1 Tablette"
```

### Berichte generieren

```yaml
service: pawcontrol.generate_report
data:
  scope: weekly
  target: notification
  format: text
```

---

## 📱 Mobile App Integration

### iOS Shortcuts
Download: `shortcuts/pawcontrol_ios.shortcut`

### Android Tasker
Import: `tasker/pawcontrol_profile.xml`

---

## 🔄 Updates

### Über HACS
1. HACS öffnen
2. Paw Control auswählen
3. Update Button klicken

### Manuell
```bash
cd /config/custom_components/pawcontrol
git pull origin main
# Home Assistant neu starten
```

---

## 📝 Changelog

### v1.1.0 (Aktuelle Version)
- ✅ Service Schema Validation
- ✅ Verbessertes Datetime-Handling
- ✅ Type Hints überall
- ✅ HomeKit Support
- ✅ Bessere Fehlerbehandlung

### v1.0.0
- Initial Release

---

## 🆘 Support

- **GitHub Issues:** https://github.com/BigDaddy1990/pawcontrol/issues
- **Discord:** https://discord.gg/pawcontrol
- **Forum:** https://community.home-assistant.io/t/pawcontrol

---

## 📜 Lizenz

MIT License - Siehe LICENSE Datei

---

*Installation getestet mit Home Assistant 2024.12.0*
*Letzte Aktualisierung: 2025-01-01*