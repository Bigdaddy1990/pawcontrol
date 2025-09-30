# ADR 003: Standardise Resilience Patterns

## Status
Accepted – 2025-03-03

## Context

Multiple modules were implementing ad-hoc retry logic which conflicted with the
central `ResilienceManager`. Errors surfaced inconsistently (some modules raised
`UpdateFailed`, others swallowed exceptions) leading to poor observability.

## Decision

Use the shared `ResilienceManager.execute_with_resilience` entry point for all
dog refreshes. The coordinator supplies retry configuration (2 attempts with
exponential backoff) and names the circuit breaker per dog (`dog_data_<id>`).

## Consequences

- Circuit breaker statistics flow into diagnostics uniformly.
- Transient errors reuse consistent retry timings, improving predictability.
- Authentication failures bypass retries and bubble up immediately, preserving
  Home Assistant's re-auth prompts.
- Simplifies unit testing because resilience can be mocked at a single point.
