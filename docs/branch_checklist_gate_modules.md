# Branch-Checklist Gate-Module (Direkte Test-Checkliste)

Quelle: `docs/coverage_gap_priorisierung.md` (Branch-Indikatoren für Gate-Module).

## `custom_components/pawcontrol/services.py`

- [x] **L217 / L222 (`return False` in `_coerce_service_bool`)**
  - Triggerbedingung: Service-Boolean als falsy String/Integer (`"off"`, `0`).
  - Test: `test_coerce_service_bool_false_variants_are_deterministic`.
  - Fachliche Verifikation: Eingaben, die "aus" bedeuten, werden als `False` normalisiert.

- [x] **L1374 (`except InputCoercionError` in `_resolve_dog`)**
  - Triggerbedingung: `dog_id` ist kein String.
  - Test: `test_add_gps_point_rejects_non_string_dog_id`.
  - Fachliche Verifikation: Service meldet nutzerfreundlichen Validierungsfehler statt internem Traceback.

- [x] **L1506 (`except Exception` in `_wrap_service_handler`)**
  - Triggerbedingung: gekapselter Service wirft Runtime-Exception.
  - Test: `test_service_wrapper_marks_handler_exception_as_error`.
  - Fachliche Verifikation: Wrapper markiert Aufruf als Fehler und propagiert stabilen Service-Fehler.

- [x] **L1628 / L1637 (`except HomeAssistantError` / `except Exception` in Add-Feeding-Handler)**
  - Triggerbedingung: erwarteter Domänenfehler und unerwarteter Laufzeitfehler beim Speichern.
  - Test: `test_add_feeding_error_paths_record_and_raise`.
  - Fachliche Verifikation: erwartete Fehler werden direkt gereicht; unerwartete Fehler werden in konsistente Nutzerbotschaft gewrappt.

- [x] **L1715 / L1724 (`except HomeAssistantError` / `except Exception` in `add_gps_point_service`)**
  - Triggerbedingung: Koordinaten-/Manager-Fehler und unerwartete Laufzeitfehler.
  - Test: `test_add_gps_point_exception_is_wrapped_and_recorded` (+ vorhandener Erfolgspfadtest).
  - Fachliche Verifikation: fachlicher Fehlertext wird konsistent persistiert; unerwartete Ausnahmen werden als `HomeAssistantError` gekapselt.

- [x] **L1787 / L1796 (`except HomeAssistantError` / `except Exception` in `update_health_service`)**
  - Triggerbedingung: Manager validiert/fehlschlägt.
  - Test: `test_update_health_error_paths_record_and_raise`.
  - Fachliche Verifikation: erwartete Fehler bleiben präzise, generische Fehler bleiben stabilisiert.

- [x] **L1844 / L1853 (`except HomeAssistantError` / `except Exception` in `log_health_service`)**
  - Triggerbedingung: Persistenz/Runtime-Fehler beim Health-Log.
  - Test: `test_log_health_error_paths_record_and_raise`.
  - Fachliche Verifikation: Fehlerstatus wird persistiert, Rückmeldung bleibt nutzerfreundlich.

- [x] **L1908 / L1917 (`except HomeAssistantError` / `except Exception` in `log_medication_service`)**
  - Triggerbedingung: Medikamenten-Log wirft fachliche/unerwartete Ausnahme.
  - Test: `test_log_medication_error_paths_record_and_raise`.
  - Fachliche Verifikation: Service verhält sich deterministisch für Automationen und UI.

## `custom_components/pawcontrol/data_manager.py`

- [x] **L587 (`return False` in `_namespace_has_timestamp_field`)**
  - Triggerbedingung: skalare Payload ohne Timestamp-Feld.
  - Test: `test_namespace_has_timestamp_field_returns_false_for_scalars`.
  - Fachliche Verifikation: Timestamp-Scanner bleibt robust auf Nicht-Collections.

- [x] **L1141 (`except OSError` in `async_initialize`)**
  - Triggerbedingung: Storage-Verzeichnis kann nicht angelegt werden.
  - Test: `test_async_initialize_raises_homeassistant_error_on_storage_oserror`.
  - Fachliche Verifikation: Initialisierung bricht kontrolliert mit klarer Fehlermeldung ab.

- [x] **L1171 (`except HomeAssistantError` beim Namespace-Preload)**
  - Triggerbedingung: einzelner Namespace lädt beim Start nicht.
  - Test: `test_async_initialize_continues_when_namespace_preload_fails`.
  - Fachliche Verifikation: Initialisierung bleibt robust; Manager wird trotz Teilfehler als initialisiert markiert.

- [x] **L1186 (`except HomeAssistantError` in `async_shutdown`)**
  - Triggerbedingung: Speichern eines Profils beim Shutdown schlägt fehl.
  - Test: `test_async_shutdown_ignores_save_errors_for_each_profile`.
  - Fachliche Verifikation: Shutdown bleibt best-effort ohne ungefangenen Fehler.

- [x] **L1195 / L1223 (`return False`-Pfade in `async_log_feeding`)**
  - Triggerbedingung: unbekannte `dog_id` sowie Save-Fehler.
  - Tests: `test_async_log_feeding_returns_false_for_unknown_dog`, `test_async_log_feeding_returns_false_when_save_raises`.
  - Fachliche Verifikation: keine Persistenzversuche für nicht konfigurierte Hunde; Save-Fehler schlagen fachlich als `False` durch.

- [x] **L1276 (`except HomeAssistantError` in `async_set_visitor_mode`)**
  - Triggerbedingung: Namespace-Update schlägt fehl.
  - Test: `test_async_set_visitor_mode_propagates_homeassistant_error`.
  - Fachliche Verifikation: Fehler wird weitergereicht und Metriken zählen den Fehler.

- [x] **L1942 / L1944 (`except OverflowError` / `except ValueError` in Sort-Key)**
  - Triggerbedingung: unplausible UNIX-Timestamps in Modul-History.
  - Test: `test_module_history_handles_unix_timestamp_parse_failures`.
  - Fachliche Verifikation: Historienabruf bleibt stabil und sortierbar trotz fehlerhafter Werte.

- [x] **L1997 / L2015 (`return False` in `async_log_poop_data`)**
  - Triggerbedingung: unbekannte `dog_id` und Persistenzfehler.
  - Test: `test_async_log_poop_data_returns_false_on_unknown_or_persist_error`.
  - Fachliche Verifikation: API liefert kontrollierten Fehlschlag ohne Exception-Leak.

- [x] **L2223 (`return False` im Report-Window-Filter `_within_window`)**
  - Triggerbedingung: ungültiger Timestamp in Historie.
  - Test: `test_generate_report_skips_entries_with_invalid_timestamps`.
  - Fachliche Verifikation: Report ignoriert defekte Einträge statt gesamten Lauf abzubrechen.

## `custom_components/pawcontrol/config_flow.py`

- [x] Validierung: Export-Mapping und `__all__` sind stabil (`test_config_flow_exports_match_main_module`, `test_config_flow_exports_tuple_is_stable`).
- [x] Fehlerpfad: unbekannter Export bleibt `AttributeError` (`test_config_flow_unknown_export_raises_attribute_error`).
- [x] Recovery: Reload des Shim-Moduls hält Alias-Verkabelung stabil (`test_config_flow_reload_keeps_export_aliases_stable`).

## `custom_components/pawcontrol/coordinator.py`

- [x] Validierung: Fallback-Intervall bei `ValidationError` bleibt erhalten (`test_initial_update_interval_falls_back_on_validation_error`).
- [x] Fehlerpfade: `ConfigEntryAuthFailed`, `UpdateFailed` und generische Fehler werden korrekt propagiert/gewrappt.
- [x] Recovery: Sync-Fehler in `_synchronize_module_states` blockieren erfolgreichen Cycle nicht.
- [x] Ergebnis-Persistenz: leeres Registry-Setup liefert deterministisch `{}` zurück.

## Offene Folgekandidaten aus Priorisierung (außerhalb dieses Pakets)

- `data_manager.py`: Export-Partial-Branches rund um L2667/L2671/L2684 sowie weitere `return False`-Pfade in Walk-Flows.
- Nächste Ticketstufe laut Priorisierung: `feeding_manager.py`, danach `sensor.py`.
