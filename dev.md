# Development Plan

## Quality Gate Expectations
- `ruff format`, `ruff check`, `mypy`, and `pytest -q` form the mandatory pre-PR sequence, matching the guidance captured in README.【F:README.md†L28-L68】
- New documentation must cite authoritative evidence (tests, scripts, or source files) as demonstrated in README and `docs/markdown_compliance_review.md` so reviewers can audit the Platinum uplift quickly.【F:README.md†L320-L372】【F:docs/markdown_compliance_review.md†L1-L120】

## Outstanding Failures and Opportunities
- `tests/unit/test_adaptive_cache.py` still reports missing expirations because `cleanup_expired` returns `0` under the lock-handoff scenarios; the cache eviction path needs to honour overrides while pruning stale entries.【9c4a6d†L4-L23】
- `tests/unit/test_optimized_data_cache.py` shows expired items sticking around and not respecting override precedence, so the cache fetch/cleanup routines must reconcile timestamp normalisation with override windows.【9c4a6d†L23-L32】

## Action Items
1. Capture the current `ruff` and `pytest` results, filing regressions under “Outstanding Failures and Opportunities”.
2. Close the remaining Platinum blockers—device removal workflows, brand assets, and automated coverage publishing—and update README badges once work lands.【F:docs/compliance_gap_analysis.md†L1-L120】
3. Expand removal/troubleshooting guidance in `INSTALLATION.md` and `info.md` after the device removal tests pass to keep Markdown aligned with runtime behaviour.【F:docs/markdown_compliance_review.md†L1-L120】

## Recently Addressed
- README now documents the Platinum uplift, quality gates, and documentation traceability so contributors follow the same compliance baseline.【F:README.md†L1-L199】【F:README.md†L320-L380】
- `docs/compliance_gap_analysis.md` and `docs/markdown_compliance_review.md` provide auditable mappings from Home Assistant requirements to repository evidence, satisfying the instruction sets from Copilot, Gemini, and Claude.【F:docs/compliance_gap_analysis.md†L1-L120】【F:docs/markdown_compliance_review.md†L1-L120】
