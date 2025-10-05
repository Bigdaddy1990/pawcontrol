# PawControl Compliance Gap Analysis

This report lists the current deltas between the integration and the documented engineering guardrails or Platinum quality scale commitments.

## 1. Outstanding Bronze/Silver gaps
- **Bronze – runtime-data:** Runtime data is stored via bespoke helpers under `hass.data[DOMAIN]` instead of the prescribed `ConfigEntry.runtime_data` attribute.
- **Silver – test-coverage:** Coverage instrumentation now targets the entire integration, but the suite still exercises only a handful of helpers so overall coverage remains ~1 %, well short of the 95 % goal.
- **Silver – config-flow-test-coverage:** The config flow tests focus on a narrow set of user, import, and reauth paths; discovery rejection, dashboard configuration, and reconfigure edge cases still lack regression coverage.
- **Bronze – docs-removal-instructions:** The primary setup guide omits removal/uninstall guidance, leaving users without teardown instructions.
- **Bronze – brands:** The repository still lacks the `brands/` submission package required for the official Home Assistant repository.

### Closed checklist items
- **Config flow subcheck:** `data_description` helper text now ships in the user step translations, giving clear setup context inside the UI.
- **Binary sensor localization:** Binary sensor entities set `_attr_has_entity_name = True` and expose translation keys, and regression tests assert the localization coverage for the core PawControl sensors.

## 2. Quality scale verification
- `quality_scale.yaml` matches the implementation status and cites evidence for every Platinum rule. Keep the file and supporting documents (for example `docs/QUALITY_CHECKLIST.md`) in sync when features evolve.【F:custom_components/pawcontrol/quality_scale.yaml†L1-L61】【F:docs/QUALITY_CHECKLIST.md†L1-L27】
- Reauth, diagnostics, and discovery flows referenced in the checklist are implemented in the config flow and supporting managers, providing reviewers with concrete proof during audits.【F:custom_components/pawcontrol/config_flow.py†L1-L690】【F:custom_components/pawcontrol/diagnostics.py†L34-L460】

## 3. Coordinator lifecycle contract
- `async_setup_entry` now awaits the public `async_prepare_entry()` helper on the coordinator, eliminating the dependency on the private `_async_setup` coroutine and aligning with Home Assistant architecture guidelines.【F:custom_components/pawcontrol/__init__.py†L360-L407】【F:custom_components/pawcontrol/coordinator.py†L248-L284】
- Unit tests patch and assert the new public hook, so regressions that attempt to call private internals will fail fast during CI.【F:tests/components/pawcontrol/test_init.py†L120-L210】

## 4. Async dependency posture
- GPX exports are produced with an inline serializer on the event loop, and `manifest.json` only declares async-friendly dependencies, satisfying the Platinum async-dependency rule without thread offloading.【F:custom_components/pawcontrol/walk_manager.py†L1388-L1558】【F:custom_components/pawcontrol/manifest.json†L1-L60】
- The async dependency audit highlights remaining watchpoints (long-running schedulers, CPU-bound calculations) and confirms no synchronous libraries remain in the runtime requirements.【F:docs/async_dependency_audit.md†L1-L120】

## 5. Documentation upkeep
- The docs portal now ships a Platinum traceability matrix so reviewers can map each guardrail to the supporting code, tests, or documentation at a glance.【F:docs/portal/README.md†L1-L86】【F:docs/portal/traceability_matrix.md†L1-L120】
- Benchmark appendices capture the recorded timings for daily resets and analytics collectors, extending the async audit evidence with concrete numbers for long-running helpers.【F:docs/async_dependency_audit.md†L1-L160】【F:docs/performance_samples.md†L15-L34】【F:generated/perf_samples/latest.json†L1-L33】

## 6. Action items to exceed Platinum
1. Schedule an end-to-end Home Assistant smoke test run and document the results in the testing checklist, including a direct link to the captured telemetry artefact so Platinum reviewers can trace the evidence without leaving the portal.
2. Capture metrics from a supervised installation to validate the new analytics collector telemetry under real workloads and publish them alongside the existing CI samples for side-by-side comparison.
