# Development plan

## Aktueller Baustellenüberblick

- MyPy ist weiterhin rot (7 Dateien, 280+ Befunde): Schwerpunkte in `options_flow.py`/`config_flow.py` (JSONValue-Clamps, TypedDict-Literal-Keys, EntityFactory-Inputs) sowie JSONPayload-Kanten in `diagnostics.py`. Die Literal-Key-Aufräumarbeiten für Geofence/Notification-Optionen sind abgeschlossen.
- Entity-Attribute-Overrides verletzen die Basissignatur (`extra_state_attributes` erwartet `dict[str, JSONValue]`), aktuell offen in den Binary-Sensoren und Buttons. Device-Tracker ist bereits auf JSONMutableMapping angeglichen.
- Runtime-/Telemetry-Snapshots landen noch als komplexe Objekte in den Diagnostics-Exports (`DataStatisticsPayload`, `RuntimeStore*`, Rejection-Metrics-Merges) und blockieren JSONValue/Hassfest-Konformität. Redaction-Keys für Koordinaten sind erweitert, Serialisierung bleibt offen.
- Device-Tracker- und Missing-Sensor-Payloads übergeben noch `object`-/`date`-Mischformen statt JSONValue-konformer Daten; damit schlagen die Offline-Stubs und Typenchecks fehl.

## Plan zur Fertigstellung

1. Entity-Attribute-Signaturen glätten: `binary_sensor.py` und `button.py` auf die `PawControlEntity.extra_state_attributes`-Rückgabe (JSONMutableMapping) ziehen und gemeinsame Attribute-Helper nutzen, damit HA und Tests die gleichen Keys sehen.
2. Flows/Optionen typfest machen: In `config_flow.py`/`options_flow.py` Placeholder- und TypedDict-Keys auf String-Literals klemmen, JSONValue- und Mapping-Casts herstellen (Dog-Configs, Door-Sensor-Overrides, EntityFactory-Aufrufe) und `dict(...)`-Kopien durch definierte Mapper ersetzen. Geofence- und Notification-Schlüssel sind bereits auf Literal-Konstanten umgestellt, übrige Optionen folgen.
3. Diagnostics-Export härten: Telemetrie-, Rejection- und Setup-Flag-Payloads in `diagnostics.py` auf JSONMapping serialisieren (`DataStatisticsPayload`, `RuntimeStore*`, `CoordinatorResilienceDiagnostics`, Service-Guard-Metriken) und `merge_rejection_metric_values` an die `RejectionMetricsSource`-Schnittstelle anschließen.
4. Tracker-/Missing-Sensor-Payloads korrigieren: `device_tracker.py` auf `GPSRouteSnapshot`/`datetime`-konforme Payloads biegen und `missing_sensors.py` auf ISO-Strings bzw. JSONValue normalisieren.
5. Abschlussprüfungen: `ruff format`, `ruff check`, `python -m mypy custom_components/pawcontrol`, `PYTHONPATH=$(pwd) pytest -q`, `python -m script.hassfest --integration-path custom_components/pawcontrol`, `python -m script.enforce_test_requirements`.

## Offene Fehler und Verbesserungen

- 280+ MyPy-Befunde konzentriert auf `options_flow.py` (83), `config_flow.py` (86), `binary_sensor.py` (75), `diagnostics.py` (28), `device_tracker.py` (2), `button.py` (5), `missing_sensors.py` (1); Hauptursachen: JSONValue/TypedDict-Mismatches, falsche Placeholder-Literal-Keys, EntityFactory-Argumente. Geofence/Notification-Literals sind bereits abgeschlossen, weitere Optionsbereiche offen.
- `extra_state_attributes` in den Binary-Sensoren und Buttons ignorieren die Basissignatur (`dict[str, JSONValue]`) und müssen auf JSONMutableMapping/Helper zurückgeführt werden.
- Diagnostics-Payloads enthalten noch komplexe Snapshots (RuntimeStore/Resilience/Service-Guards), die nicht als JSONValue serialisiert werden.
- Device-Tracker-Route/last_seen und Missing-Sensor-Diagnosen liegen nicht im JSONValue-Schema und verletzen die Stubs.
- Nach Typbereinigung Hassfest-/Guard-Skripte und ggf. Doc-Updates für Diagnostics/Setup-Flags einplanen.
