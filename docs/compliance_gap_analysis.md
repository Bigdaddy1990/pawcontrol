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
| action-setup | `custom_components/pawcontrol/__init__.py`, `custom_components/pawcontrol/services.py` | `tests/unit/test_services.py` | @BigDaddy1990 |
| appropriate-polling | `custom_components/pawcontrol/coordinator.py`, `custom_components/pawcontrol/coordinator_support.py` | `tests/unit/test_adaptive_polling.py` | @BigDaddy1990 |
| brands | `brands/pawcontrol/` | N/A | @BigDaddy1990 |
| common-modules | `custom_components/pawcontrol/utils.py`, `custom_components/pawcontrol/http_client.py`, `custom_components/pawcontrol/types.py` | N/A | @BigDaddy1990 |
| config-flow-test-coverage | `custom_components/pawcontrol/config_flow.py`, `custom_components/pawcontrol/flow_validation.py` | `tests/unit/test_config_flow_dogs.py`, `tests/unit/test_config_flow_base.py`, `tests/unit/test_config_flow_modules.py`, `tests/test_flow_validation.py` | @BigDaddy1990 |
| config-flow | `custom_components/pawcontrol/config_flow.py`, `custom_components/pawcontrol/config_flow_main.py`, `docs/user_guide.md`, `docs/setup_installation_guide.md` | `tests/unit/test_config_flow_dogs.py`, `tests/unit/test_config_flow_base.py`, `tests/unit/test_config_flow_modules.py` | @BigDaddy1990 |
| dependency-transparency | `custom_components/pawcontrol/manifest.json`, `requirements.txt` | `python -m scripts.hassfest --integration-path custom_components/pawcontrol` | @BigDaddy1990 |
| docs-actions | `custom_components/pawcontrol/services.yaml`, `custom_components/pawcontrol/services.py`, `docs/automation_examples.md`, `README.md` | `tests/unit/test_services.py` | @BigDaddy1990 |
| docs-high-level-description | `README.md`, `docs/user_guide.md` | N/A | @BigDaddy1990 |
| docs-installation-instructions | `README.md`, `docs/setup_installation_guide.md` | N/A | @BigDaddy1990 |
| docs-removal-instructions | `docs/setup_installation_guide.md`, `docs/troubleshooting.md` | N/A | @BigDaddy1990 |
| entity-event-setup | `custom_components/pawcontrol/optimized_entity_base.py` | N/A | @BigDaddy1990 |
| entity-unique-id | `custom_components/pawcontrol/optimized_entity_base.py`, `custom_components/pawcontrol/switch.py` | `tests/components/pawcontrol/test_device_registry.py` | @BigDaddy1990 |
| has-entity-name | `custom_components/pawcontrol/sensor.py`, `custom_components/pawcontrol/device.py` | N/A | @BigDaddy1990 |
| runtime-data | `custom_components/pawcontrol/runtime_data.py`, `custom_components/pawcontrol/__init__.py` | `tests/test_runtime_data.py` | @BigDaddy1990 |
| test-before-configure | `custom_components/pawcontrol/flow_validation.py`, `custom_components/pawcontrol/api_validator.py` | `tests/test_flow_validation.py`, `tests/test_api_validator.py` | @BigDaddy1990 |
| test-before-setup | `custom_components/pawcontrol/validation.py`, `custom_components/pawcontrol/api_validator.py` | `tests/test_validation_inputs.py` | @BigDaddy1990 |
| unique-config-entry | `custom_components/pawcontrol/config_flow_main.py` | `tests/unit/test_config_flow_base.py` | @BigDaddy1990 |
| action-exceptions | `custom_components/pawcontrol/services.py` | `tests/unit/test_services.py` | @BigDaddy1990 |
| config-entry-unloading | `custom_components/pawcontrol/__init__.py`, `custom_components/pawcontrol/runtime_data.py` | `tests/test_runtime_data.py` | @BigDaddy1990 |
| docs-configuration-parameters | `README.md`, `docs/user_guide.md` | N/A | @BigDaddy1990 |
| docs-installation-parameters | `docs/setup_installation_guide.md` | N/A | @BigDaddy1990 |
| entity-unavailable | `custom_components/pawcontrol/optimized_entity_base.py`, `custom_components/pawcontrol/coordinator.py` | `tests/unit/test_coordinator_observability.py` | @BigDaddy1990 |
| integration-owner | `CODEOWNERS`, `custom_components/pawcontrol/manifest.json` | N/A | @BigDaddy1990 |
| log-when-unavailable | `custom_components/pawcontrol/coordinator.py`, `custom_components/pawcontrol/coordinator_observability.py` | `tests/unit/test_coordinator_observability.py` | @BigDaddy1990 |
| parallel-updates | `custom_components/pawcontrol/sensor.py`, `custom_components/pawcontrol/switch.py`, `custom_components/pawcontrol/button.py` | N/A | @BigDaddy1990 |
| reauthentication-flow | `custom_components/pawcontrol/config_flow_reauth.py` | `tests/unit/test_config_flow_base.py` | @BigDaddy1990 |
| test-coverage | `pyproject.toml` | `pytest -q` | @BigDaddy1990 |
| devices | `custom_components/pawcontrol/device.py` | `tests/components/pawcontrol/test_device_registry.py` | @BigDaddy1990 |
| diagnostics | `custom_components/pawcontrol/diagnostics.py`, `docs/diagnostics.md` | `tests/test_diagnostics.py`, `tests/unit/test_diagnostics_cache.py`, `tests/unit/test_system_health.py` | @BigDaddy1990 |
| discovery-update-info | `custom_components/pawcontrol/config_flow_main.py`, `custom_components/pawcontrol/config_flow_discovery.py` | `tests/unit/test_discovery.py` | @BigDaddy1990 |
| discovery | `custom_components/pawcontrol/config_flow_discovery.py`, `custom_components/pawcontrol/discovery.py` | `tests/unit/test_discovery.py` | @BigDaddy1990 |
| docs-data-update | `docs/user_guide.md`, `custom_components/pawcontrol/coordinator.py` | N/A | @BigDaddy1990 |
| docs-examples | `docs/automation_examples.md` | N/A | @BigDaddy1990 |
| docs-known-limitations | `docs/user_guide.md` | N/A | @BigDaddy1990 |
| docs-supported-devices | `docs/user_guide.md` | N/A | @BigDaddy1990 |
| docs-supported-functions | `docs/user_guide.md`, `README.md` | N/A | @BigDaddy1990 |
| docs-troubleshooting | `docs/troubleshooting.md` | N/A | @BigDaddy1990 |
| docs-use-cases | `docs/user_guide.md` | N/A | @BigDaddy1990 |
| dynamic-devices | `custom_components/pawcontrol/` entity setup | `tests/helpers/homeassistant_test_stubs.py` | @BigDaddy1990 |
| entity-category | `custom_components/pawcontrol/sensor.py`, `custom_components/pawcontrol/switch.py` | N/A | @BigDaddy1990 |
| entity-device-class | `custom_components/pawcontrol/binary_sensor.py`, `custom_components/pawcontrol/sensor.py` | N/A | @BigDaddy1990 |
| entity-disabled-by-default | `custom_components/pawcontrol/sensor.py`, `custom_components/pawcontrol/button.py` | N/A | @BigDaddy1990 |
| entity-translations | `custom_components/pawcontrol/strings.json`, `custom_components/pawcontrol/translations/` | `tests/test_localization_strings.py` | @BigDaddy1990 |
| exception-translations | `custom_components/pawcontrol/strings.json`, `custom_components/pawcontrol/exceptions.py` | `tests/test_localization_strings.py` | @BigDaddy1990 |
| icon-translations | `custom_components/pawcontrol/icons.json`, `custom_components/pawcontrol/strings.json` | `tests/test_localization_strings.py` | @BigDaddy1990 |
| reconfiguration-flow | `custom_components/pawcontrol/config_flow_main.py`, `docs/troubleshooting.md` | `tests/unit/test_config_flow_base.py` | @BigDaddy1990 |
| repair-issues | `custom_components/pawcontrol/repairs.py` | `tests/test_repairs.py` | @BigDaddy1990 |
| stale-devices | `custom_components/pawcontrol/__init__.py` | `tests/components/pawcontrol/test_device_registry.py` | @BigDaddy1990 |
| async-dependency | `custom_components/pawcontrol/manifest.json`, `custom_components/pawcontrol/device_api.py` | N/A | @BigDaddy1990 |
| inject-websession | `custom_components/pawcontrol/__init__.py`, `custom_components/pawcontrol/http_client.py` | N/A | @BigDaddy1990 |
| strict-typing | `pyproject.toml`, `custom_components/pawcontrol/py.typed` | `mypy custom_components/pawcontrol` | @BigDaddy1990 |

## Review notes

- The manifest declares Platinum (`custom_components/pawcontrol/manifest.json`) and
  must stay aligned with this report and `custom_components/pawcontrol/quality_scale.yaml`.
- Diagnostics evidence should include both `custom_components/pawcontrol/diagnostics.py`
  and the regression coverage in `tests/test_diagnostics.py`.
- When adding new tests or third-party requirements, update `requirements_test.txt`
  and run `python -m scripts.enforce_test_requirements`.
