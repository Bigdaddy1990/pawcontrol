# PawControl Contributor Guide

These instructions describe how to work on the `custom_components/pawcontrol`
Home Assistant integration. They consolidate the authoring rules from the
Gemini and Claude style guides with the upstream Home Assistant requirements so
contributors consistently deliver Platinum-quality changes.

## Quick reference

```bash
ruff format                          # Apply repository formatting rules
ruff check                           # Run Ruff lint (includes docstring gates)
mypy custom_components/pawcontrol    # Ensure static typing stays strict
pytest -q                            # Execute the async pytest suite
python -m script.hassfest \
  --integration-path custom_components/pawcontrol  # Validate manifest & strings
```

*Run every command before opening a pull request.* `pyproject.toml` configures
these tools for Python 3.13+ and enforces 95 percent coverage on the package
under test.【F:pyproject.toml†L1-L72】【F:pyproject.toml†L73-L110】

## Integration architecture

- The integration lives in `custom_components/pawcontrol` and is installed via
the UI only (`CONFIG_SCHEMA` is entry-only).【F:custom_components/pawcontrol/__init__.py†L1-L118】
- Runtime state is stored on `ConfigEntry.runtime_data` through helpers such as
`store_runtime_data` and the `PawControlCoordinator`, so new features must hook
into the coordinator rather than creating bespoke tasks.【F:custom_components/pawcontrol/__init__.py†L119-L213】
- The manifest advertises discovery via DHCP, USB, HomeKit, and Zeroconf and
declares Bronze today—update the badge and manifest together when Platinum
requirements are met.【F:custom_components/pawcontrol/manifest.json†L1-L66】

## Development standards

### Python quality bar

- Target Python 3.13 syntax and typing everywhere; no untyped defs or implicit
optionals are allowed because MyPy is configured to fail otherwise.【F:pyproject.toml†L37-L72】
- Keep modules fully typed (`py.typed` is shipped) and add type aliases in
`types.py` when expanding runtime models.
- Ruff supplies formatting and linting—respect 88 character lines, prefer
f-strings, and keep imports sorted by section.
- Every coroutine interacting with Home Assistant must be async. Wrap blocking
work with `hass.async_add_executor_job` if an async variant is unavailable.

### Coordinators, managers, and services

- Use the existing managers (`FeedingManager`, `WalkManager`, etc.) to store
  per-dog logic; entities should subscribe to coordinator data instead of calling
  clients directly.【F:custom_components/pawcontrol/__init__.py†L149-L213】
- Normalise door sensor overrides with `ensure_door_sensor_settings_config` so
  timeouts, durations, delays, and confirmation toggles remain clamped before
  mutating `DoorSensorConfig`. Trim and validate sensor entity IDs before
  persisting them. Settings-only updates should leave monitoring listeners
  untouched when the effective snapshot is unchanged, stored payloads must travel
  under `CONF_DOOR_SENSOR_SETTINGS`, and the normalised snapshot has to be
  persisted through `PawControlDataManager.async_update_dog_data` so config-entry
  reloads retain the clamped values.
- Always pass the active config entry into new `DataUpdateCoordinator` instances
  and surface API errors via `UpdateFailed` or `ConfigEntryAuthFailed` as shown in
  `coordinator.py` and `exceptions.py`.
- Service handlers must live in `services.py`/`script_manager.py` and be
validated in `services.yaml`. Keep the scheduler wiring in
`async_setup_daily_reset_scheduler` intact when extending services.

### Config flows, options, and reauth

- `config_flow.py` implements user, discovery, reauth, and reconfigure steps.
Add validation helpers alongside the mixins and reuse existing constants from
`const.py` to keep schemas consistent.【F:custom_components/pawcontrol/config_flow.py†L1-L120】
- Do not allow users to rename entries during setup; titles are generated from
the profile helpers. Always call `_abort_if_unique_id_configured` or the
matching helpers before creating entries.
- Options flows should mirror config flow validation and store adjustments in
`ConfigEntry.options`. Keep translation keys in `strings.json` and
`translations/` synchronized.

### Logging and diagnostics

- Initialise loggers with `_LOGGER = logging.getLogger(__name__)` and use lazy
string formatting. Promote repeated failure information to repairs
(`repairs.py`) and diagnostics exports (`diagnostics.py`).
- Diagnostics payloads must always include the `rejection_metrics` structure with
  zeroed defaults and `schema_version` so Platinum dashboards and docs can ingest
  the counters without bespoke scraping; update coordinator observability tests,
  docs, and front-end schema references together and revalidate the diagnostics
  panel once UI updates land.
- Mark entities with `_attr_has_entity_name = True` and populate `device_info`
using identifiers from `const.py`.

## Documentation and release hygiene

- Update README, `info.md`, and `docs/` when workflows change. Each file must
link to the relevant evidence (tests, modules, or scripts) so reviewers can
verify Platinum claims.【F:docs/markdown_compliance_review.md†L1-L60】
- Keep `docs/compliance_gap_analysis.md` in sync with the manifest and
quality_scale badge. Document outstanding gaps and close them before promoting
the manifest to Platinum.【F:docs/compliance_gap_analysis.md†L1-L58】
- Log new work in `CHANGELOG.md`/`RELEASE_NOTES.md` and refresh brand assets
once the Home Assistant brand repository accepts updates.【F:docs/compliance_gap_analysis.md†L59-L75】

## Review checklist

- [ ] `ruff format`, `ruff check`, `mypy`, and `pytest -q` all pass locally.
- [ ] `script.hassfest` succeeds for `custom_components/pawcontrol`.
- [ ] Async flows, coordinators, and managers reuse shared helpers instead of
introducing duplicate code.
- [ ] Config/Options flows validate input, prevent duplicates, and provide
reauth/reconfigure paths.
- [ ] All user-facing strings live in `strings.json`/`translations/` and follow
Home Assistant tone guidelines.
- [ ] New documentation includes citations to code/tests proving the behaviour.
- [ ] Device removal (`async_remove_config_entry_device`) and diagnostics remain
covered by tests when behaviour changes.
