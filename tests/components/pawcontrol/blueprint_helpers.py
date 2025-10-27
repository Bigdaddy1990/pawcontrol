"""Shared helpers for loading PawControl blueprints inside tests."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from homeassistant.core import HomeAssistant

BLUEPRINT_RELATIVE_PATH: Final[str] = (
    "automation/pawcontrol/resilience_escalation_followup.yaml"
)

DEFAULT_RESILIENCE_BLUEPRINT_CONTEXT: Final[dict[str, object]] = {
    "statistics_sensor": "sensor.pawcontrol_statistics",
    "escalation_script": "script.pawcontrol_test_resilience_escalation",
    "guard_followup_actions": [
        {"service": "test.guard_followup", "data": {"reason": "guard"}},
    ],
    "breaker_followup_actions": [
        {"service": "test.breaker_followup", "data": {"reason": "breaker"}},
    ],
    "watchdog_interval_minutes": 0,
    "manual_check_event": "pawcontrol_resilience_check",
    "manual_guard_event": "pawcontrol_manual_guard",
    "manual_breaker_event": "pawcontrol_manual_breaker",
}


def _find_repo_root(marker: str = "pyproject.toml") -> Path:
    """Return the repository root by walking parents until a marker is found."""

    candidate = Path(__file__).resolve().parent
    while not (candidate / marker).exists():
        parent = candidate.parent
        if parent == candidate:
            raise FileNotFoundError(
                "Repository root with pyproject.toml not found while loading blueprint"
            )
        candidate = parent
    return candidate


def get_blueprint_source(relative_path: str | Path) -> Path:
    """Return the absolute path to a blueprint within the repository."""

    repo_root = _find_repo_root()
    blueprint_path = repo_root / "blueprints" / Path(relative_path)
    if not blueprint_path.is_file():
        raise FileNotFoundError(
            f"Expected blueprint at {blueprint_path} to exist for tests"
        )
    return blueprint_path


def ensure_blueprint_imported(hass: HomeAssistant, relative_path: str | Path) -> Path:
    """Copy the requested blueprint into the Home Assistant instance config."""

    source_path = get_blueprint_source(relative_path)
    target_path = Path(hass.config.path("blueprints")) / Path(relative_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
    return target_path
