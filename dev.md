# Developer Guide (pawcontrol)

## Goals
- Maintain Home Assistant-aligned quality (async-first, typed, tested, documented).
- Keep user-facing docs separate from developer docs.
- Provide reproducible quality gates locally and in CI.

## Prerequisites
- Python (match `.python-version`)
- Recommended: uv or pipx + virtualenv
- Optional: Home Assistant Core checkout for integration-style testing

## Setup (local)
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements_test.txt
pip install -r requirements.txt
pre-commit install
```

Tooling notes:
- The repository includes lightweight shims in `pytest_cov/` and
  `pytest_homeassistant_custom_component/` to avoid plugin conflicts during
  local and CI test runs; keep them versioned and avoid installing the PyPI
  variants alongside this repo.
- Do not commit generated coverage output (`htmlcov/`, `.coverage*`);
  publish HTML coverage via CI artifacts or GitHub Pages instead.

## Quality gate (must pass before PR)
```bash
ruff format
ruff check
python -m script.enforce_test_requirements
mypy custom_components/pawcontrol
pytest -q
python -m script.hassfest \
  --integration-path custom_components/pawcontrol
python -m script.sync_contributor_guides
```

## Test strategy
Minimum required suites:

- Config entry setup/unload/reload
- Config flow + options flow (happy path + error paths)
- Reauth flow
- Coordinator update failures + recovery
- Services (validation + side effects)
- Diagnostics (ensures redaction of secrets)

### Coverage rules
Treat coverage as a signal, not a trophy.

- No “fake coverage” via trivial asserts; cover failure paths and migrations.
- Publish HTML coverage via CI artifacts or gh-pages instead of committing it.

## Diagnostics
Diagnostics must redact sensitive fields (tokens, GPS home coordinates, user identifiers).
Provide a short doc snippet describing what is included/excluded.

## Documentation rules
User docs (README / INSTALLATION / docs/):

- What it is + what it supports
- Setup steps (UI-driven)
- Entities/services/events overview
- Examples: automations + dashboards
- Troubleshooting (common errors, logs, diagnostics download)

Developer docs (this file):

- Dev environment
- Test/lint/typecheck
- Release process
- Architecture notes

## Dependency policy
Keep runtime deps minimal.

If vendoring a dependency:

- Explain WHY it is vendored
- Prove isolation (no module shadowing)
- Define update & security monitoring procedure

Vendored PyYAML guidance:
- Only vendor PyYAML if Home Assistant’s constraints or wheel availability
  require it; prefer upstream wheels where possible.
- Document the import path used for the vendored copy (so it cannot shadow
  `yaml` from site-packages) and keep the isolation strategy in sync with the
  loader code.
- Track updates via the existing OSV/PyPI monitor workflow and refresh the
  status report that backs the README evidence before each release.

## Releases
- Versioning scheme
- Changelog policy
- CI checks required for release
