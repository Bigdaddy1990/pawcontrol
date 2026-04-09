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
