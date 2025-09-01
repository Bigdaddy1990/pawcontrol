# 🐕 Paw Control - GPS-basierte Hundeintegration für Home Assistant

<div align="center">

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/bigdaddy1990/pawcontrol.svg)](https://github.com/bigdaddy1990/pawcontrol/releases)
[![Downloads](https://img.shields.io/github/downloads/bigdaddy1990/pawcontrol/total.svg)](https://github.com/bigdaddy1990/pawcontrol/releases)

**🛰️ Die smarteste GPS-Tracking Integration für Hundebesitzer**

Automatische Spaziergang-Erkennung • Live-GPS-Tracking • Intelligente Automatisierungen

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/bigdaddy1990)

</div>

---

## 🎯 **Was ist Paw Control?**

**Paw Control** ist die erste **GPS-basierte Home Assistant Integration**, die speziell für Hundebesitzer entwickelt wurde. Mit **automatischer Spaziergang-Erkennung**, **Live-Route-Tracking** und vielem mehr haben Sie die komplette Kontrolle über das Wohlbefinden Ihres Hundes.

## 🎯 Hauptfeatures im Überblick

| Kategorie                    | Beschreibung                                                               |
| ---------------------------- | -------------------------------------------------------------------------- |
| 🧠 **Setup per UI**          | Einfache Konfiguration pro Hund – inkl. Name, Türsensor, Push-Gerät        |
| 🚪 **Türsensor-Erkennung**   | Automatische Erkennung, wenn Hund durch die Tür geht                       |
| 📲 **Push-Rückfrage**        | Nachricht an gewähltes Gerät: „Hat er gemacht?" – Antwort mit ✅ / ❌      |
| 🔄 **Quittierungs-Logik**    | Antwort auf einem Gerät löscht die Nachricht auf allen anderen             |
| 📊 **Dashboard-Integration** | Lovelace-fertiges YAML-Layout enthalten                                    |
| 🔃 **Tagesreset**            | Alle Zähler (Fütterung, Draußen) werden täglich um 23:59 Uhr zurückgesetzt |
| 🐾 **Mehrhundelogik**        | Unterstützung für mehrere Hunde mit eigenen Sensoren und Werten            |
| 🧪 **Besuchshund-Modus**     | Temporärer Hundebesuch? Kein Problem – einfach aktivieren                  |
| 📦 **HACS-kompatibel**       | Installation als Custom Repository in HACS möglich                         |

### 🔧 Funktionsübersicht

| Feature                   | Beschreibung                                            |
| ------------------------- | ------------------------------------------------------- |
| 🍽️ **Fütterung**          | Erinnerungen für Frühstück, Mittag, Abend, Leckerli     |
| 🚪 **Türsensor-Tracking** | „Draußen"-Protokoll mit Rückfragen                      |
| 📲 **Push-Logik**         | Nachricht an anwesende Person(en) oder manuelle Geräte  |
| 📅 **Tagesstatistik**     | Counter pro Aktion + automatischer Reset                |
| 🧍 **Besucherhunde**      | Optionaler Besuchsmodus & Statusanzeige                 |
| 🧠 **Adminpanel**         | Zentrale Übersicht, manuelle Steuerung, Push-Test       |
| 📊 **Dashboard**          | Mushroom-fähig, responsiv, Chip + Template-Karten       |
| 💬 **Rückfragen**         | „Hund schon gefüttert?" via Notification                |
| 🔁 **Flexibel**           | Beliebig viele Hunde, jede Funktion einzeln abschaltbar |

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
- \*_Lovelance Installationsanleitung_
- **Automatisches Dashboard**: Alle Entitäten werden automatisch angezeigt
- **Responsive Design**: Optimiert für Desktop und Mobile
- **Konfigurationspanel**: Zentrale Übersicht und Schnellsteuerung
- **Anpassbare Layouts**: Verschiedene Dashboard-Varianten
- **Status-Indikatoren**: Visuelle Darstellung des Hundestatus
- **Schnellaktionen**: Ein-Klick-Buttons für häufige Aktionen

### 🔧 Technische Features

- **Config Flow**: Benutzerfreundliche Einrichtung über UI
- **Entity Registry**: Saubere Entitäts-Verwaltung
- **Error Handling**: Robuste Fehlerbehandlung
- **Logging**: Umfassendes Logging für Debugging
- **Localization**: Mehrsprachige Unterstützung (DE/EN)
- **Device Integration**: Proper Device-Gruppierung
- **Service Schemas**: Validierte Service-Aufrufe

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

---

## 🚀 **HACS Installation**

### **Schritt 1: Repository hinzufügen**

1. **HACS öffnen** in Home Assistant
2. **Integrationen** → **⋮** → **Benutzerdefinierte Repositories**
3. **Repository hinzufügen**:
   ```
   URL: https://github.com/bigdaddy1990/pawcontrol
   Kategorie: Integration
   ```

### **Schritt 2: Paw Control installieren**

1. **"Paw Control"** in HACS suchen
2. **"Installieren"** klicken
3. **Home Assistant neu starten**

### **Schritt 3: Integration konfigurieren**

1. **Einstellungen** → **Geräte & Dienste** → **Integration hinzufügen**
2. **"Paw Control"** suchen und hinzufügen
3. **Setup-Assistent** folgen:
   ```yaml
   Hundename: Buddy
   GPS-Quelle: device_tracker.buddy_phone
   Auto-Tracking: Aktiviert
   Sicherheitszone: 100m
   ```

### **Schritt 4: GPS-Tracking aktivieren**

```yaml
# Automatisches Setup ausführen
service: pawcontrol.setup_automatic_gps
data:
  entity_id: sensor.buddy_status
  gps_source: "device_tracker.buddy_phone"
  auto_start_walk: true
  safe_zone_radius: 100
  track_route: true
```

**🎉 Fertig! GPS-Tracking läuft automatisch.**

---

## 📱 **Unterstützte GPS-Tracker**

### **🎯 Tractive GPS-Collar**

```yaml
# Native Home Assistant Integration
service: pawcontrol.setup_automatic_gps
data:
  gps_source: "device_tracker"
  gps_entity: device_tracker.buddy_tractive
```

### **📱 Smartphone (Empfohlen)**

```yaml
# Home Assistant Companion App
service: pawcontrol.setup_automatic_gps
data:
  gps_source: "device_tracker"
  gps_entity: device_tracker.owner_phone
```

### **🔧 DIY & Universal**

- **Webhooks**: Für jeden GPS-Tracker mit Internet
- **MQTT**: Für IoT-basierte GPS-Geräte
- **REST APIs**: Für kommerzielle GPS-Services
- **ESP32/Arduino**: Für selbstgebaute GPS-Tracker

---

## 🤖 **Beispiel-Automatisierungen**

### **🚶 Automatische Spaziergang-Benachrichtigungen**

```yaml
# Spaziergang gestartet
automation:
  - alias: "GPS: Spaziergang gestartet"
    trigger:
      - platform: state
        entity_id: binary_sensor.buddy_on_walk
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          title: "🚶 Spaziergang gestartet!"
          message: "Buddy ist spazieren gegangen - GPS-Tracking aktiv"
```

### **🚨 Sicherheits-Automatisierungen**

```yaml
# Hund verlässt Sicherheitszone
automation:
  - alias: "GPS: Sicherheitszone verlassen"
    trigger:
      - platform: state
        entity_id: binary_sensor.buddy_in_safe_zone
        to: "off"
        for: "00:02:00" # 2 Minuten außerhalb
    action:
      - service: notify.mobile_app
        data:
          title: "⚠️ Buddy außerhalb Sicherheitszone!"
          message: "GPS-Tracker zeigt Position außerhalb des sicheren Bereichs"
```

---

## 💝 **Unterstützung**

### **🦴 Spenden Sie Hundekekse! 🦴**

pawcontrol ist kostenlos und Open Source. Unterstützen Sie die Entwicklung:

<div align="center">

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/bigdaddy1990)

**🏠 Spenden Sie eine Hundehütte oder Hundekekse! 🍪**

</div>

### **🌟 Andere Unterstützung**

- ⭐ **GitHub-Stern geben** - Zeigen Sie anderen, dass pawcontrol großartig ist
- 📢 **Weiterempfehlen** - Erzählen Sie anderen Hundebesitzern davon
- 🐛 **Bugs melden** - Helfen Sie bei der Verbesserung
- 💡 **Features vorschlagen** - Ihre GPS-Ideen sind willkommen!

---

## 📞 **Support & Community**

### **🆘 Hilfe benötigt?**

- 🐛 **[Bug Reports](https://github.com/bigdaddy1990/pawcontrol/issues)** - Probleme melden
- 💬 **[GitHub Discussions](https://github.com/bigdaddy1990/pawcontrol/discussions)** - Community-Support
- 📖 **[Dokumentation](https://github.com/bigdaddy1990/pawcontrol/wiki)** - Ausführliche Anleitungen
- 📧 **support@pawcontrol.de** - Direkter Support

---

<div align="center">

## 🐶 **Ready to Track Your Dog's Adventures?**

**Paw Control** - _DOG-Tracking made simple for dog lovers!_

### **🚀 Jetzt installieren:**

1. **HACS** → **Custom Repository** → `github.com/bigdaddy1990/pawcontrol`
2. **"Paw Control"** installieren
3. **GPS-Tracker** verbinden
4. **Automatisches Tracking** genießen! 🎉

[![Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/bigdaddy1990)

_🦴 Spenden Sie Hundekekse für die Entwicklung! 🦴_

---

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/bigdaddy1990/pawcontrol.svg?style=for-the-badge)](https://github.com/bigdaddy1990/pawcontrol/releases)
[![License](https://img.shields.io/github/license/bigdaddy1990/pawcontrol.svg?style=for-the-badge)](LICENSE)

**⭐ Geben Sie uns einen Stern, wenn Sie Paw Control lieben! ⭐**

</div>
