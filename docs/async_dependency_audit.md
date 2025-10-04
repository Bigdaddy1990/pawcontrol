# PawControl Async Dependency Audit

This note captures the current state of potentially blocking dependencies and
the mitigations in place to keep the Home Assistant event loop responsive.

## Third-party libraries with synchronous behaviour

- **Async GPX builder** – the walk manager now renders GPX exports through a
  dedicated XML serializer that escapes metadata inline with Python's
  standard-library helpers, eliminating the previous `defusedxml` dependency
  from the runtime manifest and top-level requirements.【F:custom_components/pawcontrol/walk_manager.py†L1395-L1560】【F:custom_components/pawcontrol/manifest.json†L1-L60】【F:requirements.txt†L1-L3】
- **Synchronous dependency cleanup** – unused libraries (`requests`,
  `urllib3`, `pyserial`, `cryptography`, `uv`, `aiodhcpwatcher`,
  `aiodiscover`, `aiousbwatcher`, `asyncio-mqtt`, `Jinja2`) have been pruned
  from the top-level requirements so contributors do not assume synchronous
  helpers are available. Runtime requirements now mirror the manifest and test
  requirements list only the tooling needed for CI.【F:requirements.txt†L1-L3】【F:requirements_test.txt†L1-L6】【F:custom_components/pawcontrol/manifest.json†L47-L54】
- **`voluptuous`** – imported throughout the configuration and services stack;
  validation work remains synchronous but operations are short-lived and bound
  to user input handlers, matching Home Assistant expectations.【F:custom_components/pawcontrol/config_flow.py†L1-L200】【F:custom_components/pawcontrol/services.py†L1-L420】

## File and CPU-heavy routines

- Dashboard file management already runs through `asyncio.to_thread`, keeping
  template rendering and cleanup off the main loop.【F:custom_components/pawcontrol/dashboard_generator.py†L300-L360】【F:custom_components/pawcontrol/dashboard_generator.py†L520-L705】
- Utility retries transparently move synchronous callables into threads so
  helpers can wrap existing code without blocking callers.【F:custom_components/pawcontrol/utils.py†L900-L970】

## Long-running background tasks

- Emergency feeding restores schedule state via `asyncio.create_task` coupled
  with hour- and day-scale `asyncio.sleep`, which keeps the loop free while
  delayed reversion work happens in the background. The restoration routine and
  calorie recalculation now run through `_offload_blocking`, a helper that moves
  the health-metric crunching into threads and logs the wall-clock runtime for
  validation. Use these timings to spot regressions during reviews.【F:custom_components/pawcontrol/feeding_manager.py†L658-L742】【F:custom_components/pawcontrol/feeding_manager.py†L2184-L2339】
- Door, garden, and notification managers also rely on
  `asyncio.create_task`/`asyncio.sleep` orchestration for long-lived timers so
  the event loop remains responsive even for multi-minute cadence work.【F:custom_components/pawcontrol/door_sensor_manager.py†L456-L520】【F:custom_components/pawcontrol/garden_manager.py†L320-L370】【F:custom_components/pawcontrol/notifications.py†L1066-L1130】
- Additional managers (health, weather) primarily perform in-memory analytics.
  No extra synchronous libraries were detected, but deeper benchmarking is
  recommended before advertising real-time guarantees.

## Profiling benchmarks

- Runtime statistics aggregation is now wrapped in precise `perf_counter`
  measurements. The coordinator records each sample, exposes rolling averages,
  and logs the duration for audit purposes. Unit coverage asserts the
  aggregation finishes in under 5 ms with the test fixture, providing a
  repeatable guardrail for future optimisations.【F:custom_components/pawcontrol/coordinator.py†L399-L411】【F:custom_components/pawcontrol/coordinator_support.py†L162-L212】【F:tests/unit/test_coordinator.py†L9-L104】 The latest harness run captured
  samples between 1.64 ms and 1.67 ms, published in
  [`generated/perf_samples/latest.json`](../generated/perf_samples/latest.json)
  and summarised in the performance appendix.【F:docs/performance_samples.md†L15-L34】【F:generated/perf_samples/latest.json†L1-L33】
- Visitor-mode persistence runs through the same profiling path. The data
  manager captures raw timings, stores rolling averages in its metrics payload,
  and forwards the sample to the coordinator via `set_metrics_sink` so the
  shared `CoordinatorMetrics` object records the same timings for diagnostics.
  Targeted unit tests confirm the workflow completes within 3 ms using the stub
  storage layer and that the coordinator metrics receive the sample, ensuring
  regression noise appears in CI rather than at runtime.【F:custom_components/pawcontrol/data_manager.py†L922-L959】【F:custom_components/pawcontrol/coordinator.py†L226-L259】【F:custom_components/pawcontrol/coordinator_support.py†L190-L212】【F:tests/unit/test_data_manager.py†L1-L118】 The committed benchmark snapshot shows visitor
  persistence averaging roughly 0.67 ms, keeping headroom for additional
  validation logic.【F:docs/performance_samples.md†L23-L29】【F:generated/perf_samples/latest.json†L1-L33】
- Emergency feeding restorations now emit profiling samples via
  `_offload_blocking`. The worker-thread instrumentation records the rebuild and
  calorie recalculation cost so the async audit can verify the offloaded path
  remains within budget. The latest run shows the restoration routine completing
  in about 33 ms per invocation, confirming the heavy lifting stays off the
  event loop while still being observable in CI artefacts.【F:custom_components/pawcontrol/feeding_manager.py†L700-L718】【F:custom_components/pawcontrol/feeding_manager.py†L2153-L2291】【F:docs/performance_samples.md†L23-L29】【F:generated/perf_samples/latest.json†L1-L33】
- Daily reset maintenance now records per-run timings directly from the service
  helper, exposing an average runtime of ~12 ms in the profiling snapshot. The
  metrics bucket tracks successes, failures, and the last error string so audit
  reviewers can correlate anomalies with log lines. The committed data is tagged
  with the `ci` environment so reviewers can tell it was produced by the
  profiling harness.【F:custom_components/pawcontrol/services.py†L2827-L2884】【F:docs/performance_samples.md†L15-L34】【F:generated/perf_samples/latest.json†L1-L33】
- Hourly analytics collectors piggy-back on the coordinator maintenance task.
  Each execution stores its duration (≈4.3 ms) and failure tally inside the
  shared runtime data object, keeping the event-loop overhead visible even when
  multiple helpers contribute cached insights. Recordings from a supervised
  installation should be appended under a distinct `environment` label so the CI
  and real-world distributions can be compared during reviews.【F:custom_components/pawcontrol/coordinator_tasks.py†L1-L160】【F:docs/performance_samples.md†L15-L34】【F:generated/perf_samples/latest.json†L1-L33】

## Recommended follow-ups

1. Extend the profiling coverage to long-running schedulers (e.g., statistics
   recalculation and visitor cleanup tasks) so real-world Home Assistant traces
   can be compared with the CI benchmarks captured above.
2. Capture and publish a supervised-environment telemetry snapshot (for example
   `generated/perf_samples/supervised.json`) and cross-link it from the testing
   checklist once the smoke test completes, enabling Platinum reviewers to
   verify the analytics collector metrics under production-like load.
3. Extend this audit whenever new third-party libraries are added so the
   Platinum “async dependency” claim remains verifiable.
