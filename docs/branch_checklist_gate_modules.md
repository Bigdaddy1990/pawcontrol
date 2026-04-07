# Branch-Checklist Gate-Module (Direkte Test-Checkliste)

Quelle: `docs/coverage_gap_priorisierung.md` (Branch-Indikatoren für Gate-Module).

## `custom_components/pawcontrol/services.py`

- [x] **L217 / L222 (`return False` in `_coerce_service_bool`)**
  - Triggerbedingung: Service-Boolean als falsy String/Integer (`"off"`, `0`).
  - Minimaler Testfall: `test_coerce_service_bool_false_values`.
  - Fachliche Verifikation: Eingaben, die "aus" bedeuten, werden als `False` normalisiert.

- [x] **L1374 (`except InputCoercionError` in `_resolve_dog`)**
  - Triggerbedingung: `dog_id` ist kein String.
  - Minimaler Testfall: `test_given_add_gps_point_when_dog_id_not_string_then_raise_validation_error`.
  - Fachliche Verifikation: Service meldet nutzerfreundlichen Validierungsfehler statt internem Traceback.

- [x] **L1715 (`except HomeAssistantError` in `add_gps_point_service`)**
  - Triggerbedingung: Koordinatenvalidierung wirft `HomeAssistantError`.
  - Minimaler Testfall: `test_given_add_gps_point_when_coordinate_validation_fails_then_propagate_error`.
  - Fachliche Verifikation: fachlicher Fehlertext wird unverändert zurückgegeben; Ergebnisstatus wird als Fehler persistiert.

- [x] **L1724 (`except Exception` in `add_gps_point_service`)**
  - Triggerbedingung: Laufzeitfehler in `walk_manager.async_add_gps_point`.
  - Minimaler Testfall: `test_given_add_gps_point_when_walk_manager_crashes_then_wrap_error`.
  - Fachliche Verifikation: Unerwartete Ausnahmen werden als `HomeAssistantError` mit stabiler Nutzerbotschaft gekapselt.

## `custom_components/pawcontrol/data_manager.py`

- [x] **L1141 (`except OSError` in `async_initialize`)**
  - Triggerbedingung: Storage-Verzeichnis kann nicht angelegt werden.
  - Minimaler Testfall: `test_async_initialize_raises_home_assistant_error_when_storage_dir_creation_fails`.
  - Fachliche Verifikation: Initialisierung bricht kontrolliert mit klarer Fehlermeldung ab.

- [x] **L1171 (`except HomeAssistantError` beim Namespace-Preload)**
  - Triggerbedingung: einzelner Namespace lädt beim Start nicht.
  - Minimaler Testfall: `test_async_initialize_continues_when_namespace_preload_fails`.
  - Fachliche Verifikation: Initialisierung bleibt robust; Manager wird trotz Teilfehler als initialisiert markiert.

- [x] **L1195 (`return False` in `async_log_feeding`)**
  - Triggerbedingung: unbekannte `dog_id`.
  - Minimaler Testfall: `test_async_log_feeding_returns_false_for_unknown_dog`.
  - Fachliche Verifikation: keine Persistenzversuche für nicht konfigurierte Hunde.

- [x] **L1223 (`return False` in `async_log_feeding` bei Save-Fehler)**
  - Triggerbedingung: `_async_save_dog_data` wirft `HomeAssistantError`.
  - Minimaler Testfall: `test_async_log_feeding_returns_false_when_persist_fails`.
  - Fachliche Verifikation: Service signalisiert fachlich "nicht gespeichert" ohne unkontrollierte Ausnahme.

## Folge-Module (nur bei Bedarf laut Priorisierung)

- `config_flow.py` / `coordinator.py`: aktuell nicht erweitert, da Gate-Module zuerst priorisiert wurden.
