# 🐾 Paw Control

[![hacs-badge](https://img.shields.io/badge/HACS-Custom-blue.svg?style=flat-square)](https://hacs.xyz/)
[![version](https://img.shields.io/github/v/tag/Bigdaddy1990/paw_control?label=version&style=flat-square)](https://github.com/Bigdaddy1990/paw_control/releases)
[![license](https://img.shields.io/github/license/Bigdaddy1990/paw_control?style=flat-square)](LICENSE)

**Paw Control** ist eine vollständig modulare Home Assistant-Integration zur Verwaltung von Hundeverhalten, Gesundheit, Spaziergängen und Benachrichtigungen.

---

## 🚀 Features

- 🛰️ GPS-Tracking & Bewegungslog
- 🐾 Gassi-Statistiken, Trigger, Türsensor-Erkennung
- 🧠 Gesundheitsdaten: Gewicht, Medikamente, Impfungen
- 🔔 Push & Actionable Notifications
- 📊 Mushroom-kompatibles Dashboard
- 🛠️ Automatische Einrichtung (Installer-basiert)
- 🧩 Modular: leicht erweiterbar, stabile Struktur

---

## 📸 Screenshots

> *(Screenshots folgen in Release v1.1)*

---

## 📦 Quickstart

### Installation über HACS (empfohlen)

```yaml
repository: https://github.com/Bigdaddy1990/paw_control
category: integration
```

1. Repository zu HACS hinzufügen
2. Paw Control über HACS installieren
3. Home Assistant neu starten
4. Setup-Assistenten folgen

### Manuelle Installation

```bash
# Entpacke den Inhalt nach:
<config>/custom_components/pawcontrol/
# Dann Home Assistant neu starten
```

---

## 📁 Verzeichnisstruktur

```text
custom_components/pawcontrol/
├── modules/          # Hauptfunktionseinheiten (gps, health, walk…)
├── entities/         # HA-Entities: sensor, binary_sensor etc.
├── helpers/          # Gemeinsame Hilfsfunktionen
├── ui/               # Dashboard, Übersetzungen, Bilder
├── system/           # Konstanten, Exceptions, Koordinator
├── base/             # Basisklassen für Module/Entities
├── services/         # Service Handler & YAMLs
└── .github/          # Actions, Templates, Funding
```

---

## 🧪 Entwicklung

- [CHANGELOG.md](CHANGELOG.md)
- [ROADMAP.md](ROADMAP.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [LICENSE](LICENSE)

---

## ☕ Unterstützung

Du kannst mich hier unterstützen:

- GitHub Sponsors
- [Ko-Fi](https://ko-fi.com/bigdaddy1990)
- [BuyMeACoffee](https://www.buymeacoffee.com/bigdaddy1990)

---

## 🐛 Fehler melden oder Feature vorschlagen

Nutze die [Issues](https://github.com/Bigdaddy1990/paw_control/issues) oder öffne ein Feature-Request via [GitHub Template](.github/ISSUE_TEMPLATE/)

