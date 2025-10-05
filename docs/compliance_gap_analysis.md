# Paw Control Quality Compliance Report

Paw Control currently declares the **Bronze** tier of the Home Assistant
Integration Quality Scale. The goal of this report is to list the evidence we
already have and the gaps that block us from higher tiers.

## 1. Bronze status snapshot
- ⚠️ **Manifest & metadata** – `manifest.json` now reports `quality_scale: "bronze"`, but diagnostics and release notes still need to be updated to match.
- ⚠️ **Service documentation** – Feeding services are described, yet newer garden, weather, notification, and diagnostics helpers lack entries in `custom_components/pawcontrol/services.yaml`.
- ⚠️ **Runtime data** – Runtime helpers exist, though many platforms bypass them and there is no regression coverage.
- ⚠️ **Removal docs** – INSTALLATION.md includes basic uninstall steps, but we still need guidance on pruning devices once the removal hook is finalised.
- ⚠️ **Testing** – The Home Assistant–dependent suites fail in the current environment, so we do not have passing setup/unload or coordinator tests.

## 2. Silver and Gold blockers
- ❌ **Coverage enforcement** – Coverage jobs are disabled until the test harness is restored.
- ❌ **Dynamic/stale devices** – `async_remove_config_entry_device` is only partially implemented and untested.
- ❌ **Diagnostics & repairs** – Diagnostics return placeholder data and no repair flows are registered.
- ❌ **Brand assets** – Branding work has not started; the upstream submission package is empty.
- ❌ **Adaptive polling** – The adaptive polling helper is under active development and the existing tests are failing.

## 3. Next actions
- Finish documenting every registered service and add examples to `custom_components/pawcontrol/services.yaml`.
- Stabilise the Home Assistant test stubs so the component and integration suites can run without the full core package.
- Add regression tests for runtime data usage, device removal, diagnostics redaction, and repairs workflows before attempting Silver or Gold claims.
- Update public-facing docs (README, RELEASE_NOTES.md) once the above work is complete so the messaging stays honest.

Tracking this work in `custom_components/pawcontrol/quality_scale.yaml` keeps the manifest declaration grounded while we close the remaining gaps.
