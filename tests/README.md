# PawControl Testing Infrastructure

The PawControl suite follows the documented test pyramid: fast unit helpers,
resilience-focused service checks, and optional Home Assistant integration
layers. This repository snapshot keeps the lightweight tiers available so
contributors can validate changes without the full HA runtime.

## 🎯 Quality Gates

- **Branch coverage ≥ 95 %** (currently 100 %) enforced via [`pytest.ini`](../pytest.ini).
- **Line coverage ≥ 95 %** (currently 100 %).
- **100 % PRs with test evidence** – copy the command output into the PR using
  the template from the [coverage playbook](../docs/testing/coverage_reporting.md#documenting-pr-evidence).

## 🚀 Running the suites

### Canonical coverage command

```bash
pytest --cov=custom_components.pawcontrol \
       --cov-branch \
       --cov-report=term-missing \
       --cov-report=xml
```

This is the same invocation executed in CI. It produces `coverage.xml` and an
`htmlcov/` directory for inspection.

### Fast feedback loop

```bash
pytest --maxfail=1 --disable-warnings --cov-branch
```

Use this during development for immediate failures while still generating branch
metrics.

## 📁 Directory layout

```
tests/
├── coverage/
│   └── test_resilience_core.py    # Service-level coverage of the resilience toolkit
├── integration/                   # Home Assistant integration tests (skipped without HA)
├── components/                    # Component-specific fixtures and helpers
├── hassfest/                      # Manifest validation harness
├── script/                        # CLI scripts used in CI pipelines
├── unit/                          # Placeholder for pure unit helpers (see docs/testing/test_pyramid.md)
├── conftest.py                    # Shared fixtures and skip logic
└── test_placeholder.py            # Ensures pytest discovery on minimal checkouts
```

## ✅ Expectations for new tests

1. Prefer the **unit** or **coverage** layers for new logic to keep the pyramid
   balanced.
2. Mirror the patterns in `test_resilience_core.py` for async orchestration and
   branch coverage scenarios.
3. Update the coverage badge in the README if the percentage changes.
4. Attach the pytest output to the PR to prove the ≥95 % branch gate.

For additional context, consult the [test pyramid](../docs/testing/test_pyramid.md)
and the [coverage reporting playbook](../docs/testing/coverage_reporting.md).
