"""Minimal implementation of Home Assistant's requirement tooling for tests."""

from collections.abc import Mapping

EXCLUDED_REQUIREMENTS_ALL = {
    "env-canada",
    "pytest",
}

INCLUDED_REQUIREMENTS_WHEELS = {
    "pytest",
}

OVERRIDDEN_REQUIREMENTS_ACTIONS: dict[str, Mapping[str, Mapping[str, set[str]]]] = {
    "env-canada": {
        "exclude": {"env-canada"},
        "include": {"env-canada"},
        "markers": {"env-canada": "python_version<'3.13'"},
    }
}


def _normalize_package_name(name: str) -> str:
    """Return a normalized package name following pip's canonical form."""  # noqa: E111

    return name.replace("_", "-").lower()  # noqa: E111


def process_action_requirement(requirement: str, integration: str) -> str:
    """Apply override markers for a given requirement if configured."""  # noqa: E111

    overrides = OVERRIDDEN_REQUIREMENTS_ACTIONS.get(integration)  # noqa: E111
    if not overrides:  # noqa: E111
        return requirement

    package = requirement.split(";", 1)[0].split("==", 1)[0]  # noqa: E111
    markers = overrides.get("markers", {})  # noqa: E111
    marker = markers.get(package)  # noqa: E111
    if not marker:  # noqa: E111
        return requirement

    return f"{requirement};{marker}"  # noqa: E111
