# Coverage quality gates

This document defines the mandatory coverage gates for PawControl contributions.
CI fails when any gate is violated.

## Minimum goals

- **Total line coverage**: **>= 85%** in CI.
- **Critical module branch coverage target**: **100%** for
  `custom_components/pawcontrol/coordinator.py`,
  `custom_components/pawcontrol/config_flow.py`,
  `custom_components/pawcontrol/services.py`, and
  `custom_components/pawcontrol/data_manager.py`.
- If 100% branch coverage is not currently feasible, the module must be listed
  with a rationale and a floor value in
  `docs/coverage_critical_module_exceptions.json`.

These thresholds are enforced by:

- `pyproject.toml` (`[tool.coverage.report].fail_under`), and
- `python -m scripts.enforce_coverage_gates --coverage-xml coverage.xml` in CI.


## Test-Authoring-Checkliste (verbindlich)

- **Genau ein Verhalten pro Testfall**: Ein Test prüft genau eine fachliche Aussage
  (kein Multi-Assertion-Mix über mehrere Verhaltenszwecke).
- **Given/When/Then-Struktur**: Testfälle müssen klar in Setup (Given), Ausführung
  (When) und Erwartung (Then) gegliedert sein (durch Kommentare, Hilfsfunktionen
  oder Testnamen).
- **Mocking nur an Integrationsgrenzen**: Mocks/Stubs sind nur für IO, externe APIs
  und Home-Assistant-Servicegrenzen zulässig; interne Businesslogik wird nicht
  gemockt, sondern mit echten Domänenobjekten getestet.
- **Regressionstest-Pflicht pro Fix**: Jede behobene Kante (Bug/Edge Case) muss im
  selben Ticket unmittelbar durch einen Regressionstest abgesichert werden.

## Allowed exclusions (`# pragma: no cover`)

Coverage exclusions are allowed only for these categories, and each excluded line
must include a reason comment.

1. **Import/version fallbacks**
   - Example: optional Home Assistant import guards that execute only in reduced
     local test environments.
2. **Defensive logging/cleanup paths**
   - Example: emergency cleanup code reachable only through non-deterministic
     runtime failures.
3. **Type-checking-only branches**
   - Example: `if TYPE_CHECKING:` branches used exclusively for static analysis.

If an exclusion does not match one of these categories, add test coverage instead
of introducing a new `no cover` path.

## Exception documentation requirements

Any new coverage exclusion or critical-module branch exception must be
documented explicitly in the pull request description with:

1. **File + line reference** (for example `custom_components/pawcontrol/foo.py:123`)
2. **Category** (one of the allowed categories above)
3. **Justification** explaining why deterministic automated tests cannot cover
   that path safely/reliably
4. **Mitigation plan** (for example follow-up integration test, observability
   signal, or runtime guard)

Undocumented exclusions are treated as gate failures during review and must be
resolved before merge.

## Contributor workflow

1. Add or update tests for every functional behavior change.
2. Ensure every new/updated test follows one-behavior-only and explicit
   Given/When/Then structure.
3. Keep mocks at integration boundaries only (IO/API/HA service boundaries);
   avoid mocking internal business logic.
4. Add a regression test in the same ticket for every fixed bug or edge case.
5. Run `pytest` with coverage locally.
6. Run `python -m scripts.enforce_coverage_gates --coverage-xml coverage.xml`.
7. If a critical module is below 100% branch coverage, either add
   module-focused tests or update
   `docs/coverage_critical_module_exceptions.json` with a justified floor.
8. Run `python -m scripts.enforce_test_todo_policy` to verify there are no
   remaining TODO markers in test files.
