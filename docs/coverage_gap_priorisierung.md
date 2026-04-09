# Coverage Gap Priorisierung (Arbeitsgrundlage)

## Laufkontext
- Befehl: `pytest --cov=custom_components.pawcontrol --cov-branch --cov-report=term-missing:skip-covered --cov-report=xml:coverage.xml --cov-report=html:htmlcov -q`
- Ergebnis: Testlauf wurde gestartet; Coverage-Artefakte (`coverage.xml`, `htmlcov/`) wurden erzeugt, Pytest stoppte wegen verbleibender Syntaxfehler in Testdateien.


## Stabilitätsregel vor Coverage-Tickets

Vor neuen Coverage-Tickets muss das separate Stabilitäts-Backlog
`docs/stability_test_backlog.md` abgearbeitet werden, sobald der Hauptlauf
(Coverage-Run) durch Blocker abbricht. Die Reihenfolge ist verbindlich:

1. Fokuslauf stabilisieren
2. Blocker beheben
3. Danach Top-3-Coverage-Gaps schließen

### Gate 0 (Startbedingung je Paket)

Ein neues Coverage-Paket darf nur starten, wenn in
`docs/stability_test_backlog.md` **kein** offener Eintrag mit Hauptlauf-Effekt
mehr vorhanden ist.

### Feste Paket-Reihenfolge (verbindlich)

Paketbearbeitung ausschließlich in folgender Reihenfolge, ohne Überspringen:
**1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11** (gemäß
`docs/coverage_hotspot_backlog.md`).

### Paket-Abschlussmarker + Stop-Kriterium (Pflichtdokumentation)

Ein Paket wird sofort geschlossen, sobald das Mindestziel an neu abgedeckten
Zeilen erreicht ist. Danach sofort das nächste Paket starten.

| Paket | Mindestziel (neu abgedeckte Zeilen) | Stop-Kriterium | Abschlussdatum (UTC) | Bearbeitetes Modul | Neu abgedeckte Zeilen | Verantwortlich | Status |
|---:|---:|---|---|---|---:|---|---|
| 1 | 120 | Schließen bei `>=120` neuen Zeilen; danach direkt Paket 2 starten. | TBD | `custom_components/pawcontrol/services.py` | TBD | TBD | Offen |
| 2 | 110 | Schließen bei `>=110` neuen Zeilen; danach direkt Paket 3 starten. | TBD | `custom_components/pawcontrol/data_manager.py` | TBD | TBD | Offen |
| 3 | 100 | Schließen bei `>=100` neuen Zeilen; danach direkt Paket 4 starten. | TBD | `custom_components/pawcontrol/feeding_manager.py` | TBD | TBD | Offen |
| 4 | 80 | Schließen bei `>=80` neuen Zeilen; danach direkt Paket 5 starten. | TBD | `custom_components/pawcontrol/sensor.py` | TBD | TBD | Offen |
| 5 | 90 | Schließen bei `>=90` neuen Zeilen; danach direkt Paket 6 starten. | TBD | `custom_components/pawcontrol/script_manager.py` | TBD | TBD | Offen |
| 6 | 120 | Schließen bei `>=120` neuen Zeilen; danach direkt Paket 7 starten. | TBD | `custom_components/pawcontrol/types.py` | TBD | TBD | Offen |
| 7 | 90 | Schließen bei `>=90` neuen Zeilen; danach direkt Paket 8 starten. | TBD | `custom_components/pawcontrol/repairs.py` + `custom_components/pawcontrol/telemetry.py` | TBD | TBD | Offen |
| 8 | 100 | Schließen bei `>=100` neuen Zeilen; danach direkt Paket 9 starten. | TBD | `custom_components/pawcontrol/walk_manager.py` + `custom_components/pawcontrol/notifications.py` | TBD | TBD | Offen |
| 9 | 90 | Schließen bei `>=90` neuen Zeilen; danach direkt Paket 10 starten. | TBD | `custom_components/pawcontrol/coordinator_tasks.py` + `custom_components/pawcontrol/weather_manager.py` | TBD | TBD | Offen |
| 10 | 80 | Schließen bei `>=80` neuen Zeilen; danach direkt Paket 11 starten. | TBD | `custom_components/pawcontrol/entity_factory.py` + `custom_components/pawcontrol/door_sensor_manager.py` | TBD | TBD | Offen |
| 11 | 70 | Schließen bei `>=70` neuen Zeilen; Backlog-Runde beenden. | TBD | `custom_components/pawcontrol/gps_manager.py` + `custom_components/pawcontrol/validation.py` | TBD | TBD | Offen |

## Top-10 Dateien mit den meisten ungetesteten Zeilen

| Prio | Datei | Ungetestete Zeilen | Kategorie |
|---:|---|---:|---|
| 1 | `custom_components/pawcontrol/services.py` | 1647 | Kritisch |
| 2 | `custom_components/pawcontrol/data_manager.py` | 1364 | Kritisch |
| 3 | `custom_components/pawcontrol/feeding_manager.py` | 1360 | Kritisch |
| 4 | `custom_components/pawcontrol/sensor.py` | 1283 | Kritisch |
| 5 | `custom_components/pawcontrol/script_manager.py` | 1060 | Kritisch |
| 6 | `custom_components/pawcontrol/repairs.py` | 933 | Mittel |
| 7 | `custom_components/pawcontrol/helpers.py` | 928 | Kritisch |
| 8 | `custom_components/pawcontrol/telemetry.py` | 917 | Mittel |
| 9 | `custom_components/pawcontrol/config_flow_main.py` | 907 | Kritisch |
| 10 | `custom_components/pawcontrol/types.py` | 848 | Kritisch |

## Detailanalyse je Datei (unklare Pfade: Funktionen/Branches)

### 1) `custom_components/pawcontrol/services.py` — 1647 ungetestete Zeilen (Kritisch)
- Größte ungetestete Funktionen:
  - `async_setup_services` (L1308-L5001): ~1235 ungetestete Zeilen
  - `send_notification_service` (L2578-L2785): ~83 ungetestete Zeilen
  - `_record_service_result` (L498-L663): ~80 ungetestete Zeilen
  - `start_grooming_service` (L3981-L4170): ~78 ungetestete Zeilen
  - `check_feeding_compliance_service` (L3600-L3782): ~58 ungetestete Zeilen
- Ungetestete kritische Branch-Indikatoren:
  - `except`-Pfade: L1374, L1506, L1628, L1637, L1715, L1724, L1787, L1796, L1844, L1853, L1908, L1917
  - `return False`-Pfade: L217, L222
  - `coordinator`-Fehlerpfade: keine in Top-Bereich gefunden

### 2) `custom_components/pawcontrol/data_manager.py` — 1364 ungetestete Zeilen (Kritisch)
- Größte ungetestete Funktionen:
  - `async_export_data` (L2400-L2654): ~126 ungetestete Zeilen
  - `cache_repair_summary` (L1561-L1771): ~121 ungetestete Zeilen
  - `async_generate_report` (L2169-L2336): ~69 ungetestete Zeilen
  - `_export_single` (L2498-L2616): ~58 ungetestete Zeilen
  - `async_get_module_history` (L1863-L1957): ~48 ungetestete Zeilen
- Ungetestete kritische Branch-Indikatoren:
  - `except`-Pfade: L1141, L1171, L1186, L1222, L1276, L1588, L1605, L1942, L1944, L2014, L2478, L2683
  - `return False`-Pfade: L587, L1195, L1223, L1997, L2015, L2223, L2667, L2671, L2684, L2705, L2710, L2735
  - `coordinator`-Fehlerpfade: keine in Top-Bereich gefunden

### 3) `custom_components/pawcontrol/feeding_manager.py` — 1360 ungetestete Zeilen (Kritisch)
- Größte ungetestete Funktionen:
  - `_build_feeding_snapshot` (L2291-L2612): ~173 ungetestete Zeilen
  - `async_check_feeding_compliance` (L4097-L4320): ~71 ungetestete Zeilen
  - `_create_feeding_config` (L1372-L1654): ~66 ungetestete Zeilen
  - `async_initialize` (L1232-L1370): ~56 ungetestete Zeilen
  - `async_activate_emergency_feeding_mode` (L3806-L3959): ~47 ungetestete Zeilen
- Ungetestete kritische Branch-Indikatoren:
  - `except`-Pfade: L656, L981, L993, L1069, L1273, L1277, L1666, L1669, L1752, L1767, L1769, L1852
  - `return False`-Pfade: L408, L3180, L3218, L3238, L3261
  - `coordinator`-Fehlerpfade: keine in Top-Bereich gefunden

### 4) `custom_components/pawcontrol/sensor.py` — 1283 ungetestete Zeilen (Kritisch)
- Größte ungetestete Funktionen:
  - `_compute_activity_score_optimized` (L978-L1118): ~55 ungetestete Zeilen
  - `native_value` (L1221-L1302): ~40 ungetestete Zeilen
  - `_garden_attributes` (L665-L743): ~38 ungetestete Zeilen
  - `_calculate_calories_from_activity` (L3250-L3313): ~30 ungetestete Zeilen
  - `native_value` (L872-L920): ~27 ungetestete Zeilen
- Ungetestete kritische Branch-Indikatoren:
  - `except`-Pfade: L201, L203, L208, L210, L514, L530, L914, L970, L995, L1003, L1011, L1028
  - `return False`-Pfade: keine in Top-Bereich gefunden
  - `coordinator`-Fehlerpfade: keine in Top-Bereich gefunden

### 5) `custom_components/pawcontrol/script_manager.py` — 1060 ungetestete Zeilen (Kritisch)
- Größte ungetestete Funktionen:
  - `_resolve_manual_resilience_events` (L825-L1036): ~108 ungetestete Zeilen
  - `get_resilience_escalation_snapshot` (L2286-L2521): ~105 ungetestete Zeilen
  - `_manual_event_source_mapping` (L1070-L1180): ~75 ungetestete Zeilen
  - `async_generate_scripts_for_dogs` (L1737-L1877): ~71 ungetestete Zeilen
  - `_serialise_manual_event_record` (L1349-L1499): ~56 ungetestete Zeilen
- Ungetestete kritische Branch-Indikatoren:
  - `except`-Pfade: L167, L880, L882, L884
  - `return False`-Pfade: L337, L346, L751
  - `coordinator`-Fehlerpfade: keine in Top-Bereich gefunden

### 6) `custom_components/pawcontrol/repairs.py` — 933 ungetestete Zeilen (Mittel)
- Größte ungetestete Funktionen:
  - `_check_notification_delivery_errors` (L966-L1209): ~79 ungetestete Zeilen
  - `async_publish_feeding_compliance_issue` (L318-L510): ~63 ungetestete Zeilen
  - `_check_push_issues` (L747-L858): ~51 ungetestete Zeilen
  - `_check_runtime_store_duration_alerts` (L1537-L1615): ~41 ungetestete Zeilen
  - `async_step_init` (L1732-L1798): ~40 ungetestete Zeilen
- Ungetestete kritische Branch-Indikatoren:
  - `except`-Pfade: L127, L147, L149, L566, L961, L1075, L1545, L1623, L1687, L1700, L1923, L2105
  - `return False`-Pfade: L148, L150, L2964, L2979
  - `coordinator`-Fehlerpfade: L1701, L1796, L1797

### 7) `custom_components/pawcontrol/helpers.py` — 928 ungetestete Zeilen (Kritisch)
- Größte ungetestete Funktionen:
  - `_process_walk_batch` (L1414-L1567): ~75 ungetestete Zeilen
  - `async_load_data` (L824-L901): ~46 ungetestete Zeilen
  - `decorator` (L2027-L2097): ~44 ungetestete Zeilen
  - `__call__` (L2009-L2099): ~44 ungetestete Zeilen
  - `_process_health_batch` (L1339-L1412): ~43 ungetestete Zeilen
- Ungetestete kritische Branch-Indikatoren:
  - `except`-Pfade: L510, L512, L536, L538, L569, L664, L666, L730, L741, L783, L785, L834
  - `return False`-Pfade: L347
  - `coordinator`-Fehlerpfade: keine in Top-Bereich gefunden

### 8) `custom_components/pawcontrol/telemetry.py` — 917 ungetestete Zeilen (Mittel)
- Größte ungetestete Funktionen:
  - `_summarise_runtime_store_assessment_events` (L382-L661): ~137 ungetestete Zeilen
  - `update_runtime_entity_factory_guard_metrics` (L1321-L1578): ~133 ungetestete Zeilen
  - `_build_runtime_store_assessment` (L1119-L1318): ~105 ungetestete Zeilen
  - `_build_runtime_store_assessment_segments` (L664-L747): ~59 ungetestete Zeilen
  - `update_runtime_store_health` (L1021-L1116): ~58 ungetestete Zeilen
- Ungetestete kritische Branch-Indikatoren:
  - `except`-Pfade: L1780, L1782
  - `return False`-Pfade: keine in Top-Bereich gefunden
  - `coordinator`-Fehlerpfade: keine in Top-Bereich gefunden

### 9) `custom_components/pawcontrol/config_flow_main.py` — 907 ungetestete Zeilen (Kritisch)
- Größte ungetestete Funktionen:
  - `_merge_dog_entry` (L2215-L2355): ~69 ungetestete Zeilen
  - `_normalise_discovery_metadata` (L499-L608): ~60 ungetestete Zeilen
  - `_validate_import_config_enhanced` (L306-L461): ~57 ungetestete Zeilen
  - `_build_dog_candidate` (L2398-L2480): ~51 ungetestete Zeilen
  - `async_step_reconfigure` (L1677-L1839): ~46 ungetestete Zeilen
- Ungetestete kritische Branch-Indikatoren:
  - `except`-Pfade: L281, L286, L357, L450, L457, L576, L599, L834, L843, L931, L1143, L1274
  - `return False`-Pfade: L697, L1431, L2120, L2544
  - `coordinator`-Fehlerpfade: keine in Top-Bereich gefunden

### 10) `custom_components/pawcontrol/types.py` — 848 ungetestete Zeilen (Kritisch)
- Größte ungetestete Funktionen:
  - `ensure_dog_config_data` (L6682-L6798): ~76 ungetestete Zeilen
  - `ensure_notification_options` (L1957-L2030): ~48 ungetestete Zeilen
  - `from_mapping` (L5331-L5422): ~40 ungetestete Zeilen
  - `ensure_gps_payload` (L4355-L4427): ~40 ungetestete Zeilen
  - `from_dict` (L7668-L7728): ~33 ungetestete Zeilen
- Ungetestete kritische Branch-Indikatoren:
  - `except`-Pfade: L209, L1384, L1400, L2000, L4395, L4401, L5344, L5358, L7686, L7705, L8427
  - `return False`-Pfade: L1353, L1982, L8417, L8429, L8431, L8460, L8465, L8468, L8471, L8476, L8483, L8511
  - `coordinator`-Fehlerpfade: keine in Top-Bereich gefunden

## Priorisierte Testticket-Reihenfolge (ab jetzt verbindliche Arbeitsgrundlage)
1. **Kritisch**: `services.py` Fehler-/Abbruchpfade und `return False`-Semantik absichern.
2. **Kritisch**: `data_manager.py` Entity-State- und Persistenzpfade (inkl. Exception-Fallbacks) testen.
3. **Kritisch**: `feeding_manager.py` Kernzustand/Planungslogik (negative/invalid payload paths) abdecken.
4. **Kritisch**: `sensor.py` Core-Entity-Entscheidungen + defensive Guards absichern.
5. **Kritisch**: `script_manager.py` Service-Orchestrierung inkl. coordinator-bezogene Fehlerpfade.
6. **Mittel**: `repairs.py`, `helpers.py`, `telemetry.py` (Fehlerbehandlung/Recovery/Monitoring).
7. **Mittel**: `config_flow_main.py`, `types.py`, `dashboard_templates.py` (Validierung, Konvertierung, Template-Fails).

> Hinweis: Diese Liste priorisiert Risiko (Core-Logik > Fehlerbehandlung > defensive/logging-only) und dient als Basis für alle folgenden Testtickets.


## Funktionsanker für Hotspot-Pakete 8–11 (Ticket-Planung)

Zur Umsetzung der Paketliste aus `docs/coverage_hotspot_backlog.md` werden die
folgenden konkreten Funktionen als verpflichtende Ticket-Anker ergänzt.

### 11) `custom_components/pawcontrol/walk_manager.py` (Ergänzung für Paket 8)
- `async_initialize`
- `async_update_gps_data`
- `async_start_walk`
- `_start_walk_locked`
- `async_end_walk`

### 12) `custom_components/pawcontrol/notifications.py` (Ergänzung für Paket 8)
- `_empty_custom_settings`
- `_empty_rate_limit_config`
- `check_rate_limit`
- `cleanup_expired`
- `coordinator_snapshot`

### 13) `custom_components/pawcontrol/coordinator_tasks.py` (Ergänzung für Paket 9)
- `_build_runtime_store_summary`
- `derive_rejection_metrics`
- `_derive_rejection_metrics`
- `resolve_service_guard_metrics`
- `resolve_entity_factory_guard_metrics`

### 14) `custom_components/pawcontrol/weather_manager.py` (Ergänzung für Paket 9)
- `get_weather_translations`
- `async_load_translations`
- `_resolve_alert_translation`
- `_resolve_recommendation_translation`
- `is_valid`

### 15) `custom_components/pawcontrol/entity_factory.py` (Ergänzung für Paket 10)
- `_prewarm_caches`
- `begin_budget`
- `get_budget`
- `_update_last_estimate_state`
- `snapshot`

### 16) `custom_components/pawcontrol/door_sensor_manager.py` (Ergänzung für Paket 10)
- `ensure_door_sensor_settings_config`
- `_settings_from_config`
- `_settings_to_payload`
- `_apply_settings_to_config`
- `_build_payload`

### 17) `custom_components/pawcontrol/gps_manager.py` (Ergänzung für Paket 11)
- `_build_tracking_config`
- `calculate_distance`
- `calculate_bearing`
- `async_configure_dog_gps`
- `set_notification_manager`

### 18) `custom_components/pawcontrol/validation.py` (Ergänzung für Paket 11)
- `normalize_dog_id`
- `validate_time_window`
- `validate_gps_coordinates`
- `validate_entity_id`
- `validate_interval`
