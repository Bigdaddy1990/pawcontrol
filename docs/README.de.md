**🌍 Sprache / Language:** [🇩🇪 Deutsch](README.de.md) · [🇬🇧 English](../README.md) · [🇫🇷 Français](README.fr.md) · [🇪🇸 Español](README.es.md)

---

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.9.0%2B-blue.svg)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-Ready-41BDF5.svg)](https://hacs.xyz/)
[![Quality Scale](https://img.shields.io/badge/Qualit%C3%A4tsskala-Platinum%20ausgerichtet-e5e4e2.svg)](https://developers.home-assistant.io/docs/core/integration-quality-scale/)
[![Lizenz](https://img.shields.io/badge/Lizenz-MIT-green.svg)](../LICENSE)
[![Tests](https://github.com/BigDaddy1990/pawcontrol/actions/workflows/ci.yml/badge.svg)](https://github.com/BigDaddy1990/pawcontrol/actions/workflows/ci.yml)

# 🐕 PawControl – Home Assistant Companion für Mehrfach-Hundehaushalte

**PawControl** ist eine umfassende Home-Assistant-Integration für intelligentes Hundmanagement mit GPS-Tracking, automatisierten Fütterungserinnerungen, Gesundheitsüberwachung und smarten Automationsworkflows. Die Integration richtet sich an der **Platinum-Qualitätsskala** aus.

## ✨ Hauptfunktionen

🔧 **Einfache Einrichtung** – Vollständige UI-basierte Konfiguration mit modularer Funktionsauswahl
🍽️ **Intelligente Fütterung** – Automatisches Mahlzeiten-Tracking mit Portionskontrolle und gesundheitsbewussten Erinnerungen
🗺️ **Erweitertes GPS-Tracking** – Echtzeit-Standortüberwachung mit Geofencing und Routenaufzeichnung
🏥 **Gesundheitsüberwachung** – Gewichtsverfolgung, Medikamentenerinnerungen und Tierarztterminverwaltung
📱 **Mobile Integration** – Umsetzbare Benachrichtigungen mit iOS/Android-Unterstützung
🏠 **Smart-Home-Integration** – Türsensorintegration, wettergesteuerte Automationen
📊 **Auto-generierte Dashboards** – Responsive UI mit detaillierter Analytik
🔔 **Intelligente Benachrichtigungen** – Kontextbewusste Alerts mit Notfallprotokollen und Ruhezeiten

## 📋 Anforderungen

- Home Assistant 2025.9.0 oder neuer
- Python 3.14+
- HACS (empfohlen für Installation)

## 🚀 Installation

### Über HACS (empfohlen)
1. HACS in Home Assistant öffnen
2. **Integrationen** → Menü oben rechts → **Benutzerdefinierte Repositories**
3. URL `https://github.com/BigDaddy1990/pawcontrol` eingeben, Kategorie **Integration**
4. „PawControl" suchen und installieren
5. Home Assistant neu starten

### Manuelle Installation
1. Repository klonen: `git clone https://github.com/BigDaddy1990/pawcontrol`
2. Den Ordner `custom_components/pawcontrol` in das Verzeichnis
   `custom_components/` der HA-Installation kopieren
3. Home Assistant neu starten

## ⚙️ Einrichtung

### Config Flow
1. `Einstellungen → Geräte & Dienste → Integration hinzufügen`
2. „PawControl" suchen und auswählen
3. Integrationsnamen vergeben
4. **Hund(e) anlegen:** Name, ID, Größe, Gewicht und optionale Gesundheitsdaten
5. **Module wählen:** Feeding, GPS, Garten, Besuchsmodus, Wetter nach Bedarf
6. **Externe Entitäten zuordnen:** GPS-Quelle, Türsensoren, Wetter-Entity
7. **Optionen prüfen:** Dashboard, Benachrichtigungen, Performance-Modus
8. Abschließen – Entitäten werden automatisch erstellt

### Verfügbare Module

| Modul | Beschreibung |
|-------|--------------|
| 🍽️ Fütterung | Mahlzeiten-Tracking, Portionskontrolle, Erinnerungen |
| 🗺️ GPS | Echtzeit-Tracking, Geofencing, Routenaufzeichnung |
| 🏥 Gesundheit | Gewicht, Medikamente, Impfungen, Tierarzttermine |
| 🌦️ Wetter | Gesundheitsbewertung, Aktivitätsfenster, Warnungen |
| 🏡 Garten | Sitzungsverfolgung, Aktivitätsprotokoll |
| 👥 Besuchsmodus | Gasthund-Verwaltung, reduzierte Alarme |
| 📊 Dashboard | Automatisch generierte Lovelace-Ansichten |
| 🔔 Benachrichtigungen | Push-Nachrichten, Webhooks, Rückfragen |

## 🔧 Entwicklung

### Voraussetzungen
- Python 3.14+
- Git

### Umgebung einrichten
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements_test.txt
pre-commit install
pre-commit install --hook-type pre-push
```

### Tests ausführen
```bash
pytest
pytest --cov=custom_components/pawcontrol tests
```

### Code-Qualität
```bash
pre-commit run --all-files   # Ruff, MyPy, HA-Logger-Checker etc.
```

Hooks im Überblick:
- **ruff** – Linting & Formatierung
- **mypy** – Typprüfung
- **hass-logger-lint** – HA-Logger-Stilprüfung (Groß­buchstaben, kein abschließender Punkt)
- **hassfest-lite** – Manifest- und Übersetzungsvalidierung
- **homeassistant-push-guard** – Migrationsmuster-Prüfung (pre-push)

### Übersetzungen hinzufügen / synchronisieren
```bash
# Alle vorhandenen Sprachdateien mit strings.json synchronisieren
python -m scripts.sync_translations

# Bestimmte Sprachen synchronisieren
python -m scripts.sync_translations --languages de fr it

# Alle HA-Sprachen synchronisieren (60+ Sprachen)
python -m scripts.sync_translations --all-languages

# Fehlende Sprachen als Englisch-Stubs anlegen
python -m scripts.sync_translations --seed-missing

# Fehlende Sprachen anzeigen
python -m scripts.sync_translations --list-missing

# CI-Validierung (schlägt fehl bei Abweichungen)
python -m scripts.sync_translations --check
```

> **Hinweis zu Sprach-Stubs:** Neu geseedete Sprachen enthalten englische
> Strings als Platzhalter. Home Assistant fällt automatisch auf `en` zurück
> bis eine Übersetzung eingepflegt wird. Contributions willkommen!

## 🤝 Mitwirken

Beiträge sind herzlich willkommen! Bitte lies zuerst [CONTRIBUTING.md](../CONTRIBUTING.md).

- **Übersetzungen:** Alle 64 HA-Sprachen sind als Stubs vorhanden –
  `custom_components/pawcontrol/translations/<lang>.json` öffnen und
  Strings übersetzen, dann Pull Request einreichen.
- **Fehler melden:** [GitHub Issues](https://github.com/BigDaddy1990/pawcontrol/issues)
- **Feature-Anfragen:** [GitHub Discussions](https://github.com/BigDaddy1990/pawcontrol/discussions)

## 📄 Lizenz

MIT – siehe [LICENSE](../LICENSE)
