# Coverage Hotspot Backlog (Top-Liste, paketiert)

## Snapshot-Metadaten

- **Snapshot-Datum (UTC):** 2026-04-07T02:33:24Z
- **Commit-SHA:** `1ef76b717cf547e6e242bf068c1a6e50e3a982e2`
- **Quelle:** `coverage.xml` (Cobertura XML)

## Top-Liste als 2–4h-Pakete (in Bearbeitungsreihenfolge)

## Verbindlicher Ablauf pro Paket

Jedes Coverage-Paket wird strikt nach diesem Ablauf abgearbeitet:

1. **10–15 Minuten:** Zielpfade aus dem Coverage-Report auswählen (nur das aktuelle Modulpaket).
2. **90–150 Minuten:** Tests schreiben und ausschließlich innerhalb **eines** Modulpakets bleiben.
3. **15 Minuten:** Flaky-/Determinismus-Härtung durchführen (z. B. Zeit einfrieren, Async-Abläufe deterministisch machen).
4. Paket sofort beenden, sobald das Mindestziel erreicht ist; **keine Nebenbaustellen** im selben Ticket.
5. Erst danach mit dem nächsten Paket starten – nur wenn das vorherige Paket dokumentiert abgeschlossen ist (neu abgedeckte Zeilen + betroffene Funktionen).

## Reihenfolge- und Gate-Regel (ohne Ausnahmen)

1. **Gate 0 zuerst:** Vor jedem Paketstart muss
   `docs/stability_test_backlog.md` keine offenen Hauptlauf-Blocker enthalten.
2. Paketbearbeitung erfolgt strikt in numerischer Reihenfolge:
   **Paket 1 → Paket 11**, **ohne Überspringen**.
3. Ein Paket gilt als abgeschlossen, sobald das jeweilige Mindestziel erreicht
   und in `docs/coverage_gap_priorisierung.md` mit Abschlussmarker dokumentiert ist.
4. Danach sofort nächstes Paket starten; keine Perfektionsarbeit im bereits
   geschlossenen Paket-Ticket.

Regeln für jedes Paket:

1. Paket nur mit zusammenhängenden Funktionen/Codepfaden bearbeiten.
2. Mindestziel in **neu abgedeckten Zeilen** erreichen.
3. Nach Zielerreichung Paket beenden (kein Perfektions-Scope im gleichen Ticket).

> Reihenfolge basiert auf der bestehenden Hotspot-Sortierung (Missing Lines), mit der geforderten Priorisierung: erst Gate-Module, danach `feeding_manager.py`, `sensor.py`, `script_manager.py`.

| Paket | Fokusmodule | Zusammenhängende Funktionen / Flows | Zeitbox | Mindestziel (neu abgedeckte Zeilen) |
|---:|---|---|---|---:|
| 1 | `custom_components/pawcontrol/services.py` (**Gate**) | Service-Registrierung, Handler-Dispatch, Validierungspfade pro Service-Aufruf | 3–4h | 120 |
| 2 | `custom_components/pawcontrol/data_manager.py` (**Gate**) | Persistenz-Lifecycle (`load`/`save`), Update-/Merge-Flows, Fehlerpfade bei Storage-I/O | 3–4h | 110 |
| 3 | `custom_components/pawcontrol/feeding_manager.py` | Fütterungsplanung, Zustandsübergänge rund um aktive/planned Feedings, Zeitfenster-Checks | 2–4h | 100 |
| 4 | `custom_components/pawcontrol/sensor.py` | Entity-Erzeugung, Sensor-State-Mapping, Availability-/Fallback-Pfade | 2–3h | 80 |
| 5 | `custom_components/pawcontrol/script_manager.py` | Script-Dispatch, Argument-Normalisierung, Fehlerbehandlung bei Script-Ausführung | 2–4h | 90 |
| 6 | `custom_components/pawcontrol/types.py` | Typ-Normalisierung, Hilfsfunktionen für Datentransformation, Grenzwert-/Fallback-Zweige | 3–4h | 120 |
| 7 | `custom_components/pawcontrol/repairs.py` + `custom_components/pawcontrol/telemetry.py` | Repair-Issue-Erzeugung, Telemetrie-Aggregation, Counter-/Schema-Pfade | 2–4h | 90 |
| 8 | `custom_components/pawcontrol/walk_manager.py` + `custom_components/pawcontrol/notifications.py` | Walk-Lifecycle, Notification-Trigger und Deduplizierungs-/Throttle-Zweige | 3–4h | 100 |
| 9 | `custom_components/pawcontrol/coordinator_tasks.py` + `custom_components/pawcontrol/weather_manager.py` | Coordinator-Task-Orchestrierung, wetterabhängige Entscheidungszweige | 2–4h | 90 |
| 10 | `custom_components/pawcontrol/entity_factory.py` + `custom_components/pawcontrol/door_sensor_manager.py` | Entity-Build-Pipeline, Door-Sensor-Normalisierung und Monitoring-Updates | 2–4h | 80 |
| 11 | `custom_components/pawcontrol/gps_manager.py` + `custom_components/pawcontrol/validation.py` | GPS-Statuspfade, Input-Validation und Fehler-/Grenzfallzweige | 2–3h | 70 |

## Gate-Definition

Als Gate-Module gelten: `coordinator.py`, `config_flow.py`, `services.py`, `data_manager.py`.

In dieser Top-Liste priorisiert enthaltene Gate-Module:

- `services.py`
- `data_manager.py`


## Ticket-Backlog je Paket (verbindlich vor erstem Test-Commit)

> Jedes Ticket bleibt strikt auf **ein Modul** begrenzt – außer bei den in der
> Paketliste bereits definierten Modul-Paaren.

### COV-001 — Paket 1 (`services.py`)
- **Modul-Fokus:** `custom_components/pawcontrol/services.py`
- **Branch-Plan (7 Ziele, vor erstem Test-Commit festzulegen):**
  1. Exception-Branch `async_setup_services` bei Service-Registrierung.
  2. Exception-Branch `async_setup_services` bei Handler-Bindung.
  3. Fehlerbranch `send_notification_service` bei ungültigem Payload.
  4. Fehlerbranch `start_grooming_service` bei fehlender Dog-Config.
  5. Negativbranch `check_feeding_compliance_service` bei fehlenden Daten.
  6. `return False`-Pfad `_record_service_result` für abgewiesenen Status.
  7. `return False`-Pfad im Service-Guard (`L217/L222` laut Gap-Doku).
- **Verpflichtende Funktionsnamen:** `async_setup_services`, `send_notification_service`, `_record_service_result`, `start_grooming_service`, `check_feeding_compliance_service`.
- **Abschlussnachweis Pflicht:** Getroffene Branches (IDs 1–7) + neu abgedeckte Zeilen (Datei + Zeilenbereiche).

### COV-002 — Paket 2 (`data_manager.py`)
- **Modul-Fokus:** `custom_components/pawcontrol/data_manager.py`
- **Branch-Plan (8 Ziele):**
  1. Exception-Branch in `async_export_data` (Export-Initialisierung).
  2. Negativbranch in `async_export_data` (`return False` bei Export-Fehler).
  3. Exception-Branch in `cache_repair_summary`.
  4. Fallback-Branch in `async_generate_report`.
  5. Exception-Branch in `_export_single`.
  6. Negativbranch in `_export_single` (Teilexport abgebrochen).
  7. Exception-Branch in `async_get_module_history`.
  8. Negativbranch in `async_get_module_history` (`return False`/leer-Fallback).
- **Verpflichtende Funktionsnamen:** `async_export_data`, `cache_repair_summary`, `async_generate_report`, `_export_single`, `async_get_module_history`.
- **Abschlussnachweis Pflicht:** Branch-Liste (1–8) + neu abgedeckte Zeilen.

### COV-003 — Paket 3 (`feeding_manager.py`)
- **Modul-Fokus:** `custom_components/pawcontrol/feeding_manager.py`
- **Branch-Plan (6 Ziele):**
  1. Exception-Branch in `_build_feeding_snapshot`.
  2. Negativbranch `async_check_feeding_compliance` (invalid state).
  3. Exception-Branch in `_create_feeding_config`.
  4. Initialisierungs-Fallback in `async_initialize`.
  5. Negativbranch in `async_activate_emergency_feeding_mode`.
  6. `return False`-Branch in Compliance-/Planungsvalidierung.
- **Verpflichtende Funktionsnamen:** `_build_feeding_snapshot`, `async_check_feeding_compliance`, `_create_feeding_config`, `async_initialize`, `async_activate_emergency_feeding_mode`.
- **Abschlussnachweis Pflicht:** Branch-Liste (1–6) + neu abgedeckte Zeilen.

### COV-004 — Paket 4 (`sensor.py`)
- **Modul-Fokus:** `custom_components/pawcontrol/sensor.py`
- **Branch-Plan (5 Ziele):**
  1. Exception-Branch in `_compute_activity_score_optimized`.
  2. Fallback-Branch `native_value` (Sensorvariante 1).
  3. Fallback-Branch `native_value` (Sensorvariante 2).
  4. Ausnahmebranch in `_garden_attributes`.
  5. Grenzwertbranch in `_calculate_calories_from_activity`.
- **Verpflichtende Funktionsnamen:** `_compute_activity_score_optimized`, `native_value`, `_garden_attributes`, `_calculate_calories_from_activity`.
- **Abschlussnachweis Pflicht:** Branch-Liste (1–5) + neu abgedeckte Zeilen.

### COV-005 — Paket 5 (`script_manager.py`)
- **Modul-Fokus:** `custom_components/pawcontrol/script_manager.py`
- **Branch-Plan (6 Ziele):**
  1. Exception-Branch `_resolve_manual_resilience_events`.
  2. Snapshot-Fallback in `get_resilience_escalation_snapshot`.
  3. Mapping-Fehlerbranch in `_manual_event_source_mapping`.
  4. Exception-Branch in `async_generate_scripts_for_dogs`.
  5. Serialisierungs-Fehlerbranch in `_serialise_manual_event_record`.
  6. `return False`-Branch (L337/L346/L751 laut Gap-Doku).
- **Verpflichtende Funktionsnamen:** `_resolve_manual_resilience_events`, `get_resilience_escalation_snapshot`, `_manual_event_source_mapping`, `async_generate_scripts_for_dogs`, `_serialise_manual_event_record`.
- **Abschlussnachweis Pflicht:** Branch-Liste (1–6) + neu abgedeckte Zeilen.

### COV-006 — Paket 6 (`types.py`)
- **Modul-Fokus:** `custom_components/pawcontrol/types.py`
- **Branch-Plan (7 Ziele):**
  1. Exception-Branch in `ensure_dog_config_data`.
  2. Fallback-Branch in `ensure_notification_options`.
  3. Fehlerbranch in `from_mapping`.
  4. Fehlerbranch in `ensure_gps_payload`.
  5. Fehlerbranch in `from_dict`.
  6. `return False`-Branch bei Validierungsablehnung.
  7. Grenzwertbranch bei Konvertierungs-Fallback.
- **Verpflichtende Funktionsnamen:** `ensure_dog_config_data`, `ensure_notification_options`, `from_mapping`, `ensure_gps_payload`, `from_dict`.
- **Abschlussnachweis Pflicht:** Branch-Liste (1–7) + neu abgedeckte Zeilen.

### COV-007 — Paket 7 (`repairs.py` + `telemetry.py`)
- **Modul-Fokus (Paar):** `custom_components/pawcontrol/repairs.py` + `custom_components/pawcontrol/telemetry.py`
- **Branch-Plan (8 Ziele):**
  1. Exception-Branch `async_publish_feeding_compliance_issue`.
  2. Fehlerbranch `_check_notification_delivery_errors`.
  3. Negativbranch `_check_push_issues`.
  4. Fallback `_check_runtime_store_duration_alerts`.
  5. Exception-Branch `_summarise_runtime_store_assessment_events`.
  6. Fehlerbranch `_build_runtime_store_assessment`.
  7. Fehlerbranch `_build_runtime_store_assessment_segments`.
  8. Update-Branch `update_runtime_entity_factory_guard_metrics`.
- **Verpflichtende Funktionsnamen:** `async_publish_feeding_compliance_issue`, `_check_notification_delivery_errors`, `_check_push_issues`, `_check_runtime_store_duration_alerts`, `_summarise_runtime_store_assessment_events`, `update_runtime_entity_factory_guard_metrics`, `_build_runtime_store_assessment`, `_build_runtime_store_assessment_segments`.
- **Abschlussnachweis Pflicht:** Branch-Liste (1–8) + neu abgedeckte Zeilen je Modul.

### COV-008 — Paket 8 (`walk_manager.py` + `notifications.py`)
- **Modul-Fokus (Paar):** `custom_components/pawcontrol/walk_manager.py` + `custom_components/pawcontrol/notifications.py`
- **Branch-Plan (6 Ziele):**
  1. Initialisierungsbranch `async_initialize`.
  2. GPS-Update-Fehlerbranch `async_update_gps_data`.
  3. Start-Fehlerbranch `async_start_walk` / `_start_walk_locked`.
  4. Abschluss-Fallback `async_end_walk`.
  5. Rate-Limit-Negativbranch `check_rate_limit`.
  6. Cleanup-/Snapshot-Branch `cleanup_expired` + `coordinator_snapshot`.
- **Verpflichtende Funktionsnamen:** `async_initialize`, `async_update_gps_data`, `async_start_walk`, `_start_walk_locked`, `async_end_walk`, `check_rate_limit`, `cleanup_expired`, `coordinator_snapshot`.
- **Abschlussnachweis Pflicht:** Branch-Liste (1–6) + neu abgedeckte Zeilen je Modul.

### COV-009 — Paket 9 (`coordinator_tasks.py` + `weather_manager.py`)
- **Modul-Fokus (Paar):** `custom_components/pawcontrol/coordinator_tasks.py` + `custom_components/pawcontrol/weather_manager.py`
- **Branch-Plan (5 Ziele):**
  1. Summen-/Fallback-Branch `_build_runtime_store_summary`.
  2. Negativbranch `derive_rejection_metrics` / `_derive_rejection_metrics`.
  3. Guard-Metrik-Branch `resolve_service_guard_metrics`.
  4. Guard-Metrik-Branch `resolve_entity_factory_guard_metrics`.
  5. Übersetzungs-/Alert-Fallback in `async_load_translations`, `_resolve_alert_translation`, `_resolve_recommendation_translation`.
- **Verpflichtende Funktionsnamen:** `_build_runtime_store_summary`, `derive_rejection_metrics`, `_derive_rejection_metrics`, `resolve_service_guard_metrics`, `resolve_entity_factory_guard_metrics`, `async_load_translations`, `_resolve_alert_translation`, `_resolve_recommendation_translation`.
- **Abschlussnachweis Pflicht:** Branch-Liste (1–5) + neu abgedeckte Zeilen je Modul.

### COV-010 — Paket 10 (`entity_factory.py` + `door_sensor_manager.py`)
- **Modul-Fokus (Paar):** `custom_components/pawcontrol/entity_factory.py` + `custom_components/pawcontrol/door_sensor_manager.py`
- **Branch-Plan (6 Ziele):**
  1. Cache-Vorwärm-Branch `_prewarm_caches`.
  2. Budget-Negativbranch `begin_budget`.
  3. Budget-Fallback `get_budget`.
  4. Einstellungs-Normalisierung `ensure_door_sensor_settings_config`.
  5. Payload-Serialisierung `_settings_to_payload`.
  6. Update-Branch `_apply_settings_to_config` / `_build_payload`.
- **Verpflichtende Funktionsnamen:** `_prewarm_caches`, `begin_budget`, `get_budget`, `ensure_door_sensor_settings_config`, `_settings_from_config`, `_settings_to_payload`, `_apply_settings_to_config`, `_build_payload`.
- **Abschlussnachweis Pflicht:** Branch-Liste (1–6) + neu abgedeckte Zeilen je Modul.

### COV-011 — Paket 11 (`gps_manager.py` + `validation.py`)
- **Modul-Fokus (Paar):** `custom_components/pawcontrol/gps_manager.py` + `custom_components/pawcontrol/validation.py`
- **Branch-Plan (5 Ziele):**
  1. Tracking-Konfig-Branch `_build_tracking_config`.
  2. Distanz-/Bearing-Grenzfälle `calculate_distance` + `calculate_bearing`.
  3. Konfigurations-Fehlerbranch `async_configure_dog_gps`.
  4. ID-/Zeitfenster-Negativbranch `normalize_dog_id` + `validate_time_window`.
  5. Koordinaten-/Entity-Validierung `validate_gps_coordinates`, `validate_entity_id`, `validate_interval`.
- **Verpflichtende Funktionsnamen:** `_build_tracking_config`, `calculate_distance`, `calculate_bearing`, `async_configure_dog_gps`, `normalize_dog_id`, `validate_time_window`, `validate_gps_coordinates`, `validate_entity_id`, `validate_interval`.
- **Abschlussnachweis Pflicht:** Branch-Liste (1–5) + neu abgedeckte Zeilen je Modul.
