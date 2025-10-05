# Compliance Review – 2025-03-03

This follow-up review confirms that Paw Control is still targeting the **Bronze**
tier. Several Bronze requirements remain unfinished, and higher-tier evidence is
not yet in place.

## Highlights
- **Quality evidence** – Manifest, README, changelog, and release notes now call out the Bronze posture and reference the gaps documented in `custom_components/pawcontrol/quality_scale.yaml`.
- **Service documentation** – Feeding services are covered; garden and weather documentation is in progress with outstanding TODOs called out.
- **Coverage status** – CI runs `pytest -q`, but many suites fail without full Home Assistant dependencies. Coverage enforcement is paused.
- **Lifecycle hooks** – `async_remove_config_entry_device` exists, yet we still need regression tests to ensure active dogs are protected and device cleanup is documented.
- **Sustainment** – `docs/MAINTENANCE.md` now tracks the interim cadence focused on closing Bronze gaps.

## References
- `custom_components/pawcontrol/quality_scale.yaml`
- `docs/QUALITY_CHECKLIST.md`
- `docs/compliance_gap_analysis.md`
- `docs/MAINTENANCE.md`

Next review: Once the outstanding Bronze tasks (service docs, runtime data coverage, uninstall guidance, Home Assistant test harness) are complete.
