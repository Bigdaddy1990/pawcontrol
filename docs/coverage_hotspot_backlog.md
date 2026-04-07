# Coverage Hotspot Backlog (Initial)

Quelle: `docs/coverage_gap_prioritized.md` Snapshot vom **2026-04-06**.

## 1) Initiale Hotspot-Liste

| Rang | Modul | Missing Lines | Priorität |
|---:|---|---:|---|
| 1 | `custom_components/pawcontrol/services.py` | 1229 | Kritisch |
| 2 | `custom_components/pawcontrol/feeding_manager.py` | 1187 | Kritisch |
| 3 | `custom_components/pawcontrol/sensor.py` | 1076 | Kritisch |
| 4 | `custom_components/pawcontrol/helpers.py` | 928 | Mittel |
| 5 | `custom_components/pawcontrol/data_manager.py` | 899 | Kritisch |
| 6 | `custom_components/pawcontrol/script_manager.py` | 886 | Kritisch |
| 7 | `custom_components/pawcontrol/walk_manager.py` | 804 | Mittel |
| 8 | `custom_components/pawcontrol/dashboard_cards.py` | 798 | Niedrig |
| 9 | `custom_components/pawcontrol/notifications.py` | 794 | Mittel |
| 10 | `custom_components/pawcontrol/dashboard_generator.py` | 757 | Niedrig |

## 2) Arbeitspakete (2–4 Stunden pro Paket)

### Ticket COV-01 (3h)
- Scope: `services.py` Exception-/Abort-Pfade (`except`, `return False`).
- Ziel: +25 bis +40 abgedeckte Zeilen in Service-Fehlerpfaden.

### Ticket COV-02 (4h)
- Scope: `data_manager.py` Persistenz- und Export-Fehlerpfade.
- Ziel: +30 bis +50 abgedeckte Zeilen inkl. negativer Pfade.

### Ticket COV-03 (3h)
- Scope: `feeding_manager.py` Input-Validierung und Recovery.
- Ziel: +25 bis +40 Zeilen, Fokus auf invalid payload handling.

### Ticket COV-04 (3h)
- Scope: `sensor.py` Guard-Konditionen und Berechnungskanten.
- Ziel: +20 bis +35 Zeilen in defensive branches.

### Ticket COV-05 (2h)
- Scope: `script_manager.py` manuelle Event-Orchestrierung.
- Ziel: +15 bis +30 Zeilen, v. a. Mapping-/Fallback-Pfade.

### Ticket COV-06 (2h)
- Scope: `helpers.py` Batch-/Decorator-Fehlerpfade.
- Ziel: +15 bis +25 Zeilen.

### Ticket COV-07 (2h)
- Scope: `notifications.py` Delivery-Recovery.
- Ziel: +15 bis +25 Zeilen.

## 3) Definition of Done (pro Ticket)

Ein Ticket ist nur **Done**, wenn alle Punkte erfüllt sind:

- [ ] Branch geschlossen (PR gemerged, Branch gelöscht).
- [ ] Tests grün (`pytest -q` + Coverage-Gates).
- [ ] Reviewer-Check bestanden (mindestens 1 Approval, keine offenen Changes).

## 4) Täglicher 10-Minuten-Checkpoint

Täglich (Mo–Fr), 10 Minuten, fixer Slot:

1. **Blocker** (max. 3 Minuten): Was blockiert das aktuelle Ticket?
2. **Coverage-Delta** (max. 4 Minuten): Welche Lücken wurden geschlossen?
3. **Next Top Gap** (max. 3 Minuten): Nächstes Paket aus der Hotspot-Liste ziehen.

Checkpoint-Artefakt pro Tag:
- Kurzer Kommentar im Tracking-Issue mit:
  - `done_today`
  - `blockers`
  - `next_top_gap`
