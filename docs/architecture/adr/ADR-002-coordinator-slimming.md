# ADR 002: Slim Coordinator via Registry & Metrics Helpers

## Status
Accepted – 2025-03-03

## Context

The previous coordinator mixed configuration validation, runtime metrics,
and update orchestration in one class. This led to duplicated validation logic
across tests and made it hard to reason about success rates or cache health.

## Decision

- Introduce `DogConfigRegistry` to normalise entry data, compute update
  intervals, and provide helper methods such as `enabled_modules` and
  `empty_payload`.
- Introduce `CoordinatorMetrics` to encapsulate update counters, success rate
  calculations, and the serialization used by diagnostics/system_health.
- Keep `PawControlCoordinator` focused on orchestrating async refreshes by
  delegating to these helpers. Runtime-specific logic (adaptive polling,
  resilience execution, entity budget analytics) is implemented in
  `coordinator_runtime.py` to maintain readability.

## Consequences

- Coordinator implementation shrinks to 321 lines while remaining readable.
- Tests can assert behaviour by manipulating helper instances instead of
  modifying private coordinator attributes.
- Metrics serialisation is consistent across diagnostics, system health, and
  documentation.
- Registry changes are isolated, simplifying future config migrations.
