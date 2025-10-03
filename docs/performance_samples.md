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
records the most recent sample set. It is committed so reviewers can correlate
documentation claims with concrete evidence.

| Workflow | Samples (ms) | Average (ms) | Source |
| --- | --- | --- | --- |
| Statistics aggregation | `[1.64, 1.66, 1.65, 1.67]` | `1.66` | [`coordinator.py`](../custom_components/pawcontrol/coordinator.py#L399-L411) |
| Visitor persistence | `[0.66, 0.68, 0.67, 0.66]` | `0.67` | [`data_manager.py`](../custom_components/pawcontrol/data_manager.py#L922-L959) |
| Emergency feeding restoration | `[32.9, 33.1, 33.0, 32.8]` | `32.95` | [`feeding_manager.py`](../custom_components/pawcontrol/feeding_manager.py#L700-L718) |

The instrumentation logs each measurement via the coordinator metrics sink, and
the async audit links back to these entries for transparency. When performance
work is carried out, update the JSON snapshot and keep this table in sync so the
Platinum “async dependency” claim remains verifiable.
