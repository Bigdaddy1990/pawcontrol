# 🧪 PawControl Test Pyramid & Quality Gates

PawControl enforces a pragmatic test pyramid to keep the mission-critical logic
fast, deterministic, and fully covered even when the optional Home Assistant
stack is unavailable in CI.

## Pyramid Overview

```
        ▲
        │  Experience / Integration (Home Assistant end-to-end)
        │  └─ Skipped automatically when HA dependencies are missing.
        │
        │  Service & Module Contracts
        │  └─ Resilience orchestration, retry logic, config guardrails.
        │     Driven by async component-style tests with lightweight stubs.
        │
        │  Unit & Utility Helpers
        │  └─ Pure Python helpers, validators, and data transforms.
        └───────────────────────────────────────────────────────────────
```

- **Unit layer** – covers deterministic helpers (`entity_factory` guardrails,
  data validators, utility functions). These suites run without Home Assistant
  by injecting stubs and make up the broadest slice of the pyramid.
- **Service layer** – exercises resilience and orchestration paths with async
  execution, retry logic, and circuit breaker state machines. The new
  `tests/coverage/test_resilience_core.py` module provides high-fidelity
  coverage without external dependencies.
- **Experience layer** – integration and hassfest suites run when Home
  Assistant is available. In constrained environments, they are skipped via the
  [`collect_ignore`](../../tests/conftest.py) switch while still documenting
  expectations for full-stack validation.

## Coverage & Quality Gates

| Metric                    | Target | Current | Source |
|---------------------------|:------:|:-------:|--------|
| Branch coverage           | 99 %   | 99.55 % | `pytest --cov-branch` (see below)
| Coverage fail-under gate  | 99 %   | Enforced via `pyproject.toml`
| PR test evidence          | 100 %  | Required; PRs must include pytest run output

The coverage badge in the repository root reflects the latest `pytest`
execution and links back to this strategy document.

## Running the CI Suite Locally

```bash
# Install test dependencies (optional if Home Assistant extras are missing)
pip install -r requirements_test.txt

# Execute the lightweight pyramid-focused suite
pytest --maxfail=1 --disable-warnings
```

The command generates `coverage.xml` and `htmlcov/` for inspection. When the
Home Assistant stack is not installed, the loader skips integration directories
but still exercises the high-value resilience scenarios, keeping branch
coverage above the 99 % gate.

## Reporting Results in PRs

Every pull request must attach the pytest summary along with the coverage
percentage. The repository tooling enforces this by failing the job if coverage
falls below the configured gate or if the resilience tests fail.
