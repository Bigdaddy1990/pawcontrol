# Paw Control – Integration Quality Scale Checklist

This document maps our implementation to the **Integration Quality Scale**. Following the March 2025 audit the
integration now meets the expectations for **Platinum** compliance, with the historical checklist retained below
for transparency.

## Bronze (baseline expectations)
- [x] Maintainer declared in `manifest.json` (`codeowners`).
- [x] Config flow available with basic setup / unload.
- [x] Entities expose unique IDs and mark themselves unavailable on update failures.
- [x] User-facing strings are translated via `strings.json`.
- [x] Core services documented in `services.yaml`.
- [x] Automated test coverage with full platform regression suites in `tests/components/pawcontrol`.

## Silver
- [x] Services validated with rich error handling and typed schemas (`services.py`).
- [x] `PARALLEL_UPDATES` tuned per platform with coordinator-backed scheduling.
- [x] End-to-end style runtime simulations covered by scaling tests.

## Gold & Platinum
- [x] Diagnostics with redaction validated by dedicated fixtures and tests.
- [x] Repair issues surfaced with guided flows (`repairs.py`).
- [x] Device registry metadata confirmed via regression coverage.
- [x] Brands assets submitted to `home-assistant/brands`.
- [x] Test coverage ≥ 95% validated through CI reporting and scaling benchmarks.【F:.github/workflows/ci.yml†L1-L120】【F:.github/workflows/coverage.yml†L1-L60】【F:pyproject.toml†L46-L66】

## Notes
- Discovery remains optional for the currently supported hardware and is tracked as an exemption in the quality scale configuration.
- Reauthentication is handled via `async_step_reauth` and `async_step_reauth_confirm`, allowing credential refresh without removing the entry.

- [x] **GitHub Topics** gesetzt (z. B. `home-assistant`, `hacs`, `integration`) – verbessert Auffindbarkeit im HACS-Store.
