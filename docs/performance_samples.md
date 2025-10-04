# PawControl Performance Benchmarks

This appendix captures recent measurements for the latency-sensitive code
paths highlighted in the async dependency audit: statistics aggregation inside
the coordinator, visitor-mode persistence in the data manager, and the
emergency feeding restoration routine that now runs off the event loop. Values
are taken from the instrumentation added in
[coordinator.py](../custom_components/pawcontrol/coordinator.py),
[data_manager.py](../custom_components/pawcontrol/data_manager.py), and
[feeding_manager.py](../custom_components/pawcontrol/feeding_manager.py) and
are refreshed whenever the profiling harness is executed.

## Latest benchmark snapshot

The file [`generated/perf_samples/latest.json`](../generated/perf_samples/latest.json)
records the most recent sample set gathered from the CI profiling harness. Each
entry is annotated with an `environment` field so future supervised runs can be
added next to the existing data for direct comparison. When a supervised smoke
test is executed, publish a companion snapshot (for example
`generated/perf_samples/supervised.json`) and update the testing checklist with a
link to the artefact.

| Workflow | Environment | Samples (ms) | Average (ms) | Source |
| --- | --- | --- | --- | --- |
| Statistics aggregation | `ci` | `[1.64, 1.66, 1.65, 1.67]` | `1.66` | [`coordinator.py`](../custom_components/pawcontrol/coordinator.py#L399-L411) |
| Visitor persistence | `ci` | `[0.66, 0.68, 0.67, 0.66]` | `0.67` | [`data_manager.py`](../custom_components/pawcontrol/data_manager.py#L922-L959) |
| Emergency feeding restoration | `ci` | `[32.9, 33.1, 33.0, 32.8]` | `32.95` | [`feeding_manager.py`](../custom_components/pawcontrol/feeding_manager.py#L700-L718) |
| Daily reset scheduler | `ci` | `[11.8, 12.1, 11.9, 12.0]` | `11.95` | [`services.py`](../custom_components/pawcontrol/services.py#L2827-L2884) |
| Analytics collector maintenance | `ci` | `[4.2, 4.4, 4.3, 4.1]` | `4.25` | [`coordinator_tasks.py`](../custom_components/pawcontrol/coordinator_tasks.py#L1-L160) |

The instrumentation logs each measurement via the coordinator metrics sink, and
the async audit links back to these entries for transparency. When performance
work is carried out, update the JSON snapshot and keep this table in sync so the
Platinum “async dependency” claim remains verifiable.
