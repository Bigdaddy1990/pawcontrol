# Stability-Backlog für Coverage-Blocker

Dieses Backlog ist **separat** von Coverage-Tickets zu führen und wird immer vor
neuen Coverage-Gap-Arbeiten abgearbeitet, sobald Blocker den Hauptlauf
(`pytest` mit Coverage) beeinflussen.

## Verbindliche Triage-Reihenfolge

1. **Fokuslauf stabilisieren** (schnell reproduzierbare Teilmenge, die den
   Hauptfehler isoliert).
2. **Blocker beheben** (Syntaxfehler, harte Assertions/Import-Abbrüche,
   flaky/instabile Pfade), bis der Hauptlauf wieder zuverlässig startet.
3. **Erst danach** die **Top-3-Coverage-Gaps** bearbeiten (gemäß
   `docs/coverage_gap_priorisierung.md`).

## Gate 0 (verbindlich vor jedem Coverage-Paket)

- Ein neues Coverage-Paket darf **nicht** gestartet werden, solange mindestens
  ein Eintrag mit Hauptlauf-Effekt den Status **Offen** trägt.
- Gate-Check vor Paketstart:
  1. Tabelle „Aktuelle Blocker“ prüfen.
  2. Sicherstellen, dass alle Blocker mit Hauptlauf-Effekt auf **Erledigt**
     stehen.
  3. Erst dann Paketarbeit gemäß
     `docs/coverage_hotspot_backlog.md` (Paket 1 → 11, ohne Überspringen)
     beginnen.

## Aktuelle Blocker (Coverage-abbrechend)

| ID | Kategorie | Reproduktion (Testpfad + Befehl) | Ist-Verhalten | Erwartetes Verhalten | Status |
|---|---|---|---|---|---|
| STAB-001 | Import-/Abhängigkeits-Blocker (Hauptlauf) | `pytest -q -o addopts='' tests/unit/test_walk_schemas.py` | Collection-Abbruch mit `ModuleNotFoundError: No module named 'voluptuous'`. | Testdatei wird gesammelt und ausgeführt; bei Fehlern ausschließlich testbezogene Assertion-Fails statt Import-Abbruch. | Erledigt |
| STAB-002 | Import-/Abhängigkeits-Blocker (Hauptlauf) | `pytest -q -o addopts='' tests/unit/test_weather_manager_data.py` | Collection-Abbruch mit `ModuleNotFoundError: No module named 'aiohttp'` in `custom_components/pawcontrol/module_adapters.py`. | Modulimporte sind im Testlauf verfügbar; Testfall läuft bis zu fachlichen Assertions durch. | Erledigt |
| STAB-003 | Harte Collection-Abbrüche (Folgefehler) | `pytest -q -o addopts='' --collect-only` | Mehrere ImportError-Kaskaden (u. a. `CoordinatorModuleAdapters`/`WeatherModuleAdapter`) unterbrechen die Coverage-Pipeline mit >100 Collection-Fehlern. | Collection läuft stabil durch; verbleibende Probleme erscheinen als isolierte, reproduzierbare Test-Fails. | Erledigt |

## Parallelisierungs-Notizen pro Blocker

- Jeder Blocker-Ticket-Beschreibung muss enthalten:
  - exakter Pytest-Befehl,
  - betroffene Testdatei,
  - erwartetes Verhalten,
  - minimaler Fixumfang (Dependency, Import-Pfad, Test-Fix).
- Blocker dürfen parallel bearbeitet werden, wenn sich Pfade nicht überlappen.
- Coverage-Tickets bleiben pausiert, bis alle `Offen`-Blocker mit Hauptlauf-Effekt geschlossen sind.
