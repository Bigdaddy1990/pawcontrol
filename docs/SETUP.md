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
- **Standard-Temperatur** *(°C)*
  - Bereich: 35.0-42.0°C
  - Standard: 38.5°C

### Notfall-Erkennung  
- **Automatische Notfall-Erkennung** *(Boolean, Standard: false)*
- **Temperatur-Alarm-Schwellen** *(Advanced)*
  - **Fieber-Schwelle** *(°C, Standard: 41.0)*
  - **Hypothermie-Schwelle** *(°C, Standard: 37.0)*
  
- **Herzfrequenz-Monitoring** *(Boolean, Standard: false)*
  - **Tachykardie-Schwelle** *(BPM, Standard: 180)*
  - **Bradykardie-Schwelle** *(BPM, Standard: 50)*

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