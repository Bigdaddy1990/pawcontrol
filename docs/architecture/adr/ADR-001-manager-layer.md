# ADR 001: Adopt Dedicated Manager Layer

## Status
Accepted – 2025-03-03

## Context

The integration has grown to include feeding, walk analytics, weather health,
geofencing, and garden automation. Previous iterations pushed logic directly
into the `PawControlCoordinator`, resulting in a 700+ line class that hindered
testability and obscured ownership boundaries.

## Decision

Introduce a dedicated manager layer responsible for domain logic. Each manager
owns its own async APIs and exposes typed methods that the coordinator consumes
through `CoordinatorModuleAdapters`. Runtime managers are attached during entry
setup via `attach_runtime_managers`.

## Consequences

- Coordinators shrink dramatically (<400 lines) and focus on orchestration.
- Managers can be unit-tested independently of Home Assistant's runtime.
- New features slot into existing managers without bloating the coordinator.
- Requires lightweight adapter glue to harmonise caching and resilience.
