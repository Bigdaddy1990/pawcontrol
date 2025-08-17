# Paw Control Options Flow Dokumentation

## Übersicht

Der erweiterte Options Flow für die Paw Control Integration bietet eine umfassende, benutzerfreundliche Konfigurationsoberfläche, die es Benutzern ermöglicht, alle Aspekte ihrer Integration nach der ersten Einrichtung anzupassen.

## Architektur

### Hauptmerkmale

- **Menü-basierte Navigation**: Hierarchische Struktur für bessere Benutzerfreundlichkeit
- **Vollständige Typisierung**: Entspricht Home Assistant Platinum-Standards
- **Rückwärtskompatibilität**: Unterstützt bestehende Konfigurationen
- **Mehrsprachige Unterstützung**: Deutsche und englische Übersetzungen
- **Umfassende Validierung**: Robuste Fehlerbehandlung und Eingabevalidierung

### Design-Prinzipien

1. **Benutzerfreundlichkeit**: Intuitive Navigation mit klaren Kategorien
2. **Flexibilität**: Modulare Konfiguration ermöglicht selektive Aktivierung von Features
3. **Wartbarkeit**: Saubere Code-Struktur mit guter Dokumentation
4. **Erweiterbarkeit**: Einfache Erweiterung um neue Konfigurationsoptionen

## Konfigurationsbereiche

### 1. Geofence-Einstellungen (`geofence`)

Konfiguration der Heimposition und Geofencing-Optionen:

**Verfügbare Optionen:**
- `geofencing_enabled`: Aktivierung des Geofencing (Boolean)
- `geofence_lat`: Breitengrad der Heimposition (Float, -90 bis 90)
- `geofence_lon`: Längengrad der Heimposition (Float, -180 bis 180)
- `geofence_radius_m`: Radius der Geofence in Metern (Integer, 5-2000)
- `geofence_alerts_enabled`: Aktivierung von Geofence-Benachrichtigungen (Boolean)
- `use_home_location`: Verwendung der Home Assistant Heimposition (Boolean)

**Verwendung:**
```python
# Beispiel Geofence-Konfiguration
geofence_config = {
    \"geofencing_enabled\": True,
    \"geofence_lat\": 52.5200,
    \"geofence_lon\": 13.4050,
    \"geofence_radius_m\": 150,
    \"geofence_alerts_enabled\": True,
    \"use_home_location\": False
}
```

### 2. Benachrichtigungseinstellungen (`notifications`)

Konfiguration von Benachrichtigungen und Ruhezeiten:

**Verfügbare Optionen:**
- `notifications_enabled`: Aktivierung von Benachrichtigungen (Boolean)
- `quiet_hours_enabled`: Aktivierung von Ruhezeiten (Boolean)
- `quiet_start`: Startzeit der Ruhezeiten (String, HH:MM Format)
- `quiet_end`: Endzeit der Ruhezeiten (String, HH:MM Format)
- `reminder_repeat_min`: Wiederholungsintervall für Erinnerungen in Minuten (Integer, 5-120)

**Verwendung:**
```python
# Beispiel Benachrichtigungs-Konfiguration
notifications_config = {
    \"notifications_enabled\": True,
    \"quiet_hours_enabled\": True,
    \"quiet_start\": \"22:00\",
    \"quiet_end\": \"07:00\",
    \"reminder_repeat_min\": 30
}
```

### 3. Feature-Module (`modules`)

Aktivierung/Deaktivierung spezifischer Funktionen:

**Verfügbare Module:**
- `module_feeding`: Fütterungsmanagement (Boolean)
- `module_gps`: GPS-Verfolgung (Boolean)
- `module_health`: Gesundheitsüberwachung (Boolean)
- `module_walk`: Gassi-Verfolgung (Boolean)
- `module_grooming`: Pflegemanagement (Boolean)
- `module_training`: Trainingssitzungen (Boolean)
- `module_medication`: Medikamentenerinnerungen (Boolean)

**Verwendung:**
```python
# Beispiel Modul-Konfiguration
modules_config = {
    \"module_feeding\": True,
    \"module_gps\": True,
    \"module_health\": True,
    \"module_walk\": True,
    \"module_grooming\": False,  # Deaktiviert
    \"module_training\": True,
    \"module_medication\": True
}
```

### 4. Systemeinstellungen (`system`)

Allgemeine Systemkonfiguration:

**Verfügbare Optionen:**
- `reset_time`: Tägliche Zurücksetzungszeit (String, HH:MM:SS Format)
- `visitor_mode`: Aktivierung des Besuchermodus (Boolean)
- `export_format`: Standard-Exportformat (String: \"csv\", \"json\", \"pdf\")
- `auto_prune_devices`: Automatisches Entfernen alter Geräte (Boolean)

**Verwendung:**
```python
# Beispiel System-Konfiguration
system_config = {
    \"reset_time\": \"23:59:00\",
    \"visitor_mode\": False,
    \"export_format\": \"csv\",
    \"auto_prune_devices\": True
}
```

## Implementierungsdetails

### Klassenstruktur

```python
class OptionsFlowHandler(config_entries.OptionsFlow):
    \"\"\"Enhanced options flow with comprehensive configuration options.\"\"\"
    
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        \"\"\"Initialize options flow.\"\"\"
        self._entry = config_entry
        self._dogs_data: dict[str, Any] = {}
        self._current_dog_index = 0
        self._total_dogs = 0

    @property
    def _options(self) -> dict[str, Any]:
        \"\"\"Return current options with defaults.\"\"\"
        return self._entry.options

    @property  
    def _data(self) -> dict[str, Any]:
        \"\"\"Return current config data.\"\"\"
        return self._entry.data
```

### Flow-Methoden

Jeder Konfigurationsbereich hat eine dedizierte `async_step_*` Methode:

- `async_step_init()`: Hauptmenü
- `async_step_geofence()`: Geofence-Konfiguration
- `async_step_notifications()`: Benachrichtigungskonfiguration
- `async_step_modules()`: Modul-Konfiguration
- `async_step_system()`: Systemkonfiguration

### Validierung

Die Eingabevalidierung erfolgt über Voluptuous-Schemas:

```python
schema = vol.Schema({
    vol.Required(
        \"geofencing_enabled\",
        default=self._options.get(\"geofencing_enabled\", True),
    ): bool,
    vol.Optional(
        \"geofence_radius_m\",
        default=current_radius,
    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=2000)),
})
```

## Benutzerführung

### Navigation

1. **Hauptmenü**: Benutzer wählen den gewünschten Konfigurationsbereich
2. **Kategorie-spezifische Formulare**: Detailkonfiguration für den gewählten Bereich
3. **Bestätigung**: Änderungen werden gespeichert und übernommen

### Benutzererfahrung

- **Standardwerte**: Aktuelle Konfiguration wird als Standard angezeigt
- **Kontextuelle Hilfe**: Beschreibungen und Platzhalter-Texte
- **Validierung**: Sofortige Rückmeldung bei ungültigen Eingaben
- **Erhaltung bestehender Einstellungen**: Nicht geänderte Optionen bleiben erhalten

## Internationalisierung

### Unterstützte Sprachen

- **Englisch**: Vollständige Übersetzungen in `strings.json`
- **Deutsch**: Vollständige Übersetzungen in `translations/de.json`

### Übersetzungsstruktur

```json
{
    \"options\": {
        \"step\": {
            \"init\": {
                \"title\": \"Paw Control Options\",
                \"description\": \"Choose what you'd like to configure.\",
                \"menu_options\": {
                    \"geofence\": \"Geofence Settings\",
                    \"notifications\": \"Notifications\",
                    \"modules\": \"Feature Modules\",
                    \"system\": \"System Settings\"
                }
            }
        }
    }
}
```

## Testing

### Umfassende Testabdeckung

Der Options Flow wird durch umfassende Tests abgedeckt:

```python
async def test_options_flow_geofence_configuration(hass, mock_config_entry):
    \"\"\"Test geofence configuration through options flow.\"\"\"
    # Test implementation
```

**Testbereiche:**
- Menü-Navigation
- Formular-Darstellung
- Datenvalidierung
- Konfigurationsspeicherung
- Rückwärtskompatibilität
- Standardwerte
- Fehlerbehandlung

### Qualitätssicherung

- **100% Type Annotations**: Vollständige Typisierung
- **Pytest Integration**: Automatisierte Tests
- **Mock-basierte Tests**: Isolierte Testumgebung
- **Edge Case Coverage**: Grenzfälle und Fehlerbedingungen

## Migration und Kompatibilität

### Rückwärtskompatibilität

Der neue Options Flow ist vollständig rückwärtskompatibel:

```python
async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
    \"\"\"Manage the options with a menu-based approach.\"\"\"
    if user_input is not None:
        # Handle direct option updates (backward compatibility)
        return self.async_create_entry(title=\"\", data=user_input)
```

### Migration bestehender Konfigurationen

Bestehende Konfigurationen werden automatisch erkannt und als Standardwerte verwendet.

## Erweiterbarkeitleitfaden

### Hinzufügen neuer Konfigurationsbereiche

1. **Neue Menü-Option hinzufügen:**
```python
MENU_OPTIONS: Final[dict[str, str]] = {
    \"existing_option\": \"Existing Option\",
    \"new_option\": \"New Option\",  # Neue Option
}
```

2. **Neue Step-Methode implementieren:**
```python
async def async_step_new_option(
    self, user_input: dict[str, Any] | None = None
) -> FlowResult:
    \"\"\"Configure new option.\"\"\"
    # Implementation
```

3. **Schema definieren:**
```python
schema = vol.Schema({
    vol.Optional(\"new_setting\", default=default_value): validator,
})
```

4. **Übersetzungen hinzufügen:**
```json
{
    \"new_option\": {
        \"title\": \"New Option\",
        \"description\": \"Configure new option.\",
        \"data\": {
            \"new_setting\": \"New Setting\"
        }
    }
}
```

5. **Tests schreiben:**
```python
async def test_options_flow_new_option(hass, mock_config_entry):
    \"\"\"Test new option configuration.\"\"\"
    # Test implementation
```

## Best Practices

### Code-Qualität

1. **Typisierung**: Alle Funktionen und Variablen sind vollständig typisiert
2. **Dokumentation**: Comprehensive docstrings und Inline-Kommentare
3. **Fehlerbehandlung**: Robuste Behandlung von Edge Cases
4. **Validierung**: Strenge Eingabevalidierung mit aussagekräftigen Fehlermeldungen

### Benutzerfreundlichkeit

1. **Intuitive Navigation**: Logische Gruppierung verwandter Optionen
2. **Klare Beschreibungen**: Verständliche Texte und Hilfestellungen
3. **Konsistente Defaults**: Sinnvolle Standardwerte für alle Optionen
4. **Responsives Design**: Funktioniert auf verschiedenen Bildschirmgrößen

### Wartbarkeit

1. **Modulare Struktur**: Klar getrennte Konfigurationsbereiche
2. **Wiederverwendbare Komponenten**: Gemeinsame Validierungslogik
3. **Testbare Architektur**: Einfache Unit-Test-Erstellung
4. **Erweiterbare Basis**: Einfache Hinzufügung neuer Features

## Fazit

Der erweiterte Options Flow für Paw Control bietet eine umfassende, benutzerfreundliche und erweiterbare Konfigurationslösung, die den höchsten Home Assistant Standards entspricht. Durch die menü-basierte Navigation, vollständige Typisierung und umfassende Testabdeckung bietet er eine solide Grundlage für die Konfiguration aller Aspekte der Integration.

Die modulare Architektur und klare Dokumentation ermöglichen es Entwicklern, einfach neue Features hinzuzufügen, während die Rückwärtskompatibilität sicherstellt, dass bestehende Installationen nahtlos funktionieren.