# Paw Control – Integration Quality Scale Checklist

This document tracks Paw Control's progress toward the **Integration Quality Scale** requirements. The
integration is still working toward Platinum compliance and several Bronze and Silver items remain open, so the
checklist below highlights both the completed work and the gaps that still need attention.

## Bronze (baseline expectations)
- [ ] Runtime data stored via `ConfigEntry.runtime_data` instead of bespoke helpers.
- [x] Maintainer declared in `manifest.json` (`codeowners`).
- [x] Config flow available with basic setup / unload.
- [x] Entities expose unique IDs and mark themselves unavailable on update failures.
- [x] User-facing strings are translated via `strings.json`.
- [x] Core services documented in `services.yaml`.
- [ ] Automated test coverage with full platform regression suites in `tests/components/pawcontrol` (current total ~1 %).
- [ ] Removal / uninstall instructions published alongside installation docs.

## Silver
- [ ] Test coverage ≥ 95 % across the integration.
- [ ] Config flow regression suite exercises discovery, dashboard, module validation, reconfigure, and reauth paths.
- [x] Services validated with rich error handling and typed schemas (`services.py`).
- [x] `PARALLEL_UPDATES = 0` on all coordinator-backed platforms to allow unlimited parallel refreshes.
- [x] End-to-end style runtime simulations covered by scaling tests.

## Gold & Platinum
- [x] Diagnostics with redaction validated by dedicated fixtures and tests.
- [x] Repair issues surfaced with guided flows (`repairs.py`).
- [x] Device registry metadata confirmed via regression coverage.
- [ ] Brands assets submitted to `home-assistant/brands`.
- [ ] Polling cadence documented and enforced to stay under the Platinum <15-minute idle target.

## Notes
- Discovery remains optional for the currently supported hardware and is tracked as an exemption in the quality scale configuration.
- Reauthentication is handled via `async_step_reauth` and `async_step_reauth_confirm`, allowing credential refresh without removing the entry.

- [x] **GitHub Topics** gesetzt (z. B. `home-assistant`, `hacs`, `integration`) – verbessert Auffindbarkeit im HACS-Store.
