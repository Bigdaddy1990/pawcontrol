# Paw Control – Integration Quality Scale Checklist

Paw Control is still working toward the **Bronze** tier of the Home Assistant
integration quality scale. This checklist records the current status of each
requirement so contributors can see what remains before we can honestly claim
Silver, Gold, or Platinum.

## Bronze
- [x] Maintainer declared in `manifest.json` and `CODEOWNERS`.
- [ ] Config flow: Only the primary user path is implemented; discovery, reconfigure, and reauth steps remain TODO (`tests/components/pawcontrol/test_config_flow.py`).
- [ ] Runtime data: Helpers exist, but several platforms bypass them and no automated tests cover the access patterns.
- [ ] Service documentation: Garden, weather, notification, and diagnostics services still need entries in `custom_components/pawcontrol/services.yaml`.
- [ ] Setup/teardown testing: Integration setup/unload behaviour is not exercised in CI because the Home Assistant stubs are incomplete.
- [ ] Removal guidance: INSTALLATION.md needs explicit uninstall/device-cleanup steps and screenshots once the hook work lands.

## Silver
- [ ] Coverage ≥90 % in CI (`pytest --cov` is currently disabled because the suite fails without Home Assistant).
- [ ] Config flow suite for discovery, reconfigure, reauth, and abort scenarios.
- [ ] Service schema validation for garden/weather/GPS/diagnostics services.
- [ ] Platform tests confirming `PARALLEL_UPDATES` and coordinator throttling.
- [ ] Resilience tests verifying coordinator retry/failure handling.

## Gold
- [ ] Diagnostics that redact secrets with regression coverage.
- [ ] Repairs flow emitting actionable issues with accompanying tests.
- [ ] Device registry lifecycle tests covering stale-device pruning (`async_remove_config_entry_device`).
- [ ] Branding assets prepared and submitted to `home-assistant/brands`.
- [ ] Adaptive polling strategy documented and validated via automated tests.

## Platinum
- [ ] Test-before-setup/update/unload coverage.
- [ ] Dynamic device/entity lifecycle tests across reloads.
- [ ] Coverage gates enforced in CI with published artefacts.
- [ ] Maintenance playbook defining recurring verification steps.
- [ ] Localization suite preventing translation drift.

## Sustaining Notes
- Update `custom_components/pawcontrol/quality_scale.yaml` as work completes so the manifest declaration stays honest.
- Once Bronze is finished, draft a lightweight maintenance cadence before attempting Silver/Gold/Platinum again.
