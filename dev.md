# Development Plan

## Quality Gate Expectations
- `ruff format`, `ruff check`, `mypy`, and `pytest -q` form the mandatory pre-PR sequence, matching the guidance captured in README.【F:README.md†L28-L68】
- New documentation must cite authoritative evidence (tests, scripts, or source files) as demonstrated in README and `docs/markdown_compliance_review.md` so reviewers can audit the Platinum uplift quickly.【F:README.md†L320-L372】【F:docs/markdown_compliance_review.md†L1-L120】

## Outstanding Failures and Opportunities
- `tests/unit/test_adaptive_cache.py` still reports missing expirations because `cleanup_expired` returns `0` under the lock-handoff scenarios; the cache eviction path needs to honour overrides while pruning stale entries.【9cf9da†L5-L14】
- `tests/unit/test_optimized_data_cache.py` shows expired items sticking around and not respecting override precedence, so the cache fetch/cleanup routines must reconcile timestamp normalisation with override windows.【9cf9da†L14-L23】
- Pytest warns that synchronous tests are requesting async fixtures in `tests/components/pawcontrol/test_optimized_entity_base.py`; migrate those helpers to synchronous fixtures or convert the tests to async-aware patterns before pytest 9 makes this fatal.【9cf9da†L23-L60】

## Action Items
1. Capture the current `ruff` and `pytest` results, filing regressions under “Outstanding Failures and Opportunities”. `ruff check` is green; `pytest -q` fails on the adaptive and optimized cache suites.【501d79†L1-L1】【9cf9da†L1-L72】
2. Close the remaining Platinum blockers—device removal workflows, brand assets, and automated coverage publishing—and update README badges once work lands.【F:docs/compliance_gap_analysis.md†L1-L120】
3. Expand removal/troubleshooting guidance in `INSTALLATION.md` and `info.md` after the device removal tests pass to keep Markdown aligned with runtime behaviour.【F:docs/markdown_compliance_review.md†L1-L120】
4. Keep `.github/copilot-instructions.md`, `.gemini/styleguide.md`, and `.claude/agents/copilot-instructions.md` aligned when requirements change so assistant guidance does not drift.【F:.github/copilot-instructions.md†L1-L92】【F:.gemini/styleguide.md†L1-L26】【F:.claude/agents/copilot-instructions.md†L1-L8】

## Recently Addressed
- README now documents the Platinum uplift, quality gates, and documentation traceability so contributors follow the same compliance baseline.【F:README.md†L1-L199】【F:README.md†L320-L380】
- `docs/compliance_gap_analysis.md` and `docs/markdown_compliance_review.md` provide auditable mappings from Home Assistant requirements to repository evidence, satisfying the instruction sets from Copilot, Gemini, and Claude.【F:docs/compliance_gap_analysis.md†L1-L120】【F:docs/markdown_compliance_review.md†L1-L120】
