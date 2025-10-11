# Development Plan

## Quality Gate Expectations
- Run `ruff check`, `pytest`, `mypy`, and `python -m script.hassfest --integration-path custom_components/pawcontrol` before every pull request to match the repository guardrails.【F:.github/copilot-instructions.md†L10-L28】【F:.github/copilot-instructions.md†L52-L70】
- Target Python 3.13+ typing throughout the integration; keep new helpers within the existing Platinum-quality architecture under `custom_components/pawcontrol`.【F:pyproject.toml†L37-L72】【F:custom_components/pawcontrol/__init__.py†L1-L213】

## Outstanding Failures and Opportunities
- Baseline CI gaps remain: `pytest -q` still fails because legacy config-flow fixtures, resilience coverage, notification monkeypatches, and garden-service assertions have not been modernised, while hassfest succeeds and `ruff check` is clean.【214619†L1-L2】【8d03d0†L1-L92】
- `mypy custom_components/pawcontrol` continues to surface 300+ legacy issues across compatibility layers, coordinators, and service helpers; broaden strict typing only after stabilising each module sweep.【269313†L1-L2】【9bf51b†L1-L43】
- Feeding compliance aggregation now ships additional regression coverage that exercises nested, recursive, and parallel iteration so `_normalise_sequence` snapshots remain reusable without over-consuming structured telemetry sources.【F:custom_components/pawcontrol/feeding_translations.py†L320-L369】【F:tests/unit/test_feeding_translations.py†L1-L160】

## Near-term Focus
1. Finish the coordinator/service telemetry sweep so repairs, diagnostics, and runtime performance stats stay in sync while we stage the broader mypy gate.【F:custom_components/pawcontrol/services.py†L4086-L4184】【F:custom_components/pawcontrol/coordinator_tasks.py†L22-L240】
2. Reduce the outstanding typing debt module-by-module (config flows, helpers, managers) before enabling repo-wide strict mypy enforcement.【F:custom_components/pawcontrol/config_flow.py†L1888-L2036】【F:custom_components/pawcontrol/helper_manager.py†L40-L240】
3. Keep `.github/copilot-instructions.md`, `.claude/agents/copilot-instructions.md`, and `.gemini/styleguide.md` aligned whenever requirements change so assistant guidance stays consistent.【F:.github/copilot-instructions.md†L1-L92】【F:.claude/agents/copilot-instructions.md†L1-L120】【F:.gemini/styleguide.md†L1-L200】

## Tooling Checklist
- `ruff check`
- `pytest tests/unit/test_feeding_translations.py -q`
- `pytest tests/unit/test_services.py::test_check_feeding_compliance_sanitises_structured_messages -q`
- `pytest tests/test_repairs.py::test_async_publish_feeding_compliance_issue_sanitises_mapping_message -q`
- `python -m script.hassfest --integration-path custom_components/pawcontrol`

Record outcomes for each run in commit discussions so we maintain an auditable trail before broadening the Platinum gates.【F:.github/copilot-instructions.md†L10-L28】
