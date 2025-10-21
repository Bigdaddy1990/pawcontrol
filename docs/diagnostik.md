# PawControl Diagnosebericht (Stand Integration `work`)

## Zusammenfassung

- Die aktuelle Integration liefert den in den Handbüchern beschriebenen Umfang für Garden-Tracking, Diet-Validierung, Health-Emergencies sowie GPS-/Geofencing-Workflows. Sämtliche zugesagten Entitäten existieren inklusive Übersetzungen und greifen auf Managerdaten aus dem Koordinator zu.
- Die Service-Schicht ist vollständig registriert, nutzt flächendeckend `ServiceValidationError` für Payload-Prüfungen und stellt auch die zuvor fehlenden GPS- und Garden-Services bereit.
- Diagnostics, Options-Flow und Manager-Struktur sind auf die erweiterten Module abgestimmt, sodass Support-Daten, Konfigurationspfade und Automations-Hooks den Dokumentationen entsprechen.

## Funktionsabgleich

### Garden-Tracking
- Sensorplattform: `sensor.py` enthält ein eigenes Garden-Modul mit zwölf spezialisierten Sensoren (u. a. `garden_time_today`, `last_garden_session`, `garden_activities_last_session`) auf Basis von `PawControlGardenSensorBase`, die über den Koordinator auf Snapshots des `GardenManager` zugreifen.【F:custom_components/pawcontrol/sensor.py†L1295-L1610】
- Binary-Sensoren: `binary_sensor.py` liefert `garden_session_active`, `in_garden` und `garden_poop_pending`, jeweils mit Manager-Fallback und Attributen für Pending-Confirmations.【F:custom_components/pawcontrol/binary_sensor.py†L1583-L1657】
- Buttons und Services: Die Tests decken Start/Stop/Pending-Flows ab; Garden-Daten werden im gemeinsamen Koordinator-Fixture bereitgestellt.【F:tests/components/pawcontrol/test_all_platforms.py†L69-L219】

### Health & Diet
- Health-Notfälle: `PawControlHealthEmergencyBinarySensor` stellt die dokumentierten Attribute (`emergency_type`, `portion_adjustment`, `activated_at`, `expires_at`, `status`) bereit und konsumiert Managerdaten.【F:custom_components/pawcontrol/binary_sensor.py†L1571-L1579】
- Diet-Validation: Separate Sensoren für Konflikte, Warnungen, Vet-Empfehlung, Anpassungsfaktor und Kompatibilitätsscore sind implementiert und lesen die `diet_validation_summary` aus dem Feeding-Modul.【F:custom_components/pawcontrol/sensor.py†L1952-L2179】【F:tests/components/pawcontrol/test_all_platforms.py†L91-L124】

### Services & Validierung
- Service-Infrastruktur: `services.py` registriert alle Feeding-, Walk-, Garden-, GPS-, Notification- und Helper-Services inklusive der vormals fehlenden GPS-Routenfunktionen (`gps_start_walk`, `gps_end_walk`, `gps_post_location`, `gps_export_route`, `setup_automatic_gps`).【F:custom_components/pawcontrol/services.py†L967-L1140】
- Eingabevalidierung: `_resolve_dog` und weitere Handler werfen bei fehlerhaften Parametern gezielt `ServiceValidationError`, womit die Qualitätsrichtlinie erfüllt ist.【F:custom_components/pawcontrol/services.py†L614-L688】

### GPS & Geofencing
- Manager: `PawControlGeofencing` implementiert Zone-Management, Persistenz, Background-Loops und Ereignisverarbeitung; die Initialisierung erzeugt automatisch eine Home-Zone und startet Monitoring-Tasks.【F:custom_components/pawcontrol/geofencing.py†L207-L360】
- Integrationseinbindung: Während des Setups wird der Geofencing-Manager erstellt, sobald GPS-Module aktiv sind; Koordinator und weitere Manager werden parallel initialisiert.【F:custom_components/pawcontrol/__init__.py†L320-L400】
- Service- und Optionspfad: Die GPS-Services verknüpfen Geofencing- und Notifications-Manager, und der Options-Flow stellt entsprechende Selektoren für Tracker, Personen und Safe-Zonen zur Verfügung.【F:custom_components/pawcontrol/services.py†L967-L1140】【F:custom_components/pawcontrol/config_flow_external.py†L80-L137】

### Diagnostics & QA
- Diagnostics-Modul exportiert Konfiguration, Laufzeitdaten, Performance-Metriken und redigierte Schlüssel, womit Support-Daten den Guides entsprechen.【F:custom_components/pawcontrol/diagnostics.py†L1-L187】
- Die Koordinator-Snapshots liefern ein stets vorhandenes `rejection_metrics`-Objekt mit `schema_version`, Ablehnungszählern, letzter Ablehnung und Breaker-IDs; Update- und Runtime-Statistiken spiegeln dieselben Werte selbst ohne aktiven Resilience-Manager wider, sodass die Platinum-Dashboards, die kommende UI-Aktualisierung und die Dokumentationen ohne Scraping auf die neuen Felder zugreifen können.【F:custom_components/pawcontrol/coordinator_observability.py†L40-L154】【F:custom_components/pawcontrol/coordinator_tasks.py†L672-L829】【F:custom_components/pawcontrol/diagnostics.py†L598-L666】【F:tests/unit/test_coordinator_observability.py†L1-L190】【F:tests/unit/test_coordinator_tasks.py†L200-L970】
- Service-Guards erfassen jeden Home-Assistant-Serviceaufruf in `ServiceGuardResult`-Snapshots, aggregieren Ausführungen und Übersprünge zu `ServiceGuardSummary`-Metriken und persistieren diese über `_record_service_result`, sodass Diagnostics und Resilience-Berichte anzeigen, wann Guards stattgefunden haben; der Export erfolgt jetzt gebündelt unter `service_execution.guard_metrics` samt letztem Eintrag in `service_execution.last_service_result` für den direkten Support-Zugriff.【F:custom_components/pawcontrol/service_guard.py†L1-L46】【F:custom_components/pawcontrol/utils.py†L187-L264】【F:custom_components/pawcontrol/services.py†L384-L473】【F:custom_components/pawcontrol/diagnostics.py†L780-L867】【F:tests/components/pawcontrol/test_diagnostics.py†L129-L203】
- Die Dashboard-Generatoren injizieren die `CoordinatorStatisticsPayload`-Snapshots des Koordinators in die Statistik-Ansicht, wodurch die Markdown-Zusammenfassung jetzt automatisch die Ablehnungszähler, Breaker-Anzahl und den Zeitstempel der letzten Ablehnung darstellt.【F:custom_components/pawcontrol/dashboard_generator.py†L120-L214】【F:custom_components/pawcontrol/dashboard_renderer.py†L148-L260】【F:custom_components/pawcontrol/dashboard_templates.py†L1330-L1387】【F:tests/unit/test_dashboard_templates.py†L390-L446】【F:tests/unit/test_dashboard_generator.py†L210-L272】
- Das Platinum-Diagnostics-Panel in der aktuellen UI-Build zeigt den neuen Block mit `schema_version: 2` unmittelbar unter den Performance-Karten an; der JSON-Ausschnitt unten stammt aus dem validierten Front-End-Snapshot und bestätigt, dass Dashboard, Backend und Dokumentation dieselbe Struktur nutzen.【F:custom_components/pawcontrol/coordinator_observability.py†L96-L154】【F:tests/unit/test_coordinator_observability.py†L88-L124】

### Leistungseinstellungen
- Die Leistungsmodi `minimal`, `balanced` und `full` werden zentral über `normalize_performance_mode` gepflegt; damit bleiben Optionen, Select-Plattform und gespeicherte Snapshots synchron, während das frühere Alias `standard` automatisch auf `balanced` normalisiert wird.【F:custom_components/pawcontrol/types.py†L456-L509】【F:custom_components/pawcontrol/select.py†L763-L806】
- Regressionstests sichern die Alias-Behandlung und stellen sicher, dass vorhandene Installationen nach dem Upgrade weiterhin mit dem kanonischen `balanced`-Standard starten, ohne dass Benutzer die Optionen manuell anpassen müssen.【F:tests/unit/test_types_performance_mode.py†L1-L35】

```json
{
  "rejection_metrics": {
    "schema_version": 2,
    "rejected_call_count": 0,
    "rejection_breaker_count": 0,
    "rejection_rate": 0.0,
    "last_rejection_time": null,
    "last_rejection_breaker_id": null,
    "last_rejection_breaker_name": null
  }
}
```
- Tests: `tests/components/pawcontrol/test_all_platforms.py` liefert eine umfassende Fixture mit Garden-, Diet- und Emergency-Daten für Sensor-, Binary-Sensor-, Button- und Servicepfade.【F:tests/components/pawcontrol/test_all_platforms.py†L1-L219】
- Cache-Reparatur-Telemetrie wird vor dem Export über `ensure_cache_repair_aggregate` in das `CacheRepairAggregate`-Dataclass-Format überführt, sodass Performance-, Services-, Koordinator- **und Diagnostik**-Pfad ausschließlich typisierte Payloads serialisieren und Reloads keinen Mapping-Fallback mehr zulassen.【F:custom_components/pawcontrol/coordinator_support.py†L132-L147】【F:custom_components/pawcontrol/performance.py†L149-L158】【F:custom_components/pawcontrol/services.py†L360-L363】【F:custom_components/pawcontrol/diagnostics.py†L300-L359】

## Verbleibende Beobachtungen

- Einige historische Konfigurationskonstanten wie `CONF_SOURCES`, `CONF_PERSON_ENTITIES`, `CONF_DEVICE_TRACKERS`, `CONF_CALENDAR` oder `CONF_WEATHER` sind weiterhin ausschließlich in `const.py` definiert und besitzen keine weiteren Verwendungen im aktiven Codepfad, obwohl ergänzende Features (z. B. externe Kalender-Hooks) in älteren Dokumenten erwähnt werden.【F:custom_components/pawcontrol/const.py†L101-L119】【904f82†L1-L6】
- Das Performance-Monitoring-Set (`CORE_SERVICES`, `PERFORMANCE_THRESHOLDS`) bleibt bislang unreferenziert; eine spätere Integration in Telemetrie- oder Diagnostics-Routinen ist möglich, derzeit existiert jedoch keine Auswertung.【F:custom_components/pawcontrol/const.py†L347-L356】【11fb2d†L1-L6】
- Dashboard-/Automation-Templates decken den dokumentierten Funktionsumfang bereits ab; zusätzliche End-to-End-Tests für GPS-/Geofencing-Flows können künftig Regressionen reduzieren.
