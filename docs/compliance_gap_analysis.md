# Compliance gap analysis (PawControl)

This report maps the Home Assistant quality-scale Platinum rules to concrete
implementation evidence, tests, and maintainers. It mirrors
`custom_components/pawcontrol/quality_scale.yaml` and is designed to make the
Home Assistant quality-scale checks (manifest, diagnostics, and tests) easy to
verify during reviews.

## Source of truth

- Quality scale tracker: `custom_components/pawcontrol/quality_scale.yaml`
- Manifest declaration: `custom_components/pawcontrol/manifest.json`
- Diagnostics export: `custom_components/pawcontrol/diagnostics.py`
- Diagnostics tests: `tests/test_diagnostics.py`

## Platinum rule mapping

| Rule | Code / docs evidence | Tests / checks | Owner |
| --- | --- | --- | --- |
| has-owner | `CODEOWNERS`, `custom_components/pawcontrol/manifest.json` | N/A | @BigDaddy1990 |
| config-flow | `custom_components/pawcontrol/config_flow.py`, `custom_components/pawcontrol/flow_validation.py`, `custom_components/pawcontrol/strings.json`, `docs/user_guide.md`, `docs/setup_installation_guide.md` | `tests/unit/test_config_flow_dogs.py`, `tests/unit/test_config_flow_base.py`, `tests/unit/test_config_flow_modules.py`, `tests/test_flow_validation.py` | @BigDaddy1990 |
| docs-actions | `custom_components/pawcontrol/services.py`, `custom_components/pawcontrol/script_manager.py`, `custom_components/pawcontrol/services.yaml`, `README.md`, `docs/automation_examples.md` | `tests/unit/test_services.py` | @BigDaddy1990 |
| docs-removal | `docs/setup_installation_guide.md`, `docs/troubleshooting.md` | N/A | @BigDaddy1990 |
| runtime-data | `custom_components/pawcontrol/runtime_data.py`, `custom_components/pawcontrol/coordinator_runtime.py` | `tests/test_runtime_data.py` | @BigDaddy1990 |
| stale-devices | `custom_components/pawcontrol/__init__.py` | `tests/helpers/homeassistant_test_stubs.py` | @BigDaddy1990 |
| dynamic-devices | `custom_components/pawcontrol/` entity setup | `tests/helpers/homeassistant_test_stubs.py` | @BigDaddy1990 |
| test-before-setup | `custom_components/pawcontrol/validation.py`, `custom_components/pawcontrol/flow_validation.py`, `custom_components/pawcontrol/api_validator.py` | `tests/test_validation_inputs.py`, `tests/test_flow_validation.py`, `tests/test_api_validator.py` | @BigDaddy1990 |
| test-before-update | `custom_components/pawcontrol/coordinator.py`, `custom_components/pawcontrol/diagnostics.py` | `tests/test_diagnostics.py`, `tests/unit/test_coordinator_tasks.py`, `tests/unit/test_services.py` | @BigDaddy1990 |
| test-before-unload | `custom_components/pawcontrol/__init__.py`, `custom_components/pawcontrol/runtime_data.py` | `tests/test_runtime_data.py` | @BigDaddy1990 |
| test-coverage | `pyproject.toml` coverage config | `tests/` (including `tests/test_geofence_zone.py`, `tests/test_validation_inputs.py`) | @BigDaddy1990 |
| brands | `brands/pawcontrol/` | N/A | @BigDaddy1990 |
| documentation | `README.md`, `docs/user_guide.md`, `docs/automation_examples.md`, `docs/troubleshooting.md`, `docs/setup_installation_guide.md` | N/A | @BigDaddy1990 |
| diagnostics | `custom_components/pawcontrol/diagnostics.py`, `docs/diagnostics.md` | `tests/test_diagnostics.py`, `tests/unit/test_diagnostics_cache.py`, `tests/unit/test_services.py`, `tests/unit/test_system_health.py` | @BigDaddy1990 |
| repairs | `custom_components/pawcontrol/repairs.py` | `tests/test_repairs.py` | @BigDaddy1990 |
| maintenance-playbook | `dev.md` | N/A | @BigDaddy1990 |
| localization | `custom_components/pawcontrol/strings.json`, `custom_components/pawcontrol/translations/` | `tests/test_localization_strings.py` | @BigDaddy1990 |

## Review notes

- The manifest declares Platinum (`custom_components/pawcontrol/manifest.json`) and
  must stay aligned with this report and `custom_components/pawcontrol/quality_scale.yaml`.
- Diagnostics evidence should include both `custom_components/pawcontrol/diagnostics.py`
  and the regression coverage in `tests/test_diagnostics.py`.
- When adding new tests or third-party requirements, update `requirements_test.txt`
  and run `python -m scripts.enforce_test_requirements`.
