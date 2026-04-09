# PR Coverage Summary (2026-04-07)

## Täglicher Status (verbindlich)

### Gesamt-Coverage
- Gesamt-Line-Coverage aus `coverage.xml`: **14.25%** (Gate: **>= 85%**).
- Abweichung zum Gate: **-70.75 Prozentpunkte**.

### Gate-Modul-Status
| Gate-Modul | Status | Hinweis |
|---|---|---|
| `custom_components/pawcontrol/coordinator.py` | ⚠️ Offen | Coverage-Artefakt aus unterbrochenem Lauf ist nicht vollständig belastbar. |
| `custom_components/pawcontrol/config_flow.py` | ❌ Blockiert | Fehlender Eintrag in `coverage.xml` nach abgebrochenem Lauf. |
| `custom_components/pawcontrol/services.py` | ⚠️ Offen | Hoher Branch-Rückstand laut Priorisierungsliste. |
| `custom_components/pawcontrol/data_manager.py` | ⚠️ Offen | Hoher Branch-Rückstand laut Priorisierungsliste. |

### Offene Pakete
| Paket | Status | Nächster Schritt |
|---|---|---|
| Stabilisierung Hauptlauf | Offen | Blocker-Checks aus `docs/stability_test_backlog.md` strikt vorziehen. |
| Coverage-Paket `services.py` | Offen | 5-10 Branch-Ziele schneiden und Tests für Fehler-/Abbruchpfade bauen. |
| Coverage-Paket `data_manager.py` | Offen | Persistenz-/Fallback-Branches isolieren und regressionssicher testen. |
| Coverage-Paket `feeding_manager.py` | Offen | Negative Payload-Branches und Guard-Pfade priorisieren. |

## Offene Branches je Modul

> Referenzbasis für Funktionsnamen: `docs/coverage_gap_priorisierung.md`.

| Modul | Offene Branch-Cluster | Funktionsreferenzen (aus Priorisierung) | Priorität |
|---|---|---|---|
| `services.py` | Exception-/Abort-Pfade, `return False`, Service-Ergebnis-Logging | `async_setup_services`, `send_notification_service`, `_record_service_result`, `start_grooming_service`, `check_feeding_compliance_service` | Kritisch |
| `data_manager.py` | Export-/Reporting-Fehlerpfade, Persistenz-Fallbacks, `return False`-Semantik | `async_export_data`, `cache_repair_summary`, `async_generate_report`, `_export_single`, `async_get_module_history` | Kritisch |
| `feeding_manager.py` | Initialisierung, Snapshot-Bildung, Compliance-Failure-Branches | `_build_feeding_snapshot`, `async_check_feeding_compliance`, `_create_feeding_config`, `async_initialize`, `async_activate_emergency_feeding_mode` | Kritisch |
| `sensor.py` | Defensive Guards/`except`, native-value Varianten | `_compute_activity_score_optimized`, `native_value`, `_garden_attributes`, `_calculate_calories_from_activity` | Kritisch |
| `script_manager.py` | Resilience-Eskalation, Mapping-Fallbacks, `return False` | `_resolve_manual_resilience_events`, `get_resilience_escalation_snapshot`, `_manual_event_source_mapping`, `async_generate_scripts_for_dogs`, `_serialise_manual_event_record` | Kritisch |
| `repairs.py` | Recovery-/Issue-Publishing-Pfade, Coordinator-Fehlerpfade | `_check_notification_delivery_errors`, `async_publish_feeding_compliance_issue`, `_check_push_issues`, `_check_runtime_store_duration_alerts`, `async_step_init` | Mittel |
| `helpers.py` | Batch-Verarbeitung, Ladepfade, Guard-Decorator | `_process_walk_batch`, `async_load_data`, `decorator`, `__call__`, `_process_health_batch` | Kritisch |
| `telemetry.py` | Runtime-Store-Aggregation, Guard-Metrik-Fallbacks | `_summarise_runtime_store_assessment_events`, `update_runtime_entity_factory_guard_metrics`, `_build_runtime_store_assessment`, `_build_runtime_store_assessment_segments`, `update_runtime_store_health` | Mittel |
| `config_flow_main.py` | Discovery-/Import-Validierung, Reconfigure-Branches | `_merge_dog_entry`, `_normalise_discovery_metadata`, `_validate_import_config_enhanced`, `_build_dog_candidate`, `async_step_reconfigure` | Kritisch |
| `types.py` | Konvertierungs-/Validierungsfehler, `return False`-Defensivpfade | `ensure_dog_config_data`, `ensure_notification_options`, `from_mapping`, `ensure_gps_payload`, `from_dict` | Kritisch |

## Tägliche Mindestleistung (Definition)

Pro Arbeitstag muss mindestens **eine** der folgenden Bedingungen erfüllt sein:

1. **Mindestens 1 abgeschlossenes Paket** (Statuswechsel `Offen` -> `Erledigt` inkl. Testnachweis), **oder**
2. **Mindestens 2 Gate-Branch-Cluster abgeschlossen** (z. B. zwei Cluster aus der Tabelle „Offene Branches je Modul“ mit dokumentierter Testabdeckung).

Wenn beides nicht erreicht wurde, muss der Tagesabschluss eine konkrete Rest-Risiko-Notiz + Next-Step enthalten.

## Blockaden sofort markieren (Stop-the-line-Regel)

Sobald ein Coverage-Run blockiert (Collection-Abbruch, Import-/Syntaxfehler, instabile Flakes), gilt:

1. **Sofortige Markierung im Tagesstatus** mit Verweis auf `docs/stability_test_backlog.md`.
2. Neues oder betroffenes Ticket als `STAB-...` erfassen/aktualisieren, inkl. Repro-Befehl.
3. Coverage-Pakete bleiben in Status `On Hold`, bis der blockerrelevante Stabilitätspfad wieder grün ist.

Diese Regel verhindert stillstehenden Coverage-Fortschritt ohne sichtbaren Blocker-Track.
