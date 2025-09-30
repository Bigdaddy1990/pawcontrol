# ADR 004: Establish Error Catalog & Culture

## Status
Accepted – 2025-03-03

## Context

Historically, errors were logged ad-hoc with inconsistent language and no clear
escalation path. Support teams could not easily correlate log entries with user
facing guidance.

## Decision

Create `docs/architecture/error_catalog.md` as the single source of truth for
error codes, severity, and remediation steps. Update coordinator logging to map
exceptions to these codes and surface them through diagnostics.

## Consequences

- Documentation, diagnostics, and support share the same vocabulary.
- Automated tooling can watch for repeated codes (e.g. `NET-001`) and open
  GitHub issues or repairs with actionable context.
- Engineers must register new error modes in the catalog as part of code review.
