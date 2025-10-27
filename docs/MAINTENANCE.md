# PawControl Maintenance Guide

This guide tracks the work required to sustain PawControl's **Platinum** quality-scale declaration. The focus is on keeping evidence synchronised, refreshing telemetry baselines, and ensuring the automation, documentation, and translation suites remain healthy.

## Weekly
- Triage GitHub issues and confirm reproduction steps.
- Review diagnostics exports for new fields and update `docs/diagnostik.md` plus tests as needed.
- Run `pytest -q` locally to confirm suites uphold the coverage floor and Home Assistant fixtures remain compatible.

## Monthly
- Audit the config and options flows against discovery/reconfigure/reauth requirements and adjust translations when strings change.
- Review runtime data usage across platforms, ensuring new entities continue to rely on the coordinator runtime managers.
- Validate removal hooks by running the device removal tests and confirming README/portal guidance remains accurate.

## Quarterly
- Review `custom_components/pawcontrol/quality_scale.yaml` and `docs/QUALITY_CHECKLIST.md` to update statuses and highlight new findings.
- Sync release communications (README, `CHANGELOG.md`, `RELEASE_NOTES.md`) with the current quality posture and testing artefacts.
- Revalidate branding assets against Home Assistant requirements and refresh the HACS submission metadata if templates change.

## Annual
- Re-run the full documentation portal audit, including screenshots, to ensure evidence remains accessible to reviewers.
- Evaluate new Home Assistant quality-scale rules and update the checklist and development plan accordingly.
