# Developer Guide (PawControl)

This guide covers **local development**, **testing**, and **troubleshooting** for
the PawControl Home Assistant integration. User-facing documentation lives in
`README.md` and the `docs/` folder.

## Local development setup

1. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements_test.txt
   pip install -r requirements.txt
   ```
3. Optional: install the project in editable mode for packaging hooks:
   ```bash
   pip install -e .
   ```

> **Note:** The repository ships local shims in `pytest_cov/` and
> `pytest_homeassistant_custom_component/`. Avoid installing the PyPI variants
> alongside this repo to prevent plugin conflicts.

## Running locally with Home Assistant

1. Copy the integration to your HA config:
   ```bash
   cp -r custom_components/pawcontrol /config/custom_components/
   ```
2. Restart Home Assistant.
3. Add the integration from **Settings → Devices & Services**.

## Quality gate (run before PR)

```bash
ruff format
ruff check
python -m script.enforce_test_requirements
mypy custom_components/pawcontrol
pytest -q
python -m script.hassfest --integration-path custom_components/pawcontrol
python -m script.sync_contributor_guides
```

The CI workflows must execute the same quality gate and **fail fast** when any
command returns a non-zero exit code. Treat a green run as a hard requirement
before opening or merging a pull request.

## Testing strategy

Target **unit coverage for every entity type and flow**, including normal and
error paths:

- Config flow, options flow, and reauth scenarios
- Coordinator update failures and retry handling
- Service validation and side effects
- Diagnostics redaction
- Entity behavior for typical + failure paths (e.g., missing API token,
  invalid geofence coordinates, timeout handling)

Use `pytest` fixtures and the Home Assistant stubs in
`tests/helpers/homeassistant_test_stubs.py` to simulate core behavior without a
full HA runtime. Always exercise both successful and rejected paths by crafting
fixtures for missing API tokens, invalid geofence inputs, or timeout
conditions.

### Measuring coverage (without committing artifacts)

```bash
pytest -q --cov custom_components/pawcontrol --cov-report=term-missing
```

- Do **not** commit generated artifacts such as `.coverage*` or `htmlcov/`.
- Publish HTML coverage via CI artifacts or GitHub Pages instead.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `ImportError` for HA modules | Stubs not loaded or missing dependencies | Ensure tests call `install_homeassistant_stubs()` and requirements are installed. |
| `hassfest` failures | Missing keys in `strings.json` | Add new strings and sync `translations/*.json`. |
| `mypy` errors | Untyped returns/optionals | Update annotations; avoid implicit optionals. |
| `pytest` failures on coverage | Missing tests or uncovered error paths | Add unit tests for invalid inputs (e.g., geofence radius, missing API token). |

## Release checklist (dev-side)

- Update `CHANGELOG.md` with user-visible changes.
- Ensure new docs link to evidence (tests, diagnostics, workflows).
- Re-run the quality gate commands before tagging a release.
