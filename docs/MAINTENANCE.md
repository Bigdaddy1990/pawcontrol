# PawControl Maintenance Guide

This guide tracks the work required to keep PawControl honest about its
**Bronze** quality-scale declaration. Until we complete the outstanding tasks,
the focus is on stabilising the integration, documenting missing behaviour, and
building confidence in the automated tests.

## Weekly
- Triage GitHub issues and confirm reproduction steps.
- Capture notes about undocumented services so they can be added to `services.yaml`.
- Run `pytest -q` locally to monitor which suites still fail without Home Assistant.

## Monthly
- Audit the config flow against the outstanding discovery/reconfigure/reauth requirements.
- Review runtime data usage across platforms and plan follow-up tests.
- Draft uninstall/device-cleanup instructions once the removal hook is verified.

## Quarterly
- Review `custom_components/pawcontrol/quality_scale.yaml` and `docs/QUALITY_CHECKLIST.md` to update statuses and highlight new gaps.
- Sync release communications (README, RELEASE_NOTES.md) with the current quality posture.
- Prepare the branding artefacts needed for eventual HACS submission.
