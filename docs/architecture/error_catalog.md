# Error Catalog

The error catalog unifies messaging across the coordinator, managers, and
observability surface (diagnostics, repairs, `system_health`). All raised errors
map to a code in the table below, ensuring consistent escalation rules.

| Code | Exception | Origin | Severity | Coordinator Handling | Resolution Path |
| --- | --- | --- | --- | --- | --- |
| `CFG-001` | `ValidationError` | Configuration validation (`DogConfigRegistry`) | ⚠️ Warning | Skip dog, emit structured log entry, surface in diagnostics. | Prompt user to fix config UI or YAML; include offending key/value. |
| `AUTH-001` | `ConfigEntryAuthFailed` | Device/session auth | ❗ High | Abort refresh, raise to HA so re-auth flow triggers. | Refresh token via config flow; cross-reference quota usage. |
| `NET-001` | `NetworkError` | API client / adapter | ⚠️ Warning | Cache last good payload, increase retry jitter. | Check connectivity; escalate to repairs if recurring >3 cycles. |
| `GPS-001` | `GPSUnavailableError` | GPS manager | ℹ️ Info | Mark module `status=unavailable`, keep remaining modules healthy. | Provide troubleshooting hint (battery / permissions) via notification. |
| `RES-001` | `RetryExhaustedError` (wrapped) | ResilienceManager | ❗ High | Increment consecutive errors, open circuit breaker. | Auto-resets after stability window; manual reset available via diagnostics. |
| `SYS-001` | Unexpected exception | Any manager/adapter | ❗ High | Log with context, fall back to cached payload, increment metrics. | File issue with stack trace; cross-link to SLO dashboards. |

## Diagnostics & Monitoring Hooks

- `CoordinatorMetrics` tracks `failed_cycles`, `success_rate`, and
  `consecutive_errors`. These roll up into `get_update_statistics()` and
  `get_statistics()` for UI consumption.
- The resilience manager exposes `get_all_circuit_breakers()` so the repairs
  dashboard can show which subsystems are degraded.
- `get_security_scorecard()` surfaces adaptive polling drift and webhook
  posture in a single payload so diagnostics and portal tiles stay aligned with
  catalogue guidance.
- `error_catalog.md` acts as a reference for authoring new repair flows: each
  entry contains the messaging template, required telemetry, and the manager
  responsible for remediation.

## Error Culture Principles

1. **Visibility first** – log structured messages with correlation IDs before
   attempting retries.
2. **Graceful degradation** – modules failing do not cascade; cached data keeps
   entities stable.
3. **Actionable feedback** – every catalog entry links to a remediation path so
   users see a clear next step instead of raw stack traces.
