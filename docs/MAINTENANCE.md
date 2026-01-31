# PawControl Maintenance & Support Guide (EN)

This guide defines the routine maintenance and support workflows for the
PawControl Home Assistant integration. It complements the user-facing
troubleshooting guide and the diagnostics playbook.

## Scope & goals

- Keep the integration aligned with Home Assistant developer requirements.
- Provide a repeatable support workflow for incidents and user-reported issues.
- Maintain release hygiene so changelog entries, diagnostics, and docs stay in
  sync.

## Diagnostics workflow

Use this workflow whenever an issue report is missing data or needs validation.

1. **Confirm environment details**
   - Home Assistant version and installation type.
   - PawControl integration version and install path (HACS/manual).
   - Device/endpoint details (network, USB, or cloud).
2. **Reproduce or narrow scope**
   - Recreate the issue on a minimal configuration.
   - Verify whether the problem is profile-, device-, or platform-specific.
3. **Collect diagnostics**
   - Follow the dedicated diagnostics playbook: [`docs/diagnostics.md`](diagnostics.md).
   - Request logs around the failure window.
   - Ask for a Home Assistant config check if core services are affected.
4. **Capture supporting evidence**
   - Screenshots of UI errors or automations.
   - Service call payloads from **Developer Tools → Services**.
   - Related automation YAML snippets (redacted as needed).
5. **Document findings**
   - Summarize root cause, reproduction steps, and any temporary mitigations.
   - Link diagnostics artifacts to the issue thread.

## Issue triage workflow

Use this checklist for every new issue or discussion thread.

1. **Classify the report**
   - Bug, feature request, documentation, or question.
   - Determine whether it impacts setup, runtime behavior, or services.
2. **Verify required data**
   - Diagnostics export.
   - Logs with timestamps.
   - Version matrix (Home Assistant + integration).
3. **Prioritize and label**
   - Severity (blocking, regression, enhancement, low priority).
   - Component area (config flow, coordinator, services, diagnostics, UI).
4. **Reproduce & confirm**
   - Reproduce locally or in a clean Home Assistant instance if possible.
   - Confirm if the issue is already covered in [`docs/troubleshooting.md`](troubleshooting.md).
5. **Close the loop**
   - Update documentation if the resolution adds new guidance.
   - Add regression tests when behavior changes.
   - Note any follow-up tasks for the next release.

## Release routine

Follow this routine for every release or hotfix.

1. **Update documentation & release notes**
   - Log changes in `CHANGELOG.md` and `RELEASE_NOTES.md`.
   - Ensure user-facing guides reflect new behavior or requirements.
2. **Run validation & QA checks**
   - `ruff format`
   - `ruff check`
   - `pytest -q`
   - `python -m scripts.enforce_test_requirements`
   - `mypy custom_components/pawcontrol`
   - `python -m scripts.hassfest --integration-path custom_components/pawcontrol`
3. **Confirm diagnostics & repairs**
   - Validate diagnostics payload changes using the diagnostics guide.
   - Ensure repairs and error surfaces are documented.
4. **Sync contributor guides**
   - When contributor instructions change, run
     `python -m scripts.sync_contributor_guides`.
5. **Tag & publish**
   - Tag the release and verify that documentation links resolve correctly.

## Support escalation & follow-up

- Escalate blocking issues (setup failures, data loss) immediately and track
  them with high priority.
- For performance issues, capture coordinator timing, update intervals, and
  system health diagnostics.
- Close issues only after confirming the fix on the latest version or providing
  a documented workaround.

## Related references

- Diagnostics playbook: [`diagnostics.md`](diagnostics.md)
- Troubleshooting guide: [`troubleshooting.md`](troubleshooting.md)
- Setup & installation: [`setup_installation_guide.md`](setup_installation_guide.md)
- Quality scale evidence: [`compliance_gap_analysis.md`](compliance_gap_analysis.md)
