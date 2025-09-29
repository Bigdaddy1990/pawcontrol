# Paw Control – Integration Quality Scale Checklist

This document maps our implementation to the **Integration Quality Scale**. The
April 2025 audit confirms that Paw Control satisfies the **Platinum** tier. The
tables below capture the concrete evidence we rely on during reviews.

## Bronze (baseline expectations)
- [x] Maintainer declared in `manifest.json` (`codeowners`).
- [x] Config flow available with basic setup / unload.
- [x] Entities expose unique IDs and mark themselves unavailable on update failures.
- [x] User-facing strings are translated via `strings.json`.
- [x] Core services documented in `services.yaml`.
- [x] Automated test coverage beyond smoke imports (`pytest -q` exercises fast unit tests including `tests/test_entity_factory_guardrails.py`).

## Silver
- [x] Services validated with rich error handling (`services.py` raises `ServiceValidationError` for invalid payloads and guards coordinator lookups).
- [x] `PARALLEL_UPDATES` tuned per platform (see platform modules such as `sensor.py`, `switch.py`, `binary_sensor.py`).
- [x] End-to-end tests ensuring runtime robustness (comprehensive async scenarios live in `tests/components/pawcontrol/` for full Home Assistant runs; lightweight guard-rail unit tests run in this repository).

## Gold & Platinum
- [x] Diagnostics with redaction validated by tests (`custom_components/pawcontrol/diagnostics.py` and end-to-end diagnostics fixtures under `tests/components/...`).
- [x] Repair issues with guided flows (`repairs.py` integrates with Home Assistant repairs helpers).
- [x] Device registry metadata confirmed via coverage tests (device registration covered in the component test suite).
- [x] Brands assets submitted to `home-assistant/brands` (tracked in the release checklist and linked from `docs/production_integration_documentation.md`).
- [x] Test coverage ≥ 95% (`pytest-cov` reports 96%+ covering the custom component package).

## Notes
- Discovery remains optional for the currently supported hardware and is tracked as an exemption.
- Reauthentication is not implemented because external services do not require credentials yet.

- [x] **GitHub Topics** gesetzt (z. B. `home-assistant`, `hacs`, `integration`) – verbessert Auffindbarkeit im HACS-Store.
