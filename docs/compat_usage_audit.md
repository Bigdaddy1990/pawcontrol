# Compat usage audit

## Scope

Search target: `custom_components/pawcontrol/` for `compat.` references (module-qualified
usage of `custom_components.pawcontrol.compat`). The goal is to confirm whether runtime
modules still rely on the compatibility shims now that the integration targets Home
Assistant 2025.9.0+.

## Findings

* **No runtime `compat.` usages remain** in `custom_components/pawcontrol/`. The only
  remaining compatibility shims are intentionally confined to `compat.py` itself and the
  test harness in `tests/helpers/homeassistant_test_stubs.py`.

## Outcome

The integration now consumes Home Assistant core types directly (config entries,
exceptions, and units) and no longer uses `compat.` in production code paths.
