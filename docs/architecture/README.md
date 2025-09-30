# PawControl Architecture Overview

This directory captures the architectural foundations that guide the PawControl
integration. It is intentionally lightweight and focused on the deliverables
requested for the *Architektur & Fehlerkultur* milestone.

## Structure

| Document | Purpose |
| --- | --- |
| [`manager_structure.md`](manager_structure.md) | Describes the manager layer, runtime orchestration, and data flows. |
| [`error_catalog.md`](error_catalog.md) | Defines the canonical error catalogue and escalation playbook. |
| [`adr/`](adr/) | Architecture Decision Records (#001 – #005) covering the maintainability roadmap. |

## Quality Gates

- **Code Climate Maintainability ≥ 90 %** – enforced by keeping coordinator
  logic modular and shifting responsibilities into testable helpers.
- **Coordinator implementation < 400 lines** – achieved via
  `DogConfigRegistry`, `CoordinatorMetrics`, and the dedicated
  `CoordinatorRuntime` that owns concurrency, resilience, and adaptive polling
  mechanics.
- **Error Culture** – errors map to the catalogue, enabling unified reporting
  across diagnostics, repairs, and the resilience layer.

Each ADR contains validation and monitoring hooks that ensure the target
metrics stay actionable over time.
