# Development plan

## Quality gate expectations
- Run `ruff check`, `pytest -q`, `mypy custom_components/pawcontrol`, and `python -m script.hassfest --integration-path custom_components/pawcontrol` before opening a pull request so Platinum-level guardrails stay enforced.【F:.github/copilot-instructions.md†L10-L28】
- Target Python 3.13+ features and reuse PawControl helpers (coordinators, managers, and typed constants) to keep runtime data on the typed surface.【F:.github/copilot-instructions.md†L29-L94】

## Latest tooling snapshot
- ✅ `ruff check` – passes without lint findings.【c60abc†L1-L2】
- ✅ `pytest -q` – 906 tests (one skipped) succeed in 37.52 seconds.【11bdc2†L1-L6】
- ✅ `python -m script.hassfest --integration-path custom_components/pawcontrol` – manifest and translation validation succeed.【393618†L1-L1】
- ❌ `mypy custom_components/pawcontrol` – 278 legacy strict-typing errors persist across 37 files (see excerpt).【2721df†L1-L120】

## Recent improvements
- Shared `CONF_DOOR_SENSOR_SETTINGS` across helpers so stored overrides no longer rely on bespoke keys.【F:custom_components/pawcontrol/const.py†L129-L142】
- Normalised door sensor overrides through `_coerce_bool` and companion helpers before persisting them, ensuring reloads retain clamped values without restarting monitors unnecessarily.【F:custom_components/pawcontrol/door_sensor_manager.py†L40-L347】【F:custom_components/pawcontrol/types.py†L1921-L1995】
- Expanded regression coverage to assert alias handling, numeric toggle coercion, persistence, removals, and no-op updates for the door sensor manager workflow.【F:tests/unit/test_door_sensor_manager.py†L23-L310】

## Error backlog
1. **Strict typing debt** – mypy still reports hundreds of errors across helpers, dashboards, services, and config flows; reducing this backlog is the primary blocker to restoring strict gates.【2721df†L1-L120】
2. **Diagnostics schema monitoring** – coordinator and diagnostics payloads must keep the rejection metrics schema aligned with the Platinum dashboard expectations; continue validating telemetry and docs whenever payloads evolve.【F:custom_components/pawcontrol/coordinator_observability.py†L82-L150】【F:custom_components/pawcontrol/diagnostics.py†L602-L666】【F:docs/diagnostik.md†L24-L48】
3. **Config-flow harness stability** – compat shims and tests ensure exception aliases stay rebound after reloads; reconfigure/update flows still need focused validation work.【F:custom_components/pawcontrol/compat.py†L93-L218】【F:tests/components/pawcontrol/test_config_flow.py†L40-L120】【F:tests/helpers/homeassistant_test_stubs.py†L1852-L1875】
4. **Resilience telemetry follow-up** – circuit breaker metrics now surface rejection counters, but the front-end still lacks validation once the updated dashboards land in Platinum builds.【F:custom_components/pawcontrol/resilience.py†L200-L312】【F:custom_components/pawcontrol/coordinator_tasks.py†L672-L829】【F:tests/unit/test_coordinator_observability.py†L1-L138】
5. **Notification quiet-hours fixture** – the time patch remains critical for Python 3.13 compatibility; audit remaining call sites for naive `dt.now` usage before expanding automation coverage.【F:tests/unit/test_notifications.py†L371-L404】
6. **Service validation telemetry** – `_service_validation_error` still needs richer assertions so telemetry captures payloads during garden service failures.【F:custom_components/pawcontrol/services.py†L90-L127】【F:tests/components/pawcontrol/test_services.py†L190-L235】

## Improvement opportunities
- Prioritise mypy remediation on coordinator mixins and module adapters to shrink the failure surface before touching peripheral helpers.【2721df†L1-L120】
- Keep Copilot, Claude, and Gemini contributor instructions synchronised whenever workflows (such as door sensor overrides) change so community PRs follow the same Platinum guardrails.【F:.github/copilot-instructions.md†L1-L110】【F:.claude/agents/copilot-instructions.md†L1-L120】【F:.gemini/styleguide.md†L1-L40】
- Continue monitoring `_coerce_bool` telemetry for unexpected payloads and extend regression coverage if new shapes surface from legacy options.【F:custom_components/pawcontrol/door_sensor_manager.py†L90-L180】【F:tests/unit/test_door_sensor_manager.py†L86-L170】
- Track resilience UI updates so diagnostics, docs, and coordinator observability stay aligned with the latest rejection metrics schema.【F:custom_components/pawcontrol/coordinator_observability.py†L82-L150】【F:docs/diagnostik.md†L24-L48】

## Next sprint priorities
1. **Coordinators & adapters typing sweep** – Carve down the mypy backlog by introducing `TypedDict` wrappers for coordinator payloads and updating module adapters to stop cloning `object`-typed payloads before binding managers.【2721df†L1-L120】【F:custom_components/pawcontrol/coordinator.py†L200-L460】
2. **Resilience UI parity** – Extend dashboard generators so rejection metrics surface typed `CoordinatorStatisticsPayload` snapshots and add docs/tests for the updated schema to keep Platinum dashboards aligned.【F:custom_components/pawcontrol/coordinator_tasks.py†L672-L829】【F:custom_components/pawcontrol/dashboard_generator.py†L120-L520】【F:docs/diagnostik.md†L24-L48】
3. **Options flow data hygiene** – Replace residual `object` fallbacks in the advanced options menus with helpers from `types.py` to prevent malformed snapshots from bypassing `_normalise_options_snapshot`.【2721df†L1-L120】【F:custom_components/pawcontrol/options_flow.py†L3124-L3382】【F:custom_components/pawcontrol/types.py†L1900-L1990】
4. **Door sensor lifecycle integration** – Wire `ensure_door_sensor_settings_config` into config-flow save paths and persist the normalised snapshot through `PawControlDataManager.async_update_dog_data` so reloads keep clamped overrides without manual restarts.【F:custom_components/pawcontrol/options_flow.py†L2579-L2616】【F:custom_components/pawcontrol/data_manager.py†L985-L1030】【F:custom_components/pawcontrol/door_sensor_manager.py†L600-L760】
5. **Documentation sync** – Capture the outstanding Platinum gaps (typing debt, diagnostics telemetry, resilience UI) in `docs/compliance_gap_analysis.md` and surface callouts in `README.md` so partners can monitor readiness.【F:docs/compliance_gap_analysis.md†L1-L58】【F:README.md†L402-L448】

## Regression coverage highlights
- `tests/unit/test_door_sensor_manager.py` protects alias handling, numeric toggle coercion, persistence through the data manager, removals, and monitoring restarts for the door sensor manager helpers.【F:tests/unit/test_door_sensor_manager.py†L23-L310】
- Config flow and compat tests safeguard the exception rebinding harness so reloads keep using the active Home Assistant exceptions.【F:tests/components/pawcontrol/test_config_flow.py†L40-L120】【F:tests/unit/test_exception_alias_rebinds.py†L1-L184】

