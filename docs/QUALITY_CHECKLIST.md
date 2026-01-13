# Quality checklist (PawControl)

This document mirrors the integration's Home Assistant quality-scale tracker and provides a quick human-readable checklist.
The authoritative source is `custom_components/pawcontrol/quality_scale.yaml`.

## Current target tier

- Declared tier: **platinum** (see `custom_components/pawcontrol/quality_scale.yaml`)

## Checklist

All rules are currently marked as **done** in `custom_components/pawcontrol/quality_scale.yaml`.  
If you change behavior that affects quality-scale compliance, update both `custom_components/pawcontrol/quality_scale.yaml` and this checklist.

### Evidence pointers

- CI / Quality gate: `.github/workflows/`
- Tests: `tests/` (unit tests, hassfest, translation validation)
- Translations: `custom_components/pawcontrol/translations/`
- Docs: `docs/`
- Lint / typing configuration: `pyproject.toml`, `.pre-commit-config.yaml`

## Notes

- Home Assistant quality scale is an internal guideline for integrations. For custom integrations, prefer wording like:
  “aligned with Platinum quality requirements”.
