# Coverage quality gates

This document defines the mandatory coverage gates for PawControl contributions.
CI fails when any gate is violated.

## Minimum goals

- **Total line coverage**: **>= 75%** across `custom_components/pawcontrol`.
- **Critical module minimums**:
  - `custom_components/pawcontrol/coordinator.py`: **>= 80%**
  - `custom_components/pawcontrol/config_flow.py`: **>= 80%**
  - `custom_components/pawcontrol/services.py`: **>= 75%**
  - `custom_components/pawcontrol/data_manager.py`: **>= 75%**

These thresholds are enforced by:

- `pyproject.toml` (`[tool.coverage.report].fail_under`), and
- `python -m scripts.enforce_coverage_gates --coverage-xml coverage.xml` in CI.

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

Any new coverage exclusion must be documented explicitly in the pull request
description with:

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
2. Run `pytest` with coverage locally.
3. Run `python -m scripts.enforce_coverage_gates --coverage-xml coverage.xml`.
4. If a critical module falls below its gate, add module-focused tests before
   opening a pull request.
