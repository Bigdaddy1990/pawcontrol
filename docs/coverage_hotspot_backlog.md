# Coverage Hotspot Backlog (Top 15 aus coverage.xml)

## Snapshot-Metadaten

- **Snapshot-Datum (UTC):** 2026-04-07T02:33:24Z
- **Commit-SHA:** `1ef76b717cf547e6e242bf068c1a6e50e3a982e2`
- **Quelle:** `coverage.xml` (Cobertura XML)

## Extraktion (ohne manuelle Schätzung)

Die Liste wurde direkt aus `coverage.xml` nach `missing lines` berechnet (Anzahl `<line>` mit `hits="0"` je `<class>`), absteigend sortiert.

## Top-15 Module nach Missing Lines

| Rang | Modul | Missing Lines | Gate-Modul |
|---:|---|---:|---|
| 1 | `custom_components/pawcontrol/types.py` | 1866 | Nein |
| 2 | `custom_components/pawcontrol/services.py` | 1647 | **Ja** |
| 3 | `custom_components/pawcontrol/data_manager.py` | 1364 | **Ja** |
| 4 | `custom_components/pawcontrol/feeding_manager.py` | 1360 | Nein |
| 5 | `custom_components/pawcontrol/script_manager.py` | 1060 | Nein |
| 6 | `custom_components/pawcontrol/repairs.py` | 933 | Nein |
| 7 | `custom_components/pawcontrol/telemetry.py` | 917 | Nein |
| 8 | `custom_components/pawcontrol/walk_manager.py` | 804 | Nein |
| 9 | `custom_components/pawcontrol/notifications.py` | 794 | Nein |
| 10 | `custom_components/pawcontrol/coordinator_tasks.py` | 712 | Nein |
| 11 | `custom_components/pawcontrol/weather_manager.py` | 632 | Nein |
| 12 | `custom_components/pawcontrol/entity_factory.py` | 552 | Nein |
| 13 | `custom_components/pawcontrol/door_sensor_manager.py` | 529 | Nein |
| 14 | `custom_components/pawcontrol/gps_manager.py` | 456 | Nein |
| 15 | `custom_components/pawcontrol/validation.py` | 424 | Nein |

## Gate-Definition

Als Gate-Module gelten: `coordinator.py`, `config_flow.py`, `services.py`, `data_manager.py`.

In den Top-15 dieses Snapshots enthaltene Gate-Module:

- `services.py`
- `data_manager.py`
