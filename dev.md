# Development Plan

## Outstanding Failures and Opportunities
- `pytest -q` now reports 4 failures concentrated in adaptive cache cleanup and optimized data cache expiration when patched `dt_util` timestamps jump, so cache eviction still needs hardening. 【44ea0e†L1-L68】
- `tests/unit/test_adaptive_cache.py` still returns zero removals for expired entries, indicating the override window prevents the background cleaner from pruning stale keys. 【44ea0e†L5-L32】
- `tests/unit/test_optimized_data_cache.py` continues to return stale values and refuses to drop overrides when expirations overlap, so we must reconcile timestamp normalization with override precedence. 【44ea0e†L33-L44】

## Action Items
1. Align the adaptive cache cleanup and optimized data cache eviction paths with Platinum expectations under repeated `dt_util` monkeypatching so expired items are removed deterministically even when overrides are active.
2. Once cache eviction is stable, re-run `pytest -q` to verify the failure surface is clear before moving to the next backlog item.

## Recently Addressed
- Reworked the global entity registry to register entities exactly once and keep the sentinel alive through cleanup, so `test_cleanup_preserves_live_entities` now survives full-suite garbage collection without duplicating weakrefs. 【F:custom_components/pawcontrol/optimized_entity_base.py†L1306-L1399】
- Documented the entity registry lifecycle helpers to satisfy the docstring baseline and keep the public API discoverable for Home Assistant reviewers. 【F:custom_components/pawcontrol/optimized_entity_base.py†L1227-L1260】
