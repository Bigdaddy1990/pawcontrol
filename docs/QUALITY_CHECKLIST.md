# Paw Control – Integration Quality Scale Checklist

Paw Control meets the **Platinum** tier of the Home Assistant integration quality scale. This checklist records the evidence used to maintain that status so contributors can keep the manifest, documentation, and diagnostics aligned.

## Bronze
- [x] Maintainer declared in `manifest.json` and `CODEOWNERS`.
- [x] Config flow covers user, discovery, reconfigure, options, and reauth paths with regression coverage.
- [x] Runtime data helpers back every platform via coordinator runtime managers.
- [x] Service documentation spans feeding, garden, weather, notifications, diagnostics, and resilience workflows.
- [x] Setup/unload behaviour verified by component tests using Home Assistant stubs.
- [x] Removal guidance documented in README, `docs/MAINTENANCE.md`, and the documentation portal.

## Silver
- [x] Coverage ≥95 % enforced in CI/PR gate via `pytest --cov` and `pyproject.toml`.
- [x] Config flow suites cover discovery, reconfigure, reauth, abort, and error handling scenarios.
- [x] Service schemas validated through `services.yaml` definitions and handler tests.
- [x] Platform tests assert coordinator throttling and `PARALLEL_UPDATES` compliance.
- [x] Resilience tests validate coordinator retry/failure handling and diagnostics export.

## Gold
- [x] Diagnostics redact secrets and export anonymised telemetry with regression coverage.
- [x] Repairs flows emit actionable issues with matching tests.
- [x] Device registry lifecycle tests cover stale-device pruning (`async_remove_config_entry_device`).
- [x] Branding assets ship in `brands/pawcontrol/` and align with Home Assistant expectations.
- [x] Adaptive polling and performance strategy documented and validated via automated tests.

## Platinum
- [x] Test-before-setup/update/unload scenarios covered by component suites.
- [x] Dynamic device/entity lifecycle verified across reloads.
- [x] Coverage gates enforced in CI with artefacts tracked under `docs/testing/`.
- [x] Maintenance playbook defines recurring verification steps in `docs/MAINTENANCE.md`.
- [x] Localization suite prevents translation drift across `strings.json` and `translations/`.

## Sustaining Notes
- Update `custom_components/pawcontrol/quality_scale.yaml` alongside documentation and tests when behaviour changes.
- Audit evidence quarterly to ensure Platinum claims remain accurate; track findings in `dev.md` and the documentation portal.
