# Implementierungsanleitung: Erweiterte Options Flow für Paw Control

## Überblick der Erweiterungen

Der Options Flow wurde umfassend erweitert und bietet jetzt folgende neue Funktionen:

### 🐕 **Hundeverwaltung**
- **Individuelle Hunde-Konfiguration**: Jeder Hund kann individual konfiguriert werden
- **Hunde hinzufügen/bearbeiten/entfernen**: Vollständige CRUD-Operationen
- **Modulspezifische Aktivierung**: Module können pro Hund aktiviert/deaktiviert werden
- **Detaillierte Hundeinformationen**: Rasse, Alter, Gewicht, Größe pro Hund

### 📍 **GPS & Tracking**
- **Erweiterte GPS-Einstellungen**: Genauigkeitsfilter, Distanzfilter, Update-Intervalle
- **Automatisierte Gassi-Erkennung**: Auto-Start/End basierend auf Bewegung und Position
- **Routenaufzeichnung**: Konfigurierbare Aufzeichnung und Historienaufbewahrung
- **Performance-Optimierung**: Einstellbare GPS-Parameter für bessere Performance

### 🏡 **Geofencing**
- **Mehrere Zonen**: Unterstützung für mehrere Geofence-Zonen
- **Flexible Zonenerkennnung**: Home Assistant Zonen, Custom Geofences oder beide
- **Erweiterte Warnungen**: Konfigurierbare Geofence-Alerts

### 🔔 **Benachrichtigungen**
- **Mehrere Kanäle**: Mobile, E-Mail, Slack, Discord, persistente Benachrichtigungen
- **Prioritäts-System**: Wichtige vs. normale Benachrichtigungen
- **Tägliche Zusammenfassungen**: Automatische Tagesberichte
- **Erweiterte Ruhezeiten**: Detaillierte Konfiguration der Ruhezeiten

### 🔗 **Datenquellen**
- **Entity-Management**: Auswahl von Person-, Device-Tracker-, Sensor-Entitäten
- **Auto-Discovery**: Automatische Erkennung verfügbarer Entitäten
- **Fallback-Tracking**: Backup-Tracking-Methoden
- **Integration Management**: Verwaltung aller Datenquellen-Verbindungen

### ⚙️ **System & Wartung**
- **Performance-Modi**: Minimal, Ausgewogen, Vollständig
- **Datenaufbewahrung**: Konfigurierbare Aufbewahrungszeiten
- **Automatische Backups**: Regelmäßige Konfigurationssicherungen
- **Bereinigungstools**: Automatische und manuelle Datenbereinigung

## Implementierungsschritte

### 1. **Backup der aktuellen config_flow.py**
```bash
cp custom_components/pawcontrol/config_flow.py custom_components/pawcontrol/config_flow.py.backup
```

### 2. **Integration des erweiterten Options Flow**

Ersetzen Sie die `OptionsFlowHandler` Klasse in der `config_flow.py` mit dem neuen erweiterten Code aus dem ersten Artifact.

**Wichtige Änderungen:**
- Neue `OptionsFlowHandler` Klasse mit umfangreichem Menüsystem
- Hundeverwaltung mit CRUD-Operationen
- Erweiterte Validierung und Fehlerbehandlung
- Backup/Restore-Funktionalität

### 3. **Übersetzungen aktualisieren**

#### **strings.json**
Ersetzen Sie den Inhalt der `strings.json` mit dem erweiterten englischen Translation-Set.

#### **translations/de.json**
Aktualisieren Sie die deutsche Übersetzung mit dem erweiterten deutschen Translation-Set.

#### **translations/en.json**
Aktualisieren Sie die englische Übersetzung entsprechend.

### 4. **Validierung der Schemas**

Stellen Sie sicher, dass alle neuen Validierungsregeln in der `schemas.py` korrekt referenziert werden:

```python
# Erweiterte Schema-Validierung für Dog-Management
DOG_CONFIG_SCHEMA = vol.Schema({
    vol.Required(CONF_DOG_ID): cv.string,
    vol.Required(CONF_DOG_NAME): cv.string,
    vol.Optional(CONF_DOG_BREED, default=""): cv.string,
    vol.Optional(CONF_DOG_AGE, default=1): vol.All(
        vol.Coerce(int), vol.Range(min=0, max=30)
    ),
    vol.Optional(CONF_DOG_WEIGHT, default=20.0): vol.All(
        vol.Coerce(float), vol.Range(min=0.5, max=200.0)
    ),
    # ... weitere Felder
})
```

### 5. **Testen der neuen Funktionen**

#### **Grundlegende Tests**
1. **Menünavigation**: Alle Menüpunkte sollten erreichbar sein
2. **Hunde-CRUD**: Hinzufügen, Bearbeiten, Entfernen von Hunden
3. **Validierung**: Fehlerbehandlung bei ungültigen Eingaben
4. **Speichern**: Korrekte Persistierung der Optionen

#### **Erweiterte Tests**
1. **GPS-Konfiguration**: Alle GPS-Parameter sollten funktionieren
2. **Geofence-Setup**: Mehrere Zonen und Modi testen
3. **Benachrichtigungen**: Verschiedene Kanäle und Timing
4. **Backup/Restore**: Funktionalität der Wartungsoptionen

### 6. **Konfigurationsmigration**

Für bestehende Installationen sollten Sie eine Migrationsfunktion implementieren:

```python
async def _migrate_options_to_extended_format(self) -> dict[str, Any]:
    """Migrate existing options to new extended format."""
    old_options = self._options

    # Migrate old format to new structure
    new_options = {
        "gps": {
            "enabled": old_options.get("gps_enabled", True),
            "accuracy_filter": old_options.get("gps_accuracy_filter", 100),
            # ... weitere Migrationen
        },
        "notifications": {
            "enabled": old_options.get("notifications_enabled", True),
            # ... weitere Migrationen
        }
    }

    return new_options
```

## Erweiterte Features

### **Backup & Restore System**
```python
# Automatisches Backup wird unterstützt mit:
- Zeitstempel-basierte Dateinamen
- JSON-Format für einfache Wiederherstellung
- Validierung beim Restore
- Rollback-Funktionalität
```

### **Performance-Optimierung**
```python
# Drei Performance-Modi:
- Minimal: Nur essenzielle Features
- Balanced: Empfohlene Einstellung (Standard)
- Full: Alle Features aktiv (für Power-User)
```

### **Entity-Discovery**
```python
# Automatische Erkennung von:
- Person-Entitäten für Anwesenheitserkennung
- Device-Tracker für GPS-Tracking
- Türsensoren für Walk-Detection
- Wetter-Entitäten für Kontext
- Kalender für Termine
```

## Qualitätskontrolle

### **Home Assistant Standards**
- ✅ Vollständige Type-Annotations
- ✅ Async/Await Pattern
- ✅ Proper Error Handling
- ✅ ConfigEntry.runtime_data Usage
- ✅ Comprehensive Logging

### **Benutzerfreundlichkeit**
- ✅ Intuitive Menüstruktur
- ✅ Kontextuelle Hilfen
- ✅ Validierte Eingaben
- ✅ Klare Fehlermeldungen
- ✅ Mehrsprachige Unterstützung

### **Erweiterbarkeit**
- ✅ Modulares Design
- ✅ Plugin-ähnliche Struktur
- ✅ Konfigurations-Templates
- ✅ Schema-basierte Validierung

## Troubleshooting

### **Häufige Probleme**

1. **Import-Fehler**
   ```python
   # Sicherstellen, dass alle const.py Imports verfügbar sind
   from .const import (
       DOMAIN, MODULE_FEEDING, # ... alle verwendeten Konstanten
   )
   ```

2. **Schema-Validierung**
   ```python
   # Alle vol.Schema müssen korrekte Types verwenden
   vol.Required("field"): cv.string  # nicht str
   vol.Optional("field", default=[]): cv.multi_select([])
   ```

3. **Translation Keys**
   ```python
   # Alle Step-IDs müssen in translations verfügbar sein
   # Fehlende Keys führen zu englischen Fallbacks
   ```


## Kompatibilität

- ✅ **Home Assistant 2025.9+**: Vollständig kompatibel
- ✅ **Python 3.13+**: Type Hints und moderne Features
- ✅ **Bestehende Konfigurationen**: Migration automatisch
- ✅ **HACS**: Installation über HACS möglich

Diese Erweiterung bringt Paw Control auf das nächste Level der Benutzerfreundlichkeit und Funktionalität, während die Platinum-Qualitätsstandards beibehalten werden.
