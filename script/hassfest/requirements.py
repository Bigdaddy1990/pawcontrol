"""Requirement validation helpers for hassfest tests."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

from .model import Integration

FORBIDDEN_PACKAGE_NAMES: set[str] = {"tests", "testing"}
PACKAGE_CHECK_VERSION_RANGE: dict[str, str] = {}
PACKAGE_CHECK_PREPARE_UPDATE: dict[str, int] = {}
_packages_checked_files_cache: dict[str, dict[str, set[str]]] = {}


@dataclass(frozen=True)
class PackagePath:
    """Simple representation of a package file path."""

    path: str

    @property
    def parts(self) -> tuple[str, ...]:
        return tuple(part for part in self.path.split("/") if part)

    def __str__(self) -> str:  # pragma: no cover - debugging helper
        return self.path


def _normalize_requirement(requirement: str) -> str:
    return requirement.strip()


def _iter_requirement_entries(integration: Integration) -> Iterable[str]:
    return integration.manifest.get("requirements", [])


def _has_spacing_issue(requirement: str) -> bool:
    return any(sep in requirement for sep in (" == ", " ~= ", " >= ", " <= ", " != "))


def _extract_version_portion(requirement: str) -> str:
    if "==" not in requirement:
        return ""
    return requirement.split("==", 1)[1]


def validate_requirements_format(integration: Integration) -> bool:
    """Validate requirement strings follow hassfest conventions."""

    valid = True
    is_custom = integration.is_custom_integration

    for requirement in _iter_requirement_entries(integration):
        requirement = _normalize_requirement(requirement)

        if requirement.startswith("git+") and not is_custom:
            integration.add_error(
                "Requirements for core integrations may not reference Git repositories"
            )
            valid = False
            continue

        if _has_spacing_issue(requirement):
            integration.add_error(f'Requirement "{requirement}" contains a space')
            valid = False
            continue

        if not is_custom and "==" not in requirement:
            integration.add_error(
                f'Requirement {requirement} need to be pinned "<pkg name>==<version>".'
            )
            valid = False
            continue

        if "==" in requirement:
            version = _extract_version_portion(requirement)
            try:
                Version(version.split(";", 1)[0].split(",", 1)[0])
            except InvalidVersion:
                integration.add_error(
                    f"Unable to parse package version ({version}) for {requirement.split('==', 1)[0]}."
                )
                valid = False

    return valid


def check_dependency_version_range(
    integration: Integration,
    package: str,
    *,
    pkg: str,
    version: str | None,
    package_exceptions: Iterable[str],
) -> bool:
    """Ensure dependency version ranges allow the upcoming release version."""

    target_major = PACKAGE_CHECK_PREPARE_UPDATE.get(pkg)
    if not target_major or pkg in package_exceptions or not version:
        return True

    spec = version.split(";", 1)[0]
    try:
        specifier_set = SpecifierSet(spec)
    except Exception:  # pragma: no cover - defensive
        integration.add_error(
            f"Invalid version specifier {version} for {pkg} in {package}"
        )
        return False

    test_version = Version(f"{target_major}.0")
    return test_version in specifier_set


def files(package: str) -> list[PackagePath]:  # pragma: no cover - patched in tests
    """Return files contained in a package distribution.

    The real Home Assistant implementation inspects installed distributions. For
    the purposes of these tests the function is patched, but we provide a basic
    fallback that returns an empty list.
    """

    return []


def check_dependency_files(
    integration: Integration,
    package: str,
    pkg: str,
    package_exceptions: Iterable[str],
) -> bool:
    """Validate that dependency packages do not ship forbidden top level names."""

    if pkg in package_exceptions:
        return True

    cached = _packages_checked_files_cache.get(pkg)
    if cached is not None:
        top_level = cached["top_level"]
    else:
        top_level = {path.parts[0] for path in files(pkg) if path.parts}
        _packages_checked_files_cache[pkg] = {"top_level": top_level}

    violations = sorted(top_level & FORBIDDEN_PACKAGE_NAMES)
    for violation in violations:
        integration.add_error(
            f"Package {pkg} has a forbidden top level directory '{violation}' in {package}"
        )

    return not violations


__all__ = [
    "FORBIDDEN_PACKAGE_NAMES",
    "PACKAGE_CHECK_PREPARE_UPDATE",
    "PACKAGE_CHECK_VERSION_RANGE",
    "PackagePath",
    "_packages_checked_files_cache",
    "check_dependency_files",
    "check_dependency_version_range",
    "files",
    "validate_requirements_format",
]
