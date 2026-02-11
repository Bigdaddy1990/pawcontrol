"""Regression tests for translation placeholders used by repairs telemetry."""

from __future__ import annotations

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
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", TRANSLATION_FILES, ids=lambda path: path.name)
def test_reconfigure_warning_placeholders_present(path: Path) -> None:
    """Ensure reconfigure warning translations keep all format placeholders."""

    payload = _load_translation(path)
    issues = payload.get("issues")
    assert isinstance(issues, dict)

    warning = issues.get("reconfigure_warnings")
    assert isinstance(warning, dict)

    description = warning.get("description")
    assert isinstance(description, str)

    for key in sorted(RECONFIGURE_WARNING_KEYS):
        assert f"{{{key}}}" in description, f"missing {{{key}}} in {path}"


@pytest.mark.parametrize("path", TRANSLATION_FILES, ids=lambda path: path.name)
def test_reconfigure_health_placeholders_present(path: Path) -> None:
    """Ensure reconfigure health translations keep all format placeholders."""

    payload = _load_translation(path)
    issues = payload.get("issues")
    assert isinstance(issues, dict)

    health = issues.get("reconfigure_health")
    assert isinstance(health, dict)

    description = health.get("description")
    assert isinstance(description, str)

    for key in sorted(RECONFIGURE_HEALTH_KEYS):
        assert f"{{{key}}}" in description, f"missing {{{key}}} in {path}"


@pytest.mark.parametrize("path", TRANSLATION_FILES, ids=lambda path: path.name)
def test_reconfigure_entity_placeholders_present(path: Path) -> None:
    """Ensure reconfigure entity profile translations include all placeholders."""

    payload = _load_translation(path)
    config_flow = payload.get("config")
    assert isinstance(config_flow, dict)

    steps = config_flow.get("step")
    assert isinstance(steps, dict)

    profile = steps.get("entity_profile")
    assert isinstance(profile, dict)

    description = profile.get("description")
    assert isinstance(description, str)

    for key in sorted(RECONFIGURE_ENTITY_KEYS):
        assert f"{{{key}}}" in description, f"missing {{{key}}} in {path}"
