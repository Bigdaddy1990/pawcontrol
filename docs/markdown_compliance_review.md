# Markdown Compliance Review

This document summarises how the repository’s Markdown meets the Home Assistant
custom integration documentation guidelines and the internal instructions from
`.github/copilot-instructions.md`, `.gemini/styleguide.md`, and
`.claude/agents/`.

## Alignment with assistant instruction sets
- **Copilot** – The rewritten `.github/copilot-instructions.md` now documents the
  Python toolchain, architecture touchpoints, and review checklist expected for
  PawControl contributors, replacing the outdated frontend guidance.【F:.github/copilot-instructions.md†L1-L92】
- **Gemini** – `.gemini/styleguide.md` explicitly references the Copilot guide to
  keep both assistants synchronized on Platinum standards and repository
  structure.【F:.gemini/styleguide.md†L1-L26】
- **Claude** – `.claude/agents/copilot-instructions.md` now identifies PawControl
  as a Home Assistant custom integration and points Claude back to the shared
  style guides for consistency.【F:.claude/agents/copilot-instructions.md†L1-L8】

## Scope of review
- **Core user documentation** – `README.md`, `info.md`, `INSTALLATION.md`, and
the documentation portal entry point (`docs/README.md`).
- **Compliance artefacts** – `docs/compliance_gap_analysis.md`,
  `docs/QUALITY_CHECKLIST.md`, and `dev.md`.
- **Release support** – `CHANGELOG.md`, `RELEASE_NOTES.md`, and
  `docs/production_integration_documentation.md`.

## Current coverage status
- `README.md` now reflects the Platinum uplift effort, documents system
  requirements for Home Assistant 2025.1+/Python 3.13+, and links to options,
  diagnostics, and removal workflows so reviewers can verify the integration’s
  support expectations.【F:README.md†L1-L199】【F:README.md†L320-L372】
- `info.md` continues to provide the HACS-facing summary of modules, async
  design, and installation/removal steps, satisfying the repository instruction
  to keep helper generation and shared-session enforcement documented for
  auditors.【F:info.md†L1-L120】
- `docs/README.md` organises onboarding, architecture, testing, compliance, and
  supplementary guides, giving Home Assistant reviewers a single index for
  deeper evidence.【F:docs/README.md†L1-L35】
- `docs/compliance_gap_analysis.md` records Platinum rule alignment, linking
  every rule to the sustaining documentation or test suite and logging any
  future findings so the audit trail remains complete.【F:docs/compliance_gap_analysis.md†L1-L120】
- `dev.md` captures the latest failing tests, improvement backlog, and
  remediation plan, fulfilling the Gemini instruction to keep contributors aware
  of Ruff and pytest expectations.【F:dev.md†L1-L40】

## Required corrections to satisfy Home Assistant reviewers
- Keep `CHANGELOG.md` and `RELEASE_NOTES.md` summarising the Platinum uplift and refresh them when new sustainment work lands so documentation stays aligned with the manifest and badges.
- Ensure README (`Quality Scale`) and documentation portal badges continue to advertise the Platinum posture during submissions.【F:README.md†L1-L120】【F:docs/portal/README.md†L1-L40】
- Expand the troubleshooting/removal guidance in `INSTALLATION.md` with explicit
  steps for helper cleanup and `async_remove_config_entry_device` behaviour once
  the implementation work in `dev.md` is finished.
- When new modules or services are introduced, ensure `info.md`, README, and the
  documentation portal receive simultaneous updates so the Markdown remains in
  lockstep with runtime capabilities.

## Review cadence
- Re-run this Markdown audit before each release and whenever Home Assistant
  updates its custom integration requirements.
- Keep citations in documentation sections (for example in README and
  `info.md`) pointing at authoritative evidence files/tests so reviewers can
  confirm claims quickly.

Maintaining this checklist alongside the compliance report ensures the
integration’s documentation stays ready for Home Assistant Platinum review.
