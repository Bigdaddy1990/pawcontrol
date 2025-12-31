# Development plan

## Aktueller Baustellenüberblick

- Typing-Blöcke in den Flows/Optionen schließen: Placeholder-TypedDicts (`ReauthPlaceholders`, Reconfigure, Dashboard) per `MappingProxyType` mit Literal-Keys einfrieren und `dict(...)`-Konvertierungen entfernen; Options-/Data-Payloads auf JSONValue- und TypedDict-konforme Mappings klemmen.
- Binary-Sensor-Attribute anpassen: `extra_state_attributes` auf `JSONMutableMapping` bzw. die Basismethode klemmen, damit die Overrides mit `PawControlEntity` kompatibel werden.
- Offene JSONValue-Kanten und Guards: `missing_sensors.py` auf ISO/JSONValue trimmen, `optimized_entity_base.py`-Mapping-Casts vereinheitlichen, Quiet-Hours-Tests für fehlerhafte Optionen ergänzen, hassfest-Shim gegen neue Manifest/Translation-Regeln abgleichen.
- Registry- und Flow-Stubs mit HA-Release-Notes synchron halten (FlowResult-/ConfigEntryState-/ConfigEntry-Support-Flags, Subentries, Registry-Merge-Heuristiken), damit die Offline-Tests API-Drift weiter melden.
- Mypy-Gesamtfehlstand abbauen: offene Fehler v. a. in `compat.py`, `resilience.py`, `utils.py`, `telemetry.py`, `feeding_manager.py`, `notifications.py`, `services.py`, `repairs.py`, `coordinator.py`, `data_manager.py`, `options_flow.py`, `binary_sensor.py`, `missing_sensors.py`, `config_flow*` und `text.py`; Redundant-Casts entfernen, ungetypte Decorators parametrieren, Tasks/Callables typisieren und JSONValue-Rückgaben vereinheitlichen.

## Plan zur Fertigstellung

1. Flows/Optionen typisieren:
   - `config_flow.py`: Reauth/Reconfigure/Dashboard-Placeholders per `MappingProxyType` mit Literal-Keys einfrieren, Options-/Data-Payloads auf `dict[str, JSONValue]` klemmen, Entry-Casts auf `Mapping[str, int | float | str]` setzen.
   - `config_flow_dogs.py`: Placeholder-Freezes, Hunde-/Modul-Listen auf JSONValue/TypedDict clampen, offene `object`-Assigns eliminieren.
   - `config_flow_dashboard_extension.py`: Dashboard-Placeholders einfrieren, Payload-Coercions auf JSONValue/Casts auf `Mapping[str, int | float | str]` ergänzen.
   - `options_flow.py`: Options-/Dashboard-Placeholders einfrieren, Optionspayloads auf `dict[str, JSONValue]` normalisieren, Entry-Coercer und TypedDict-Keys sichern.
   - `config_flow_external.py`: External-Placeholders auf `Mapping[str, int | float | str]` klemmen, via `MappingProxyType` einfrieren, Payloads JSONValue-sicher machen.
   - `config_flow_profile.py`: Profile-Placeholders/Literals einfrieren, Payloads auf JSONValue trimmen und String-Guards für Profile erzwingen.
2. Binary-Sensor-Attributes härten: `binary_sensor.py` Overrides auf Basissignatur klemmen und JSONMutableMapping erzwingen.
3. JSONValue-Gaps schließen: `missing_sensors.py`, `optimized_entity_base.py`, Quiet-Hours-Parser-Tests, hassfest-Shim-Regressionen aktualisieren.
4. Registry-/Flow-Stubs mit aktuellen HA-Release-Notes synchronisieren (FlowResult/ConfigEntryState/Support-Flags/Subentries, Registry-Merge-Heuristiken) und Regressionstests anpassen.
5. Mypy-Gesamtbereinigung: Redundant-Casts und Any-Rückgaben in den verbleibenden Modulen entfernen, Tasks/Decorators typisieren und JSONValue-Rückgaben normieren, bis `python -m mypy custom_components/pawcontrol` grün ist.
6. Abschlussläufe: `ruff format`, `ruff check`, `python -m mypy custom_components/pawcontrol`, `PYTHONPATH=$(pwd) pytest -q`, `python -m script.hassfest --integration-path custom_components/pawcontrol`, `python -m script.enforce_test_requirements`, `python -m scripts.enforce_shared_session_guard.py`; Ergebnisse dokumentieren.

## Offene Fehler und Verbesserungen

- Flows/Optionen: Placeholder-Freezes, JSONValue-Clamps und TypedDict-Keys in `config_flow.py`, `config_flow_dogs.py`, `config_flow_dashboard_extension.py`, `config_flow_external.py`, `config_flow_profile.py`, `options_flow.py`.
- Binary-Sensoren: `extra_state_attributes`-Overrides an Basissignatur anpassen (`binary_sensor.py`), JSONMutableMapping sicherstellen.
- JSONValue/Guards: `missing_sensors.py` (Date/Real-Union), `optimized_entity_base.py` (Mapping-Casts), Quiet-Hours-Parser-Tests und hassfest-Shim gegen neue Manifest/Translation-Regeln aktualisieren.
- Registry-/Flow-Stubs: FlowResult-/ConfigEntryState-/Support-Flag-/Subentry-Updates und Registry-Merge-Heuristiken regelmäßig mit HA-Release-Notes abgleichen; Tests in den Factory-/Flow-Stubs erweitern.
- Mypy-Restschulden: Redundant-Casts/Any-Rückgaben/fehlende Typ-Parameter in `compat.py`, `resilience.py`, `utils.py`, `telemetry.py`, `feeding_manager.py`, `notifications.py`, `services.py`, `repairs.py`, `coordinator.py`, `data_manager.py`, `options_flow.py`, `binary_sensor.py`, `missing_sensors.py`, `config_flow*`, `text.py`; Tasks/Callables/ConfigEntry-Typen parametrieren und JSONValue-Rückgaben vereinheitlichen.
