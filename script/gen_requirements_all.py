"""Minimal subset of Home Assistant's gen_requirements_all helpers used in tests."""

from __future__ import annotations

from collections.abc import Mapping

from packaging.utils import canonicalize_name

EXCLUDED_REQUIREMENTS_ALL: frozenset[str] = frozenset(
    {
        "env-canada",
        "homeassistant",
        "paho-mqtt",
    }
)
"""Normalized requirement names that are excluded from default processing."""

INCLUDED_REQUIREMENTS_WHEELS: frozenset[str] = frozenset({"env-canada"})
"""Requirement names that should always be available as wheels."""

OVERRIDDEN_REQUIREMENTS_ACTIONS: dict[str, dict[str, Mapping[str, str] | set[str]]] = {
    "default": {
        "exclude": set(),
        "include": set(),
        "markers": {},
    }
}
"""Per-action requirement overrides used by the requirements script."""


def _normalize_package_name(name: str) -> str:
    """Return a normalized package name following PEP 503 rules."""

    return canonicalize_name(name)


def _extract_requirement_name(requirement: str) -> str:
    """Extract the package name from a requirement string."""

    requirement = requirement.strip()
    if not requirement:
        return ""

    requirement = requirement.split(";", 1)[0]

    if "[" in requirement:
        requirement = requirement.split("[", 1)[0]

    for separator in ("==", "~=", ">=", "<=", ">", "<", "!="):
        if separator in requirement:
            requirement = requirement.split(separator, 1)[0]
            break

    return _normalize_package_name(requirement.strip())


def process_action_requirement(requirement: str, action: str) -> str:
    """Apply any override markers for a requirement used in a specific action."""

    overrides = OVERRIDDEN_REQUIREMENTS_ACTIONS.get(action)
    if not overrides:
        return requirement

    normalized_name = _extract_requirement_name(requirement)
    markers = overrides.get("markers", {})
    marker = markers.get(normalized_name)
    if not marker:
        return requirement

    if ";" in requirement:
        base, existing_marker = requirement.split(";", 1)
        combined_marker = f"{existing_marker} and {marker}"
        return f"{base};{combined_marker}"

    return f"{requirement};{marker}"


__all__ = [
    "EXCLUDED_REQUIREMENTS_ALL",
    "INCLUDED_REQUIREMENTS_WHEELS",
    "OVERRIDDEN_REQUIREMENTS_ACTIONS",
    "_normalize_package_name",
    "process_action_requirement",
]
