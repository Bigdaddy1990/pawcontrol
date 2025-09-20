# Paw Control – Verbindliche Anforderungsaufnahme

Diese Aufstellung fasst alle in den zentralen Produktdokumenten zugesagten Funktionen der Paw-Control-Integration zusammen. Jede Anforderung ist einem Prioritätslevel zugeordnet und mit dem heutigen Implementierungsstand abgeglichen.

- **Quellenbasis:** `info.md`, `docs/comprehensive_readme.md`, `docs/automations_health_feeding.md`, `docs/options_flow_documentation.md`
- **Prioritäten:**
  - **Muss:** Kernfunktionalität, die laut Dokumentation zwingend vorhanden sein soll.
  - **Soll:** Wichtige Ergänzungen, die laut Beschreibung erwartet werden, aber nicht zwingend für den Grundbetrieb notwendig sind.
  - **Kann:** Komfort- oder Zukunftsfunktionen, die als wünschenswert beschrieben werden.
- **Statuslegende:**
  - **Umgesetzt:** Funktion ist im aktuellen Code nachweisbar.
  - **Teilweise:** Ansätze vorhanden, aber Funktionsumfang entspricht nicht der Beschreibung.
  - **Fehlt:** Keine Umsetzung gefunden.

## Zusammenfassung nach Bereichen

| Bereich | Muss | Soll | Kann |
| --- | --- | --- | --- |
| Setup & Konfiguration | 3 umgesetzt, 1 fehlt | 1 umgesetzt | – |
| Benachrichtigungen | 1 teilweise, 2 fehlen | 2 umgesetzt, 1 teilweise | 1 umgesetzt |
| Fütterung & Gesundheit | 4 teilweise/fehlen | 4 fehlen | 1 fehlt |
| Walk/GPS & Geofencing | 1 teilweise, 3 fehlen | 1 teilweise, 1 fehlt | – |
| Aktivitäten & Garten | 3 fehlen | 1 fehlt | – |
| Automationen & Skripte | 1 fehlt | 9 fehlen | – |
| Dashboard & UI | 1 teilweise | 2 teilweise/fehlen | 1 fehlt |
| Optionen & Systemeinstellungen | 2 umgesetzt, 3 fehlen | 2 umgesetzt | – |
| Sensoren & Entitäten | 2 fehlen | 4 fehlen | – |
| Services & APIs | 1 umgesetzt, 4 fehlen | 6 fehlen | – |

## Detaillierte Anforderungsmatrix

| Kategorie | Featureversprechen | Quelle(n) | Priorität | Status | Hinweise |
| --- | --- | --- | --- | --- | --- |
| Setup & Konfiguration | UI-Gestütztes Onboarding pro Hund inkl. Name, Türsensor, Push-Gerät | info.md | Muss | Umgesetzt | Entspricht `config_flow_*` und Options-Flow-Struktur. |
| Setup & Konfiguration | Mehrhundelogik mit eigenen Sensoren/Werten | info.md | Muss | Umgesetzt | Mehrhundeverwaltung über `options_flow` und `entity_factory`. |
| Setup & Konfiguration | Besuchshund-Modus mit separaten Statistiken | info.md | Muss | Umgesetzt | Buttons/Switches & Entities für Visitor-Mode vorhanden. |
| Setup & Konfiguration | Automatische Helper-Erstellung (input_boolean/input_datetime etc.) | info.md | Muss | Fehlt | Im Code keine Helper-Erzeugung. |
| Setup & Konfiguration | Konfigurierbarer Tagesreset um 23:59 Uhr | info.md | Soll | Umgesetzt | Service `daily_reset` + Option `reset_time`. |
| Benachrichtigungen | Dynamische Personenerkennung (`person.*` wenn home) | info.md | Muss | Fehlt | Benachrichtigungssystem nutzt keine Person-Entitäten. |
| Benachrichtigungen | Push-Rückfragen mit ✅/❌ und Quittierungslogik | info.md | Muss | Teilweise | Service zum Acknowledgement vorhanden, jedoch keine interaktive Aktionserkennung oder Türkontext. |
| Benachrichtigungen | Multi-Geräte-Synchronisierung (Antwort löscht auf allen Geräten) | info.md | Soll | Teilweise | Acknowledge-Service vorhanden, aber keine Kanalsynchronisierung implementiert. |
| Benachrichtigungen | Fallback auf statisch konfigurierte Geräte (`mobile_app_*`) | info.md | Soll | Umgesetzt | Benachrichtigungskonfiguration erlaubt mobile Dienste. |
| Benachrichtigungen | Benachrichtigungs-Test per Button/Service | info.md | Kann | Umgesetzt | `button.test_notification` verfügbar. |
| Fütterung & Gesundheit | Vier Mahlzeiten mit individuellen Toggles (`input_boolean`) | info.md | Muss | Fehlt | Keine Helper/Schalter für Mahlzeiten. |
| Fütterung & Gesundheit | Zeitgesteuerte Erinnerungen via `input_datetime` | info.md | Muss | Fehlt | Keine Helper-Generierung oder Zeitplanerkennung. |
| Fütterung & Gesundheit | Überfütterungs-Schutz und Warnungen | info.md | Muss | Teilweise | Health-Analyse kennt Overfeeding, aber keine Benachrichtigungen/Helper laut Doku. |
| Fütterung & Gesundheit | Tagesübersicht und Counter pro Mahlzeit | info.md | Muss | Teilweise | Feeding-Manager berechnet Daten, aber keine separaten Helper/Sensoren wie beschrieben. |
| Fütterung & Gesundheit | Wetterintegration für Gesundheitswarnungen (geplant) | info.md | Kann | Fehlt | Keine Wetterdaten-Anbindung. |
| Walk/GPS & Geofencing | Automatische Spaziergang-Erkennung über Türsensor | info.md, docs/comprehensive_readme.md | Muss | Fehlt | Türsensor wird nicht ausgewertet. |
| Walk/GPS & Geofencing | Live-GPS-Tracking & Route-Aufzeichnung | info.md, docs/comprehensive_readme.md | Muss | Teilweise | GPS-Punkte-Service vorhanden, aber kein vollwertiges Routen-Management. |
| Walk/GPS & Geofencing | Service `pawcontrol.setup_automatic_gps` inkl. Safe-Zone | info.md | Muss | Fehlt | Service nicht registriert. |
| Walk/GPS & Geofencing | Geofencing mit Sicherheitszonen & Alerts | docs/comprehensive_readme.md, docs/options_flow_documentation.md | Muss | Fehlt | Keine Geofence-Optionen oder Events. |
| Walk/GPS & Geofencing | Automatischer Walk-Start beim Verlassen des Hauses | docs/comprehensive_readme.md | Soll | Fehlt | Keine Logik für Auto-Start. |
| Walk/GPS & Geofencing | Routen-Export als GPX/GeoJSON | docs/comprehensive_readme.md | Soll | Teilweise | `export_data` kennt Format, aber kein dedizierter Route-Service. |
| Aktivitäten & Garten | Gartengang-Tracking inkl. Push-Rückfrage | info.md | Muss | Fehlt | Keine Gartensensoren oder Push-Workflows. |
| Aktivitäten & Garten | Aufenthaltsdauer & Zeitstempel für Gartenaufenthalte | info.md | Muss | Fehlt | Keine entsprechenden Sensoren. |
| Aktivitäten & Garten | Kot-Tracking Counter & Push-Abfragen | info.md | Muss | Fehlt | Service `log_poop` fehlt; keine Entitäten. |
| Aktivitäten & Garten | Manuelle Aktivitätserfassung | info.md | Soll | Fehlt | Keine UI/Service für manuelle Einträge. |
| Automationen & Skripte | Auto-generierte Skripte (Rückfragen, Reset, Push-Test) | info.md | Muss | Fehlt | Keine Skripterstellung im Code. |
| Automationen & Skripte | Gesundheits-/Fütterungsservices für Automationen (`recalculate_health_portions` etc.) | docs/automations_health_feeding.md | Soll | Fehlt | Services nicht vorhanden. |
| Automationen & Skripte | `adjust_calories_for_activity` Service | docs/automations_health_feeding.md | Soll | Fehlt | Nicht registriert. |
| Automationen & Skripte | `activate_diabetic_feeding_mode` Service | docs/automations_health_feeding.md | Soll | Fehlt | Nicht registriert. |
| Automationen & Skripte | `feed_with_medication` Service | docs/automations_health_feeding.md | Soll | Fehlt | Nicht registriert. |
| Automationen & Skripte | `generate_weekly_health_report` Service | docs/automations_health_feeding.md | Soll | Fehlt | Nicht registriert. |
| Automationen & Skripte | `activate_emergency_feeding_mode` Service | docs/automations_health_feeding.md | Soll | Fehlt | Nicht registriert. |
| Automationen & Skripte | `start_diet_transition` Service | docs/automations_health_feeding.md | Soll | Fehlt | Nicht registriert. |
| Automationen & Skripte | `check_feeding_compliance` Service | docs/automations_health_feeding.md | Soll | Fehlt | Nicht registriert. |
| Automationen & Skripte | `adjust_daily_portions` Service | docs/automations_health_feeding.md | Soll | Fehlt | Nicht registriert. |
| Automationen & Skripte | `add_health_snack` Service | docs/automations_health_feeding.md | Soll | Fehlt | Nicht registriert. |
| Dashboard & UI | Lovelace-fertiges YAML-Layout/Mushroom Dashboard | info.md | Muss | Teilweise | Dashboard-Generator vorhanden, aber kein fertiges YAML im Repo. |
| Dashboard & UI | Automatische Dashboard-Generierung pro Hund | info.md | Soll | Teilweise | Dashboard-Renderer vorhanden, aber kein Abgleich mit Dokument. |
| Dashboard & UI | Widget-Support / Quick Actions | docs/comprehensive_readme.md | Soll | Fehlt | Keine Widget-spezifischen Konfigurationen. |
| Dashboard & UI | Pause-Tracking Button | docs/comprehensive_readme.md | Kann | Fehlt | Button nicht vorhanden. |
| Optionen & Systemeinstellungen | Modulschalter für Feeding, GPS, Health, Walk, Grooming, Medication, Training | docs/options_flow_documentation.md | Muss | Umgesetzt | Options-Flow bietet Modulumschalter (teilweise abweichende Namen). |
| Optionen & Systemeinstellungen | Benachrichtigungseinstellungen inkl. Ruhezeiten, Wiederholintervalle | docs/options_flow_documentation.md | Muss | Umgesetzt | `async_step_notifications` deckt Optionen ab. |
| Optionen & Systemeinstellungen | Geofence-Optionen (`geofence_lat/lon/radius`, Alerts, Use Home Location) | docs/options_flow_documentation.md | Muss | Fehlt | Kein `async_step_geofence` oder Felder vorhanden. |
| Optionen & Systemeinstellungen | Systemoption `export_format` (csv/json/pdf) | docs/options_flow_documentation.md | Soll | Umgesetzt | System-Settings erlauben Formatwahl (über `export_settings`). |
| Optionen & Systemeinstellungen | Automatisches Gerätepruning | docs/options_flow_documentation.md | Soll | Umgesetzt | Option vorhanden. |
| Optionen & Systemeinstellungen | Route-Recording & History-Tage in GPS-Settings | docs/comprehensive_readme.md | Soll | Fehlt | Felder nicht vorhanden. |
| Sensoren & Entitäten | Sensor `sensor.{dog}_walk_distance_today` | docs/comprehensive_readme.md | Muss | Fehlt | Entität nicht erzeugt. |
| Sensoren & Entitäten | Sensoren `sensor.{dog}_daily_portions`, `sensor.{dog}_food_consumption` | docs/comprehensive_readme.md | Soll | Fehlt | Nicht implementiert. |
| Sensoren & Entitäten | Binary Sensor `binary_sensor.{dog}_needs_grooming` | docs/comprehensive_readme.md | Soll | Fehlt | Abweichende Benennung (`grooming_due`). |
| Sensoren & Entitäten | Device Tracker `device_tracker.{dog}_gps` mit Routen | docs/comprehensive_readme.md | Soll | Fehlt | Kein Device-Tracker-Setup. |
| Sensoren & Entitäten | Health-Feeding-Sensoren (`sensor.{dog}_calorie_goal_progress` etc.) | docs/automations_health_feeding.md | Soll | Fehlt | Entitäten nicht vorhanden. |
| Services & APIs | Service `pawcontrol.start_walk`/`end_walk` (Walk-Management) | docs/comprehensive_readme.md | Muss | Umgesetzt | Services in `services.py` vorhanden. |
| Services & APIs | Services `pawcontrol.gps_start_walk`, `gps_end_walk`, `gps_post_location`, `gps_export_last_route` | docs/comprehensive_readme.md | Muss | Fehlt | Nur generische Walk-Services vorhanden. |
| Services & APIs | Service `pawcontrol.feed_dog` | docs/comprehensive_readme.md | Muss | Fehlt | Nur `add_feeding`. |
| Services & APIs | Service `pawcontrol.log_health` | docs/comprehensive_readme.md | Muss | Fehlt | Nicht registriert. |
| Services & APIs | Service `pawcontrol.log_medication` | docs/comprehensive_readme.md | Soll | Fehlt | Nicht registriert. |
| Services & APIs | Service `pawcontrol.start_grooming` | docs/comprehensive_readme.md | Soll | Fehlt | Nicht registriert. |
| Services & APIs | Service `pawcontrol.export_data` mit `date_from/date_to` | docs/comprehensive_readme.md | Soll | Fehlt | Schema unterstützt nur `days`. |
| Services & APIs | Service `pawcontrol.generate_report` mit Format-Auswahl | docs/comprehensive_readme.md | Soll | Fehlt | Schema bietet nur `report_type/days`. |
