# ADR 005: Maintainability Targets & Monitoring

## Status
Accepted – 2025-03-03

## Context

Stakeholders requested a Code Climate maintainability score above 90 % and a
hard cap of 400 lines for the coordinator. Without explicit governance these
targets risk regressing over time.

## Decision

- Track coordinator length via `wc -l` checks in review (documented in the
  release checklist) and keep helper logic in separate modules.
- Surface maintainability drivers in documentation so future contributors know
  why the split exists (`coordinator_support.py`, ADRs, error catalog).
- Update diagnostics to expose success rate and cache hit rate, enabling SLO
  dashboards to detect degradations early.

## Consequences

- Contributors have clear guidance on where to place new logic.
- The coordinator file currently sits at 353 lines, providing headroom for
  minor tweaks without violating the target.
- Documentation and ADRs record the rationale, making it part of onboarding.
