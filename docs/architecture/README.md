# PawControl Architecture Overview

This directory captures the architectural foundations that guide the PawControl
integration. It is intentionally lightweight and focused on the deliverables
requested for the *Architektur & Fehlerkultur* milestone. A curated overview is
available via the [documentation portal](../portal/README.md).

## Structure

| Document | Purpose |
| --- | --- |
| [`manager_structure.md`](manager_structure.md) | Describes the manager layer, runtime orchestration, and data flows. |
| [`error_catalog.md`](error_catalog.md) | Defines the canonical error catalogue and escalation playbook. |
| [`adr/`](adr/) | Architecture Decision Records (#001 – #005) covering the maintainability roadmap. |

## Quality Gates

- **Code Climate Maintainability ≥ 90 %** – enforced by keeping coordinator
  logic modular and shifting responsibilities into testable helpers.
- **Coordinator implementation < 400 lines** – the orchestration file is now
  358 lines because `CoordinatorRuntime.execute_cycle` handles concurrency,
  resilience, and adaptive polling while `coordinator.py` focuses on glue
  logic and manager wiring.
- **Error Culture** – errors map to the catalogue, enabling unified reporting
  across diagnostics, repairs, and the resilience layer.

Each ADR contains validation and monitoring hooks that ensure the target
metrics stay actionable over time.
