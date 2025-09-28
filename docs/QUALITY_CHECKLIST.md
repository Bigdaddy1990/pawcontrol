# Paw Control – Integration Quality Scale Checklist

This document maps our implementation to the **Integration Quality Scale**. As of the February 2025 review, the
integration only claims **Bronze** compliance while keeping the higher-tier items tracked for future work.

## Bronze (baseline expectations)
- [x] Maintainer declared in `manifest.json` (`codeowners`).
- [x] Config flow available with basic setup / unload.
- [x] Entities expose unique IDs and mark themselves unavailable on update failures.
- [x] User-facing strings are translated via `strings.json`.
- [x] Core services documented in `services.yaml`.
- [ ] Automated test coverage beyond smoke imports. (Bronze has no fixed bar but this remains a risk.)

## Silver (deferred)
- [ ] Services validated with rich error handling.
- [ ] `PARALLEL_UPDATES` tuned per platform.
- [ ] End-to-end tests ensuring runtime robustness.

## Gold & Platinum (deferred)
- [ ] Diagnostics with redaction validated by tests.
- [ ] Repair issues with guided flows.
- [ ] Device registry metadata confirmed via coverage tests.
- [ ] Brands assets submitted to `home-assistant/brands`.
- [ ] Test coverage ≥ 95% to unlock Platinum claims.

## Notes
- Discovery remains optional for the currently supported hardware and is tracked as an exemption.
- Reauthentication is not implemented because external services do not require credentials yet.

- [x] **GitHub Topics** gesetzt (z. B. `home-assistant`, `hacs`, `integration`) – verbessert Auffindbarkeit im HACS-Store.
