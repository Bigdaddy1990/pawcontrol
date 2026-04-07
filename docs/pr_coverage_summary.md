# PR Coverage Summary (2026-04-07)

## Gate Run Status

- Full gate run executed (`ruff format`, `ruff check`, `pytest -q`, `python -m scripts.enforce_test_requirements`, `python -m scripts.enforce_coverage_gates --coverage-xml coverage.xml`, `mypy custom_components/pawcontrol`, `python -m scripts.hassfest --integration-path custom_components/pawcontrol`).
- `pytest -q` failed with collection/runtime assertion failures, so coverage gate cannot pass in current branch state.
- Total line coverage from `coverage.xml`: **14.25%** (required: **>= 85%**).
- Critical-module gate check failed because `coverage.xml` does not contain `custom_components/pawcontrol/config_flow.py` after interrupted run.

## Critical-module exceptions/floors

- Existing exceptions file `docs/coverage_critical_module_exceptions.json` already defines floors for all critical modules.
- No floor update was applied in this run because the gate failure is caused by missing/failed coverage generation, not by branch-floor drift.

## Delta by package (PR scope)

| Package | Current Coverage | Delta vs base | Notes |
|---|---:|---:|---|
| `custom_components.pawcontrol` | 14.16% | n/a | Base-branch coverage artifact not available in workspace. |
| `custom_components.pawcontrol.setup` | 18.64% | n/a | Base-branch coverage artifact not available in workspace. |
