# 🐕 Paw Control - Smart Dog Management for Home Assistant

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Quality Scale](https://img.shields.io/badge/Quality%20Scale-Custom-#99670A)](https://developers.home-assistant.io/docs/core/integration-quality-scale/#-custom)
[![GitHub release](https://img.shields.io/github/release/BigDaddy1990/pawcontrol.svg)](https://github.com/BigDaddy1990/pawcontrol/releases)

Eine umfassende Home Assistant Integration für intelligentes Hundemanagement mit GPS-Tracking, Gesundheitsüberwachung, Geofencing und automatisierten Erinnerungen.

## ✨ Features

### 🚶‍♂️ Gassi-Tracking
- **GPS-basierte Routenverfolgung** mit Distanz und Dauer
- **Automatische Gassi-Erkennung** über Türsensoren
- **Tägliche Statistiken** und Verlaufsdaten
- **Kalorienbedarf-Berechnung** basierend auf Aktivität

### 📍 Geofencing & Standort
- **Sichere Zonen definieren** mit konfigurierbarem Radius
- **Ein-/Ausgangsmeldungen** bei Geofence-Verlassen
- **Anwesenheitserkennung** (Zuhause/Unterwegs)
- **DHCP/USB/Zeroconf Discovery** für automatische Erkennung

### 🍽️ Fütterungsmanagement
- **Mahlzeiten-Tracking** (Frühstück, Mittag, Abend, Snacks)
- **Portion- und Nahrungstyp-Erfassung**
- **Automatische Hunger-Erkennung** basierend auf Fütterungszeiten
- **Tägliche Ernährungsstatistiken**

### 💊 Gesundheit & Medikamente
- **Gewichtsverfolgung** mit Trend-Analyse
- **Medikamentenerinnerungen** mit konfigurierbaren Intervallen
- **Gesundheitsnotizen** und Verlaufsdokumentation
- **Impfstatus-Tracking** mit Terminerinnerungen

### 🛁 Pflege & Training
- **Pflegetermine verwalten** (Baden, Bürsten, Krallen, etc.)
- **Training-Sessions dokumentieren** mit Themen und Notizen
- **Automatische Erinnerungen** basierend auf Intervallen
- **Aktivitätslevel-Berechnung**

### 🔔 Intelligente Benachrichtigungen
- **Ruhezeiten-Respektierung** (konfigurierbare Zeiten)
- **Prioritätsbasierte Meldungen** (Info, Warnung, Kritisch)
- **Schlummer-Funktionen** mit konfigurierbarer Dauer
- **Fallback-Benachrichtigungen** bei Zielverfügbarkeit

## 🚀 Installation

### Voraussetzungen
- Home Assistant 2024.1.0 oder neuer
- Python 3.11+
- Konfiguration über UI (Config Flow)

### Automatische Installation (HACS)
1. Öffnen Sie HACS in Home Assistant
2. Gehen Sie zu "Integrations"
3. Klicken Sie auf "⋮" → "Custom Repositories"
4. Fügen Sie `https://github.com/BigDaddy1990/pawcontrol` hinzu
5. Kategorien: "Integration"
6. Installieren Sie "Paw Control"

### Manuelle Installation
1. Laden Sie die neueste Version herunter
2. Extrahieren Sie `custom_components/pawcontrol/` nach `<config_dir>/custom_components/`
3. Starten Sie Home Assistant neu
4. Gehen Sie zu "Einstellungen" → "Geräte & Dienste" → "Integration hinzufügen"
5. Suchen Sie nach "Paw Control"

## ⚙️ Konfiguration

### Ersteinrichtung
1. **Anzahl Hunde**: Geben Sie an, wie viele Hunde Sie haben (1-10)
2. **Hunde-Details**: Name, Rasse, Alter, Gewicht und Größe für jeden Hund
3. **Module**: Wählen Sie gewünschte Funktionen (GPS, Gesundheit, etc.)
4. **Datenquellen**: Optional - Türsensoren, Kalender, Wetter
5. **Benachrichtigungen**: Ruhezeiten und Erinnerungsintervalle
6. **System**: Zurücksetzungszeit und Export-Einstellungen

### Unterstützte Hardware
- **GPS-Tracker**: Via Person/Device-Tracker Entitäten
- **Türsensoren**: Beliebige binary_sensor für Gassi-Erkennung
- **USB-Geräte**: Automatische Erkennung von Paw-Trackern
- **Netzwerk**: DHCP-Discovery für Tracker-Hardware

### Geofencing einrichten
```yaml
# Automatische Konfiguration über UI
# Oder manuell in configuration.yaml:
geofence:
  latitude: 52.5200  # Ihr Heimstandort
  longitude: 13.4050
  radius_m: 100      # Radius in Metern
  alerts_enabled: true
```

## 📱 Verwendung

### Services
Die Integration stellt umfangreiche Services zur Verfügung:

```yaml
# Gassi starten
service: pawcontrol.start_walk
data:
  dog_id: "buddy"

# Fütterung protokollieren
service: pawcontrol.feed_dog
data:
  dog_id: "buddy"
  meal_type: "breakfast"
  portion_g: 200
  food_type: "dry"

# GPS-Position manuell setzen
service: pawcontrol.gps_post_location
data:
  dog_id: "buddy"
  latitude: 52.5200
  longitude: 13.4050
  accuracy: 5
```

### Automatisierungsbeispiele

**Gassi-Erinnerung basierend auf Zeit:**
```yaml
automation:
  - alias: "Gassi-Erinnerung Abends"
    trigger:
      - platform: time
        at: "19:00:00"
    condition:
      - condition: state
        entity_id: binary_sensor.buddy_needs_walk
        state: "on"
    action:
      - service: notify.mobile_app
        data:
          message: "Buddy braucht einen Abendspaziergang!"
```

**Automatische Geofence-Benachrichtigung:**
```yaml
automation:
  - alias: "Hund hat sicheren Bereich verlassen"
    trigger:
      - platform: state
        entity_id: binary_sensor.buddy_is_home
        from: "on"
        to: "off"
    action:
      - service: notify.family
        data:
          title: "🐕 Geofence Alert"
          message: "Buddy hat den sicheren Bereich verlassen!"
```

## 📊 Entitäten

Die Integration erstellt automatisch folgende Entitäten pro Hund:

### Sensoren
- `sensor.{dog_name}_walk_distance_today` - Tageskilometer
- `sensor.{dog_name}_last_feeding` - Letzte Fütterung
- `sensor.{dog_name}_weight` - Aktuelles Gewicht
- `sensor.{dog_name}_activity_level` - Aktivitätslevel
- `sensor.{dog_name}_calories_burned_today` - Verbrannte Kalorien

### Binary Sensoren
- `binary_sensor.{dog_name}_needs_walk` - Gassi erforderlich
- `binary_sensor.{dog_name}_is_hungry` - Fütterung erforderlich
- `binary_sensor.{dog_name}_is_home` - Zuhause/Unterwegs
- `binary_sensor.{dog_name}_walk_in_progress` - Gassi läuft

### Device Tracker
- `device_tracker.{dog_name}` - GPS-Position (falls konfiguriert)

## 🔧 Fehlerbehebung

### Häufige Probleme

**GPS-Tracking funktioniert nicht:**
- Prüfen Sie die Person/Device-Tracker Konfiguration
- Stellen Sie sicher, dass GPS-Module aktiviert sind
- Überprüfen Sie die Geofence-Koordinaten

**Benachrichtigungen kommen nicht an:**
- Überprüfen Sie den Fallback-Service in den Einstellungen
- Testen Sie mit `pawcontrol.notify_test`
- Prüfen Sie die Ruhezeiten-Konfiguration

**Entitäten erscheinen nicht:**
- Führen Sie `pawcontrol.sync_setup` aus
- Prüfen Sie die Logs auf Fehler
- Starten Sie Home Assistant neu

### Logs und Diagnose
```yaml
# Erweiterte Logs aktivieren
logger:
  default: warning
  logs:
    custom_components.pawcontrol: debug
```

## 🤝 Mitwirken

### Entwicklung
1. Forken Sie das Repository
2. Erstellen Sie einen Feature-Branch
3. Implementieren Sie Tests für neue Features
4. Führen Sie die Tests aus: `pytest`
5. Erstellen Sie einen Pull Request

### Quality Scale Status
**Aktuell: Platinum (Technisch Erfüllt)**
- ✅ Alle Bronze-Anforderungen erfüllt
- ✅ Alle Gold-Anforderungen erfüllt
- ✅ Alle Platinum-Anforderungen erfüllt
- ⚠️ **Einziger Blocker:** Zusätzliche Code-Owner für Silver benötigt

**Erreichte Meilensteine:**
- 🎯 Vollständige UI-Konfiguration mit Multi-Step Flow
- 🏗️ Moderne Architektur (async, runtime_data, strict typing)
- 🧪 Umfassende Test-Abdeckung (30+ Testdateien)
- 🔍 Multi-Protokoll Discovery (USB, DHCP, Zeroconf)
- 🌍 Vollständige deutsche Übersetzungen
- 📚 Comprehensive Documentation mit Beispielen
- 🔧 Diagnostics und Repair Issues
- ⚡ Vollständig asynchrone Implementierung

## 📄 Lizenz

Dieses Projekt steht unter der MIT-Lizenz. Siehe [LICENSE](LICENSE) für Details.

## 🙏 Danksagungen

- Home Assistant Community für das Feedback
- Beta-Tester für die Qualitätssicherung
- Alle Mitwirkenden an diesem Projekt

---

**Hinweis:** Diese Integration befindet sich in aktiver Entwicklung. Features können sich ändern. Für Produktionsumgebungen empfehlen wir, stabile Releases zu verwenden.
