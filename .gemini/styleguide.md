# PawControl Gemini Style Guide

This style guide mirrors the conventions already documented for GitHub Copilot and adapts them for Gemini Code Assist. It
applies to the entire repository unless a more specific file-level convention is documented elsewhere. Keep the contents of
this guide aligned with `.github/copilot-instructions.md` so both assistants surface the same Home Assistant expectations for
PawControl.【F:.github/copilot-instructions.md†L1-L74】

## Repository context
- **Domain:** `custom_components/pawcontrol` is a Home Assistant integration that targets the Platinum quality scale.
- **Primary language:** Python 3.13 with full typing; auxiliary assets live in `assets/`, documentation in `docs/`, and tests in
  `tests/`.
- **Automation & tooling:** Ruff formats and lints the codebase, MyPy enforces static types, and pytest provides the test suite
  (see `pyproject.toml`).
- **Constants:** Add or reuse shared identifiers from `custom_components/pawcontrol/const.py` instead of hard coding values.

## Core engineering principles
1. **Maintain Platinum readiness.** Keep `quality_scale.yaml` accurate when capabilities change and preserve requirements such as
   diagnostics (`diagnostics.py`), repairs (`repairs.py`), and strict typing throughout the package.
2. **Favor typed runtime data.** Use the aliases from `types.py` (`PawControlConfigEntry`, `DogConfigData`, etc.) and store
   runtime state on `ConfigEntry.runtime_data`.
3. **Stay asynchronous.** Avoid blocking I/O inside Home Assistant callbacks—create network clients with
   `async_get_clientsession` and rely on `asyncio` primitives.
4. **Centralize fetching.** Route external updates through `PawControlCoordinator` so entities can subscribe via
   `CoordinatorEntity`.
5. **Fail loudly but clearly.** Raise specific exceptions such as `PawControlSetupError` and log actionable context with the
   module-level `_LOGGER`.

## Python guidelines
### Language level & formatting
- Target Python 3.13 features (structural pattern matching, dataclasses, `type` alias syntax).
- Respect Ruff defaults: 88-character lines, double quotes, spaces for indentation, and alphabetized import groups. Keep
  `__all__`, constants, and data class fields sorted for readability.
- Prefer f-strings and comprehensions; avoid legacy formatting helpers unless backward compatibility is required.

### Typing & data models
- Type every function signature and significant local variable. Extend the existing `TypedDict` definitions in `types.py` for new
  configuration payloads and add frozen `set`/`frozenset` constants for allowed values.
- When storing structured state, add dataclasses in `types.py` or dedicated models modules so the coordinator and entities share
  consistent contracts.
- Update `py.typed` if new typed modules are added to ensure PEP 561 compliance.

### Async patterns & concurrency
- Use `asyncio.create_task` and `asyncio.gather` only from async contexts that already handle cancellation (see
  `PawControlCoordinator._async_update_data`). Guard concurrent sections with semaphores when talking to external services.
- Wrap long-running work in executors via `hass.async_add_executor_job` if synchronous libraries must be used.
- Provide timeouts for network calls and propagate `ConfigEntryNotReady` when setup prerequisites are missing.

### Entities & platforms
- Instantiate new entities through `EntityFactory` so profile-driven platform selection remains centralized. Update
  `get_platforms_for_profile_and_modules` in `__init__.py` when introducing new platforms.
- Entities should inherit from the appropriate Home Assistant mixins (for example, `CoordinatorEntity`) and set
  `_attr_has_entity_name = True` unless there is a compatibility reason not to.
- Expose device information through `device_info` and unique IDs via `entity_registry_enabled_default` / `_attr_unique_id`.
- Keep per-dog calculations (feeding, walk statistics, notifications) inside their respective managers instead of entities.

### Configuration flows & services
- Increment `VERSION`/`MINOR_VERSION` in `config_flow.py` when altering stored options and document new flow strings in
  `strings.json` and `translations/`.
- Validate user input early, surface friendly error keys that exist in `strings.json`, and reuse helper methods from
  `config_flow_base.py` to avoid duplication.
- Document service parameter changes in `services.yaml` and update validation helpers in `services.py` and related manager
  modules.

### Logging & error handling
- Instantiate `_LOGGER` with `logging.getLogger(__name__)` and use structured messages (`_LOGGER.warning("Dog %s", dog_id)`).
- Downgrade log severity when handling expected states (for example, temporary connectivity issues) but raise `UpdateFailed`
  when the coordinator cannot deliver fresh data.
- Provide guard clauses before mutating shared caches like `_PLATFORM_CACHE` to keep setup deterministic.

## Testing expectations
- Write pytest tests in `tests/` using `pytest.mark.asyncio` where appropriate. Maintain at least 95% coverage (see
  `[tool.coverage.report] fail_under` in `pyproject.toml`).
- New behavior should have positive and negative path tests and update fixtures under `tests/fixtures/` when schemas change.
- Run the standard suite before submitting: `ruff format`, `ruff check`, `mypy`, and `pytest -q`.

## Documentation, UI strings & assets
- Author user-facing text in American English and second-person voice ("you"/"your"). Keep titles and headings in sentence case.
- Update `README.md`, `docs/`, and release notes when adding features that affect setup or user workflows.
- Keep translation files in sync: edit `strings.json` first, then regenerate or manually update localized copies in
  `translations/`.
- Store only optimized, committed assets in `assets/` and `docs/`. Large binaries should remain out of the repository.

## Review checklist for Gemini
- Does the change preserve asynchronous patterns and avoid blocking Home Assistant's event loop?
- Are types, constants, and coordinator contracts extended consistently across `const.py`, `types.py`, and manager modules?
- Have services, options flows, diagnostics, and dashboards been updated together when behavior changes?
- Do new or modified user-visible strings follow the language and tone requirements and include translation updates?
- Are tests and coverage goals satisfied with meaningful assertions rather than simple smoke tests?

Following these guidelines keeps Gemini Code Assist aligned with the expectations documented for Copilot and the Home Assistant
community standards this project already meets.
