"""Regression tests for translation placeholders used by repairs telemetry."""

import json
from pathlib import Path

import pytest

TRANSLATION_FILES = (
  Path("custom_components/pawcontrol/strings.json"),
  Path("custom_components/pawcontrol/translations/en.json"),
  Path("custom_components/pawcontrol/translations/de.json"),
)

RECONFIGURE_WARNING_KEYS = {
  "timestamp",
  "previous_profile",
  "requested_profile",
  "warnings",
}

RECONFIGURE_HEALTH_KEYS = {
  "timestamp",
  "requested_profile",
  "health_issues",
  "health_warnings",
}

RECONFIGURE_ENTITY_KEYS = {
  "dogs_count",
  "profiles_info",
  "compatibility_info",
  "reconfigure_valid_dogs",
  "reconfigure_invalid_dogs",
  "last_reconfigure",
  "reconfigure_requested_profile",
  "reconfigure_previous_profile",
  "reconfigure_dogs",
  "reconfigure_entities",
  "reconfigure_health",
  "reconfigure_warnings",
  "reconfigure_merge_notes",
}


def _load_translation(path: Path) -> dict[str, object]:
  return json.loads(path.read_text(encoding="utf-8"))  # noqa: E111


@pytest.mark.parametrize("path", TRANSLATION_FILES, ids=lambda path: path.name)
def test_reconfigure_warning_placeholders_present(path: Path) -> None:
  """Ensure reconfigure warning translations keep all format placeholders."""  # noqa: E111

  payload = _load_translation(path)  # noqa: E111
  issues = payload.get("issues")  # noqa: E111
  assert isinstance(issues, dict)  # noqa: E111

  warning = issues.get("reconfigure_warnings")  # noqa: E111
  assert isinstance(warning, dict)  # noqa: E111

  description = warning.get("description")  # noqa: E111
  assert isinstance(description, str)  # noqa: E111

  for key in sorted(RECONFIGURE_WARNING_KEYS):  # noqa: E111
    assert f"{{{key}}}" in description, f"missing {{{key}}} in {path}"


@pytest.mark.parametrize("path", TRANSLATION_FILES, ids=lambda path: path.name)
def test_reconfigure_health_placeholders_present(path: Path) -> None:
  """Ensure reconfigure health translations keep all format placeholders."""  # noqa: E111

  payload = _load_translation(path)  # noqa: E111
  issues = payload.get("issues")  # noqa: E111
  assert isinstance(issues, dict)  # noqa: E111

  health = issues.get("reconfigure_health")  # noqa: E111
  assert isinstance(health, dict)  # noqa: E111

  description = health.get("description")  # noqa: E111
  assert isinstance(description, str)  # noqa: E111

  for key in sorted(RECONFIGURE_HEALTH_KEYS):  # noqa: E111
    assert f"{{{key}}}" in description, f"missing {{{key}}} in {path}"


@pytest.mark.parametrize("path", TRANSLATION_FILES, ids=lambda path: path.name)
def test_reconfigure_entity_placeholders_present(path: Path) -> None:
  """Ensure reconfigure entity profile translations include all placeholders."""  # noqa: E111

  payload = _load_translation(path)  # noqa: E111
  config_flow = payload.get("config")  # noqa: E111
  assert isinstance(config_flow, dict)  # noqa: E111

  steps = config_flow.get("step")  # noqa: E111
  assert isinstance(steps, dict)  # noqa: E111

  profile = steps.get("entity_profile")  # noqa: E111
  assert isinstance(profile, dict)  # noqa: E111

  description = profile.get("description")  # noqa: E111
  assert isinstance(description, str)  # noqa: E111

  for key in sorted(RECONFIGURE_ENTITY_KEYS):  # noqa: E111
    assert f"{{{key}}}" in description, f"missing {{{key}}} in {path}"
