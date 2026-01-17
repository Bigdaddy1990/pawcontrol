# Contributing to PawControl

Thank you for your interest in improving the PawControl integration. This guide explains how you can deliver high-quality contributions quickly and confidently.

## Know the quality expectations
- PawControl declares the Platinum level of the Home Assistant integration quality scale (see `custom_components/pawcontrol/manifest.json`). Contributions must preserve the evidence tracked in `custom_components/pawcontrol/quality_scale.yaml` and related compliance reports.
- Review `custom_components/pawcontrol/quality_scale.yaml` before you start so you understand which requirements are complete, exempt, or still marked as TODO.
- When you finish a requirement or claim an exemption, update the quality scale file and include a short comment that explains the change.

## Set up your environment
1. Use Python 3.13 or newer.
2. Fork the repository and create a feature branch for each contribution.
3. Create a virtual environment and install the dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows use `.venv\\Scripts\\activate`
   pip install -r requirements.txt -r requirements_test.txt
   pip install -U homeassistant pytest-homeassistant-custom-component
   pip install -U ruff mypy pre-commit pytest pytest-asyncio pytest-cov
   pre-commit install --install-hooks
   ```

4. Install any additional tooling you need for documentation or translation updates.

## Follow development guidelines
- Write asynchronous, fully typed code and prefer modern Python features such as pattern matching, dataclasses, and `ConfigEntry.runtime_data`.
- Reuse shared helpers under `custom_components/pawcontrol/` and constants from `homeassistant.const` instead of hardcoding values.
- Keep all user-facing text in American English, use sentence case for headings, and speak to the user in second-person voice.
- Update or add tests under `tests/` for every behavior change so coverage stays above the threshold defined in `pyproject.toml`.
- Revise documentation, release notes, and translations (for example files in `docs/`, `README.md`, and `custom_components/pawcontrol/translations/`) whenever behavior or options change.

### Required Home Assistant references
PawControl contributions must align with the official Home Assistant developer documentation and policy updates. Review the following sources before you begin and use them as the authoritative reference when implementing or reviewing changes:

- Home Assistant developer blog and platform overview:
  - https://developers.home-assistant.io/blog
  - https://developers.home-assistant.io/
- Development expectations and validation:
  - https://developers.home-assistant.io/docs/development_guidelines
  - https://developers.home-assistant.io/docs/development_checklist
  - https://developers.home-assistant.io/docs/development_testing
  - https://developers.home-assistant.io/docs/development_validation
  - https://developers.home-assistant.io/docs/development_typing
  - https://www.home-assistant.io/docs/tools/check_config/
- Quality scale rules and checklists:
  - https://developers.home-assistant.io/docs/core/integration-quality-scale/rules
  - https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/action-setup/
  - https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/common-modules
  - https://developers.home-assistant.io/docs/core/integration-quality-scale/checklist
- Code review and documentation standards:
  - https://developers.home-assistant.io/docs/creating_component_code_review
  - https://developers.home-assistant.io/docs/creating_platform_code_review
  - https://developers.home-assistant.io/docs/documenting/yaml-style-guide
  - https://developers.home-assistant.io/docs/documenting/create-page
  - https://developers.home-assistant.io/docs/documenting/integration-docs-examples
- Core platform behaviors and helpers:
  - https://developers.home-assistant.io/docs/core/platform/significant_change
  - https://developers.home-assistant.io/docs/core/platform/reproduce_state
  - https://developers.home-assistant.io/docs/core/platform/repairs
  - https://developers.home-assistant.io/docs/instance_url
- Config entries, flows, and automations:
  - https://developers.home-assistant.io/docs/data_entry_flow_index
  - https://developers.home-assistant.io/docs/config_entries_index
  - https://developers.home-assistant.io/docs/automations
  - https://developers.home-assistant.io/docs/device_automation_index
  - https://developers.home-assistant.io/docs/device_automation_trigger
  - https://developers.home-assistant.io/docs/device_automation_condition
  - https://developers.home-assistant.io/docs/device_automation_action
  - https://developers.home-assistant.io/docs/internationalization/custom_integration
- Mobile app and intent integrations:
  - https://developers.home-assistant.io/docs/api/native-app-integration/setup
  - https://developers.home-assistant.io/docs/api/native-app-integration/sending-data
  - https://developers.home-assistant.io/docs/api/native-app-integration/sensors
  - https://developers.home-assistant.io/docs/api/native-app-integration/notifications
  - https://developers.home-assistant.io/docs/intent_conversation_api
  - https://developers.home-assistant.io/docs/intent_builtin
  - https://developers.home-assistant.io/docs/core/llm/

## Run local checks
Run the same checks that continuous integration executes before you open a pull request:

```bash
ruff format custom_components/pawcontrol tests
ruff check custom_components/pawcontrol tests
python -m scripts.enforce_test_requirements
mypy custom_components/pawcontrol
pytest --cov=custom_components/pawcontrol tests
pre-commit run --all-files
python -m hassfest  # Available via the Home Assistant hassfest tool or the hassfest PyPI package
```

If you have Home Assistant Core tooling available, also run the HACS validation (`hacs action --category integration`) to mirror the `hacs.yml` workflow. Fix any reported issues before you submit your changes.

## Submit your pull request
- Fill out the pull request template, describe the intent of your change, and link any related issues.
- Include a concise test plan listing the commands you ran. Attach screenshots or recordings for UI-visible updates.
- Keep commits focused and explain documentation, code, and translation updates in your summary.
- Stay involved after opening the pull request by responding to feedback and rebasing on `main` until your contribution merges.

We appreciate your help making PawControl better for every pet family!
