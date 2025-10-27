# Development plan

## Quality gate expectations
- Run `ruff check`, `pytest -q`, `mypy custom_components/pawcontrol`, and `python -m script.hassfest --integration-path custom_components/pawcontrol` before opening a pull request so Platinum-level guardrails stay enforced.【F:.github/copilot-instructions.md†L10-L33】
- Target Python 3.13+ features and reuse PawControl helpers (coordinators, managers, and typed constants) to keep runtime data on the typed surface.【F:.github/copilot-instructions.md†L34-L94】

## Documentation sync
- `RELEASE_NOTES.md` und `CHANGELOG.md` verlinken die Diagnostik- und Wartungsleitfäden, damit Release-Kommunikation und Sustainment-Planung dieselben Nachschlagewerke nutzen ([docs/diagnostik.md](docs/diagnostik.md), [docs/MAINTENANCE.md](docs/MAINTENANCE.md)).【F:RELEASE_NOTES.md†L14-L24】【F:CHANGELOG.md†L114-L140】

## Latest tooling snapshot
- ✅ `ruff check`【bfdc87†L1-L3】
- ✅ `pytest -q`【50c9da†L1-L6】
- ✅ `mypy custom_components/pawcontrol`【08fbce†L1-L2】
- ✅ `python -m script.hassfest --integration-path custom_components/pawcontrol`【350092†L1】

## Fehleranalyse
- **Home-Assistant-Teststubs modernisiert:** Die Template-Helfer nutzen jetzt synchrone und asynchrone `NativeEnvironment`-Instanzen, Events enthalten Kontext- und Herkunftsdaten und der Service-Stub akzeptiert das `blocking`-Flag. Damit laufen Blueprint- und Service-Tests wieder gegen eine API, die der aktuellen Home-Assistant-Version entspricht.【F:tests/helpers/homeassistant_test_stubs.py†L1288-L1356】【F:tests/helpers/homeassistant_test_stubs.py†L297-L333】
- **Manuelle Resilience-Ereignisse angereichert:** `PawControlScriptManager` speichert Listener-Quellen als `ManualEventSourceList`, reichert Ereignisse mit Gründen, Kontext und Zählwerten an und stellt die Historie für Diagnostik sowie Snapshots bereit. Laufzeitdaten werden beim Unload in `hass.data[DOMAIN]` persistiert, sodass Re-Initialisierungen keine Metadaten verlieren.【F:custom_components/pawcontrol/script_manager.py†L1210-L1303】【F:custom_components/pawcontrol/script_manager.py†L2030-L2083】【F:custom_components/pawcontrol/script_manager.py†L2475-L2485】【F:custom_components/pawcontrol/__init__.py†L1539-L1552】
- **Benchmark-Stabilität verbessert:** `EntityFactory` kann `_ensure_min_runtime` auf Wunsch per `PAWCONTROL_ENABLE_ENTITY_FACTORY_BENCHMARKS=1` aktivieren und ruft den Guard dann aus allen Hotpaths auf. Dadurch bleiben Performance-Metriken reproduzierbar, ohne dass Prioritätsberechnungen in Tests ausfransen oder produktive Installationen blockiert werden.【F:custom_components/pawcontrol/entity_factory.py†L36-L37】【F:custom_components/pawcontrol/entity_factory.py†L658-L767】【F:custom_components/pawcontrol/entity_factory.py†L768-L779】
- **Typdefinitionen erweitert:** Die Manual-Event-TypedDicts erlauben jetzt Sequenzen und optionale Quellinformationen, wodurch MyPy und Telemetrie-Ausgaben dieselbe Form erwarten. `Sequence` wird explizit importiert, um Python 3.13-Forward-Kompatibilität sicherzustellen.【F:custom_components/pawcontrol/types.py†L20-L39】【F:custom_components/pawcontrol/types.py†L1986-L2012】
- **Konstanten bereinigt:** Überflüssige Update-Intervall-Duplikate wurden entfernt, sodass `const.py` wieder die einzige Quelle für Integrationsschwellen darstellt. Das vereinfacht spätere Retention-Anpassungen.【F:custom_components/pawcontrol/const.py†L20-L60】【F:custom_components/pawcontrol/const.py†L495-L586】

## Verbesserungsplan
1. **Blueprint-Testhelfer zentralisieren:** Die neuen Manual-Event-Metadaten sollen in einem gemeinsamen Testutility landen, damit Komponenten- und E2E-Blueprint-Suiten dieselben Listener-Mocks und Assertions verwenden.【F:tests/components/pawcontrol/test_resilience_blueprint_e2e.py†L24-L200】
2. **Automation-/Template-Stubs erweitern:** Ergänzende Fixtures für `_enforce_polling_limits`, `_validate_gps_interval` und `async_block_till_done` halten die Test-Suite lauffähig, wenn Home Assistant weitere Validierungen einschleust.【F:tests/helpers/homeassistant_test_stubs.py†L1992-L2054】
3. **Coverage-Retention konfigurabel machen:** `script.publish_coverage` erhält einen Schalter für maximale Aufbewahrungsdauer, inklusive Tests und Dokumentation, damit Support-Teams Speicherbudgets einfacher einhalten.【F:script/publish_coverage.py†L21-L210】
