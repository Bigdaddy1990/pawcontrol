# 🐶🐕 Paw Control - Smart Dog Management for Home Assistant

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.9%2B-blue.svg)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Quality Scale](https://img.shields.io/badge/Quality%20Scale-Platinum%20Niveau-gold.svg)](https://developers.home-assistant.io/docs/core/integration-quality-scale/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![codecov](https://codecov.io/github/Bigdaddy1990/pawcontrol/graph/badge.svg?token=Y8IFVQ0KDD)](https://codecov.io/github/bigdaddy1990/pawcontrol)
[![CodeFactor](https://www.codefactor.io/repository/github/bigdaddy1990/pawcontrol/badge)](https://www.codefactor.io/repository/github/bigdaddy1990/pawcontrol)
[![GitHub Release](https://img.shields.io/github/v/release/BigDaddy1990/pawcontrol.svg)](https://github.com/bigdaddy1990/pawcontrol/releases)
[![Downloads](https://img.shields.io/github/downloads/BigDaddy1990/pawcontrol/total.svg)](https://github.com/bigdaddy1990/pawcontrol/releases)


**Paw Control** ist eine umfassende Home Assistant Integration für intelligentes Hundemanagement. Mit erweiterten GPS-Tracking, automatisierten Erinnerungen und umfassenden Gesundheitsüberwachung bringt sie das Smart Home auf die nächste Ebene der Haustierpflege.

## ✨ Hauptfeatures im Überblick

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
### 🗺️ **GPS-Tracking & Geofencing**
- **Live GPS-Tracking** mit Routenaufzeichnung
- **Intelligente Walk-Erkennung** über Türsensoren und Standort
- **Geofencing** mit anpassbaren Sicherheitszonen
- **Automatische Walk-Starts** bei Verlassen des Hauses
- **Detaillierte Statistiken** zu Distanz, Dauer und Geschwindigkeit
- **Routen-Export** als GPX/GeoJSON für externe Analyse

### 🍽️ **Fütterungsmanagement**
- **Automatische Fütterungserinnerungen** basierend auf Zeitplänen
- **Smart Feeder Integration** für automatisierte Fütterung
- **Mahlzeit-Tracking** mit verschiedenen Futterarten
- **Portionsüberwachung** und Kalorienzählung
- **Fütterungshistorie** und Trends

### 🏥 **Gesundheitsüberwachung**
- **Gewichtstracking** mit Trendanalyse
- **Medikationserinnerungen** mit anpassbaren Zeitplänen
- **Tierarzttermin-Verwaltung** und Erinnerungen
- **Pflegeerinnerungen** (Baden, Bürsten, Krallenschneiden)
- **Aktivitätslevel-Monitoring** basierend auf GPS-Daten
- **Gesundheits-Alerts** bei Anomalien

### 📱 **Mobile Integration**
- **Actionable Notifications** für iOS und Android
- **Widget-Support** für Quick Actions
- **Location-basierte Automatisierungen**
- **Push-Benachrichtigungen** mit Smart Actions
- **Offline-Synchronisation** für GPS-Daten

### 🏠 **Smart Home Integration**
- **Türsensor-Integration** für automatische Walk-Erkennung
- **Wetter-basierte** Walk-Empfehlungen
- **Kalender-Integration** für Termine und Events
- **Alarm-System Integration** (Auto-Scharf bei Walk-Start)
- **Licht-Signale** für Warnungen und Status

### 📊 **Analytics & Reporting**
- **Detaillierte Dashboards** mit Echtzeit-Daten
- **Wochen-/Monatsberichte** mit Trends
- **Performance-Monitoring** der Integration
- **Export-Funktionen** für Datenanalyse
- **Health-Checks** und Diagnostics

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

### Fütterungsmengen
- **Tägliche Futtermenge** *(Optional)*
  - Bereich: 50-2000g
  - Standard: Auto-Berechnung basierend auf Gewicht (2.5% Körpergewicht)

- **Anzahl Mahlzeiten pro Tag** *(Optional)*
  - Bereich: 1-5
  - Standard: 2
  - Beeinflusst Portionsgrößen-Berechnung

- **Standard-Futtertyp** *(Optional)*
  - Optionen: ["Trockenfutter", "Nassfutter", "BARF", "Selbstgekocht", "Gemischt", "Spezialfutter"]
  - Standard: "Trockenfutter"

### Fütterungszeiten
- **Frühstück aktivieren**
  - **Frühstückszeit** *(Zeit, Standard: 09:00)*

- **Mittagessen aktivieren**
  - **Mittagszeit** *(Zeit, Standard: 13:00)*

- **Abendessen aktivieren**
  - **Abendzeit** *(Zeit, Standard: 17:00)*

- **Snacks aktivieren**
  - **Snack-Zeiten** *(Mehrfach-Auswahl)*

### Fütterungs-Erinnerungen
- **Automatische Fütterungs-Erinnerungen** *(Boolean, Standard: true)*
- **Erinnerungszeit vor Mahlzeit** *(Minuten, Standard: 30)*
- **Snooze-Zeit bei Erinnerungen** *(Minuten, Standard: 10)*

---

## 🏥 MODUL 3: Gesundheitsüberwachung (OPTIONAL)

### Gesundheits-Tracking
- **Erweiterte Gesundheitsüberwachung aktivieren**
- **Gewichtsverlauf speichern**
- **Temperatur-Tracking aktivieren**
- **Activity-Logger aktivieren**

### Gesundheits-Parameter


### Notfall-Erkennung
- **Automatische Notfall-Erkennung**

### Medikations-Management
- **Medikations-Erinnerungen aktivieren**
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

- **Regelmäßige Checkup-Erinnerungen**
  - **Checkup-Intervall** *(Monate, Standard: 12)*
  - **Nächster Termin** *(Datum, Optional)*

---

## 🔔 MODUL 4: Benachrichtigungssystem (OPTIONAL)

### Benachrichtigungs-Grundeinstellungen
- **Benachrichtigungen aktivieren**
- **Benachrichtigungstyp** *(Auswahl)*
  - "Persistent Notifications" (Standard)
  - "Mobile App Notifications"
  - "Both"

### Mobile App Konfiguration
- **Mobile App Integration** *(Multi-Select)*
  - **Person-Entity für Benachrichtigungen** *(Entity-Auswahl)*
  - **Mobile App Service Name** *(Auto-Detection oder Manual)*
  - **Fallback bei Abwesenheit**

### Actionable Notifications
- **Actionable Notifications aktivieren**
- **Action-Button-Konfiguration** *(Advanced)*
  - Fütterungs-Actions: "Gefüttert ✅", "10 Min später ⏰"
  - Walk-Actions: "Gassi starten 🚶", "Später 🕐"

### Benachrichtigungs-Kategorien
**Fütterungs-Benachrichtigungen**
- **Aktiviert**
- **Vorlaufzeit** *(Minuten, Standard: 30)*
- **Wiederholungen bei ignoriert** *(Number, 0-5, Standard: 2)*
- **Wiederholungs-Intervall** *(Minuten, Standard: 15)*

**Spaziergang-Benachrichtigungen**
- **Aktiviert**
- **Erinnerungsintervall** *(Stunden, Standard: 8)*
- **Wetterbasierte Anpassungen**

**Gesundheits-Benachrichtigungen**
- **Aktiviert**
- **Notfall-Benachrichtigungen**
- **Medikations-Erinnerungen**

**GPS-Benachrichtigungen**
- **Geofence-Alerts**
- **Signal-Verlust-Alerts**
- **Signal-Verlust-Schwelle** *(Minuten, Standard: 10)*

### Zeitbasierte Benachrichtigungs-Steuerung
- **Nachtmodus aktivieren**
- **Ruhezeiten** *(Zeitbereich)*
  - **Start** *(Zeit, Standard: 22:00)*
  - **Ende** *(Zeit, Standard: 07:00)*
- **Nur Notfälle in Ruhezeiten**

---

## 🤖 MODUL 5: Automatisierungssystem (OPTIONAL)

### Basis-Automatisierung
- **Automatisierungs-Manager aktivieren**

### Fütterungs-Automatisierung
- **Fütterungs-Erinnerungen aktivieren**

### Aktivitäts-Automatisierung
- **Walk-Meilenstein-Feiern**
- **Meilenstein-Benachrichtigungen**
- **Meilenstein-Schwellen** *(Multi-Number)*
  - Standard: [5, 10, 25, 50, 100]
- **Aktivitäts-Level-Monitoring**
- **Inaktivitäts-Alerts**
- **Inaktivitäts-Schwelle** *(Stunden, Standard: 24)*

### Gesundheits-Automatisierung
- **Automatische Gesundheits-Alerts**
- **Stimmungsänderungs-Tracking**
- **Gewichtsänderungs-Alerts**
- **Gewichtsänderungs-Schwelle** *(%, Standard: 5)*

### Besucher-Modus-Automatisierung
- **Automatischer Besuchermodus**
- **Besuchererkennung-Methode** *(Optionen)*
  - "Manual Toggle"
  - "Person Detection"
  - "Door Sensor"
  - "Calendar Integration"

### Wartungs-Automatisierung
- **Tägliche Berichte generieren**
- **Berichts-Zeit**
- **Wöchentliche Zusammenfassungen**
- **System-Gesundheitschecks**
- **Check-Intervall** *(Minuten, Standard: 30)*

### Notfall-Automatisierung
- **Automatisches Notfall-Protokoll**
- **Notfall-Kontakt-Integration**
- **Eskalations-Stufen** *(Advanced)*

---

## 📊 MODUL 6: Dashboard und Visualisierung (OPTIONAL)

### Dashboard-Erstellung
- **Automatisches Dashboard erstellen**
- **Dashboard-Name**
- **Dashboard-Pfad**

### Dashboard-Module
**Übersichts-Karten**
- **Status-Übersichtskarte**
- **Tages-Zusammenfassung**
- **Quick-Action-Buttons**

**GPS-Module** *(Wenn GPS aktiviert)*
- **Live-GPS-Karte**
- **Route-Verlauf**
- **Geofence-Visualisierung**

**Gesundheits-Module**
- **Gesundheits-Status-Karte**
- **Gewichtsverlaufs-Graph**
- **Medikations-Übersicht**

**Aktivitäts-Module**
- **Walk-Statistiken**
- **Fütterungs-Status**
- **Aktivitäts-Verlauf**

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
- **GPS-Tracking aktivieren**
- **GPS-Update-Intervall** *(Sekunden)*
  - Optionen: [60, 120, 300, 600]
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
- **Geofencing aktivieren**
- **Geofence-Konfigurationen** *(Multi-Entry)*
  - **Name** *(Text)*
  - **Center-Koordinaten** *(Lat, Lon)*
  - **Radius** *(10-10000m)*
  - **Typ** *(Optionen: "Safe Zone", "Restricted Area", "Point of Interest")*
  - **Benachrichtigung bei Eintritt**
  - **Benachrichtigung bei Verlassen**

### Automatische Spaziergang-Erkennung
- **Auto-Walk-Detection aktivieren**
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
- **Detaillierte Route aufzeichnen**
- **Route-Punkte-Limit** *(Number)*
  - Bereich: 10-1000
  - Standard: 100

- **GPS-Punkt-Speicher-Intervall** *(Sekunden)*
  - Bereich: 30-300
  - Standard: 60

### Kalorien-Berechnung
- **Kalorien-Berechnung aktivieren**
- **Aktivitäts-Intensitäts-Multiplikatoren** *(Advanced)*
  - Langsam: 0.7 (Standard)
  - Normal: 1.0 (Standard)
  - Schnell: 1.4 (Standard)

---

## ⚙️ MODUL 8: Erweiterte Service-Konfiguration (OPTIONAL)

### Script-Services-Aktivierung
- **Erweiterte Script-Services aktivieren**
- **Service-Statistik-Tracking**

### Fütterungs-Services
- **feed_dog Service**
- **Automatische Portionsgrößen-Berechnung**
- **Fütterungs-Logging-Level**

### Aktivitäts-Services
- **walk_dog Service**
- **play_with_dog Service**
- **start_training_session Service**
- **Wetterintegration für Spaziergänge**
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
- **HA-Restart-Persistence**
- **State-Backup-Intervall** *(Stunden, Standard: 24)*
- **Entity-Naming-Prefix** *(Text, Standard: Hundename)*

### Hardware-Integration
**Sensoren-Integration**
- **Gewichts-Sensor Integration**
- **Gewichts-Sensor Entity** *(Entity-Auswahl)*
- **Temperatur-Sensor Integration**
- **Temperatur-Sensor Entity** *(Entity-Auswahl)*

**Smart Home Integration**
- **Türsensoren für Outside-Detection**
- **Türsensor-Entities**
- **Kamera-Integration für Überwachung**
- **Kamera-Entities** *(Multi-Entity-Auswahl)*

**IoT-Device Integration**
- **MQTT-Broker für IoT-Geräte**
- **MQTT-Broker-Konfiguration**
- **Custom-Device-Endpoints**

### Externe API-Integration
- **Wetterservice-Integration**
- **Wetterservice-Typ** *(Optionen: "OpenWeatherMap", "Weather.com", "Home Assistant Weather")*


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
- **Automatische Backups aktivieren**
- **Backup-Intervall**
- **Backup-Speicherort**
- **Backup-Anzahl-Limit**

### Datenexport
- **Export-Funktionen aktivieren**
- **Export-Formate** *(Multi-Select)*
  - CSV
  - JSON
  - PDF-Reports
  - GPX (für GPS-Routen)

### Datenschutz und Sicherheit
- **Daten-Anonymisierung bei Export**
- **GPS-Daten-Verschlüsselung**
- **Backup-Verschlüsselung**

---

## ✅ ZUSAMMENFASSUNG DER SETUP-KATEGORIEN

### ERFORDERLICHE KONFIGURATION
1. **Hundename** (Pflichtfeld)

### MODULARE OPTIONAL-KONFIGURATION
1. **Hundedaten-Erweiterung**
2. **Fütterungssystem**
3. **GPS-Tracking-System**
4. **Gesundheitsüberwachung**
5. **Benachrichtigungssystem**
6. **Automatisierungssystem**
7. **Dashboard-System**
8. **Service-Konfiguration**
9. **Hardware-Integration**
10. **Datenverwaltung**

### GESAMT-PARAMETER-ANZAHL
- **Erforderlich**: 1 Parameter
- **Optional**: 200+ Parameter
- **Total**: 200+ konfigurierbare Einstellungen

Dieses Setup-System ermöglicht eine vollständige Anpassung von einer Basis-Hundeverfolgung bis hin zu einem professionellen Tierpflege-Management-System auf Enterprise-Niveau.

- Optionen: **Hunde verwalten** – schnelle Eingabe als `id:name` je Zeile.

## Schnellstart
- HACS installieren → Paw Control hinzufügen → Optionen öffnen → **Hunde verwalten** ausfüllen.

- Optionen: **Module aktivieren** – Multi-Select für GPS / Feeding / Health / Walk.

- **Geräte-Trigger**: Für jeden Hund in den Automationen verfügbar – Start/Ende Spaziergang, Sicherheitszone betreten/verlassen.

- Optionen: **Erinnerungen & Benachrichtigungen** – Notify-Ziel, Intervall, Snooze, optional Auto-Erinnerung.

- Optionen: **Medikamente – Zuordnung je Slot** – pro Hund Slot 1–3 den Mahlzeiten (Frühstück/Mittag/Abend) zuordnen.

---

### Contribution Guidelines

1. **Issues erstellen** für Bugs oder Feature Requests
2. **Fork & Branch** für Entwicklung
3. **Tests schreiben** für neue Features
4. **Code Quality** mit pre-commit hooks sicherstellen
5. **Pull Request** mit detaillierter Beschreibung

---

## 📖 Dokumentation

- **[Setup Guide](docs/SETUP.md)**: Detaillierte Installation
- **[API Reference](docs/API.md)**: Service und Entity Dokumentation
- **[Automation Examples](docs/AUTOMATIONS.md)**: Fertige Automatisierungen
- **[Troubleshooting](docs/TROUBLESHOOTING.md)**: Problembehebung
- **[Development](docs/DEVELOPMENT.md)**: Entwickler-Dokumentation

---

## 🐛 Troubleshooting

### Häufige Probleme

---

## 📞 Support

- **GitHub Issues**: [Bug Reports & Feature Requests](https://github.com/BigDaddy1990/pawcontrol/issues)
- **Home Assistant Community**: [Forum Discussion](https://community.home-assistant.io/t/paw-control/)
- **Discord**: [Smart Home Pets Channel](https://discord.gg/smart-home-pets)
- **Wiki**: [Comprehensive Documentation](https://github.com/BigDaddy1990/pawcontrol/wiki)

---

## 📝 Changelog

[Vollständiges Changelog →](CHANGELOG.md)

---

## 📄 Lizenz

Dieses Projekt steht unter der MIT Lizenz - siehe [LICENSE](LICENSE) für Details.

## 🏆 Auszeichnungen

- 🥇 **Home Assistant Quality Scale**: Platinum Tier
- 🌟 **HACS Featured Integration**: Top-Bewertung
- 👥 **Community Choice**: Beliebteste Pet-Integration 2025

---

## 🙏 Credits

- **Entwicklung**: [BigDaddy1990](https://github.com/BigDaddy1990)
- **Contributors**: [Alle Contributors](https://github.com/BigDaddy1990/pawcontrol/graphs/contributors)
- **Beta-Tester**: Paw Control Community
- **Icons**: [Material Design Icons](https://materialdesignicons.com/)
- **Inspiration**: Alle Hundebesitzer der Home Assistant Community

---

<div align="center">
![Paw Control](assets/logo.png)
**🐕 Made with ❤️ for our four-legged family members 🐾**

*Paw Control - Bringing Smart Home technology to pet care since 2024*

</div>

---

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=BigDaddy1990/pawcontrol&type=Date)](https://star-history.com/#BigDaddy1990/pawcontrol&Date)
