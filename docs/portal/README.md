# PawControl Documentation Portal

Dieses Portal bündelt die wichtigsten Einstiegsdokumente für Entwicklerinnen
und Maintainer der PawControl-Integration. Ziel ist es, den Onboarding-Prozess
zu beschleunigen und offene Compliance-Aufgaben transparent zu halten.

## Navigationsmatrix

| Schwerpunkt | Zweck | Primäre Ressourcen |
| --- | --- | --- |
| Architektur & Module | Überblick über Koordinator, Manager-Schichten und Plattformen | [Manager Structure](../architecture/manager_structure.md), [Coordinator Source](../../custom_components/pawcontrol/coordinator.py), [Module Adapters](../../custom_components/pawcontrol/module_adapters.py) |
| Automationen & Dashboards | Nutzung der generierten Skripte, Dashboards und Helfer | [Automation Guide](../implementation_guide.md), [Dashboard Quickstart](../setup_installation_guide.md#lovelace-dashboard), [Script Manager](../../custom_components/pawcontrol/script_manager.py) |
| Benachrichtigungen & Resilienz | Konfiguration von Notification-Kanälen, Webhooks und Fehlertoleranz | [Improvement Plan](../improvement-plan.md), [Resilience README](../resilience-README.md), [Async Dependency Audit](../async_dependency_audit.md) |
| Besucher & Wetter-Workflows | Dokumentierte Besucherprozesse und wettergesteuerte Automationen | [Produktionsdoku](../production_integration_documentation.md), [Weather Automation Guide](../weather_integration_examples.md) |
| Qualität & Tests | Richtlinien für Linting, Docstrings, Benchmarks und verfügbare Tests | [Compliance Gap Analysis](../compliance_gap_analysis.md), [Docstring Enforcement](../../scripts/enforce_docstring_baseline.py), [Performance Benchmarks](../performance_samples.md), [Test Pyramid](../testing/test_pyramid.md), [CI Workflows](../../.github/workflows/ci.yml) |

## Arbeitsablauf für neue Beiträge

1. **Codebasis verstehen** – lies das Architekturkapitel, um die Aufteilung in
   Koordinator, Manager und Plattformadapter zu verstehen.
2. **Docstrings & Typen respektieren** – der Ruff-basierte Guard schlägt an,
   sobald neue Funktionen ohne Docstring eingecheckt werden (`python
   scripts/enforce_docstring_baseline.py`).
3. **Sitzungsmanagement prüfen** – HTTP-Helfer müssen die von Home Assistant
   verwaltete aiohttp-Session über `ensure_shared_client_session` nutzen; der
   Guard `python scripts/enforce_shared_session_guard.py` blockiert direkte
   `ClientSession()`-Instanzen – selbst wenn sie über aliasierte Importe oder
   verschachtelte `aiohttp.client`-Zugriffe erzeugt werden – entdeckt zusätzliche
   Pakete automatisch über `_discover_package_roots` und nutzt die
   konfigurierbaren Glob-Muster in
   `scripts/shared_session_guard_roots.toml` für nicht paketierte Helfer wie
   `services/`-Ordner.【F:scripts/enforce_shared_session_guard.py†L1-L188】【F:scripts/shared_session_guard_roots.toml†L1-L9】【F:tests/tooling/test_enforce_shared_session_guard.py†L1-L110】
4. **Tests lokal ausführen** – Unit-Tests fokussieren sich auf pure Python
   Module (`pytest tests/unit`). Komponenten-Tests benötigen ein Home
   Assistant-Test-Environment und werden daher optional geführt.
5. **Dokumentation anpassen** – Änderungen an Features oder Konfigurationswegen
   müssen in `info.md`, im Installationsguide und gegebenenfalls in den
   Automationskapiteln gespiegelt werden.

## Aktueller Qualitätsstatus

- **Docstrings** – vollständig erfüllt; die Baseline bleibt Teil von
  Pre-Commit-Hooks.
- **Async-Disziplin** – Synchronous Bibliotheken sind dokumentiert, kritische
  Stellen (GPX, Dashboard-Dateien, Notfall-Ernährungsrechner) laufen über
  `_offload_blocking` im Thread-Pool und werden mit Laufzeit-Logs profiliert.
  Zusätzlich erfassen Koordinator und Datenmanager `perf_counter`-Messwerte für
  Statistiken (~1.66 ms) und Besuchsmodus (~0.67 ms); die Benchmarks sind im
  Async-Audit verlinkt und per Tests abgesichert.【F:custom_components/pawcontrol/coordinator.py†L360-L420】【F:custom_components/pawcontrol/coordinator_support.py†L160-L213】【F:custom_components/pawcontrol/data_manager.py†L360-L450】【F:docs/async_dependency_audit.md†L1-L120】【F:docs/performance_samples.md†L1-L27】【F:generated/perf_samples/latest.json†L1-L17】【F:tests/unit/test_data_manager.py†L1-L118】
- **Tests** – Die globalen Fixtures stellen mit `session_factory` sicher, dass
  alle HTTP-Einstiegspunkte denselben aiohttp-Doppel nutzen; Unit-Tests laufen
  dadurch konsistent auch ohne Home Assistant Core.【F:tests/conftest.py†L195-L242】
- **CI & Coverage** – Unit-Tests laufen ohne Home Assistant; die GitHub-Actions-
  Jobs für `ci` und `coverage` erzwingen ≥95 % Coverage und laden Reports hoch.
- **Compliance** – Hassfest, Pre-Commit und Coverage-Gates laufen bei jedem
  Push/PR automatisch. Offene Punkte (z. B. verbleibende Runtime-Timeouts)
  sind im `compliance_gap_analysis` dokumentiert.

Das Portal wird regelmäßig aktualisiert, sobald neue Manager, Plattformen oder
Qualitätschecks hinzukommen. Bitte verlinke neue Dokumente hier, damit der
Einstieg konsistent bleibt.
