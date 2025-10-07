# Development Plan

## Outstanding Failures and Opportunities
- Hassfest dependency and requirement validators are missing Home Assistant's `visit_Import`/`visit_ImportFrom` hooks and canonical name checks, causing failures in `tests/hassfest/test_dependencies.py` and `tests/hassfest/test_requirements.py`.
- Adaptive polling never reaches the requested idle interval, so `tests/unit/test_adaptive_polling.py` reports premature cadence convergence.
- Optimized data cache expiration and override paths disagree with the guard tests in `tests/unit/test_optimized_data_cache.py`.
- Walk lifecycle helpers fail to close or validate overlapping sessions, leading to assertion errors in `tests/unit/test_walk_manager.py` and `tests/components/pawcontrol/test_data_manager.py`.

## Action Items
1. Confirm the ConfigEntry compat resync runs when Home Assistant stubs load so the config flow and integration suites can execute.
2. Restore the standard profile metadata to the ≤12 entity budget expected by the profile tests and config flow titles.
3. Plan focused fixes for the hassfest validators, adaptive polling controller, optimized cache cleanup, and walk manager edge cases identified above.
