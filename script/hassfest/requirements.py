"""Requirement validation helpers for hassfest tests."""

from __future__ import annotations

from collections.abc import Iterable
from importlib.metadata import files

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

from .model import Integration

FORBIDDEN_PACKAGE_NAMES: set[str] = {"tests"}
FORBIDDEN_TOP_LEVEL_FILES: set[str] = {"py.typed"}
PACKAGE_CHECK_PREPARE_UPDATE: dict[str, int] = {}
PACKAGE_CHECK_VERSION_RANGE: dict[str, str] = {}
_packages_checked_files_cache: dict[str, dict[str, set[str]]] = {}


def _is_core_integration(integration: Integration) -> bool:
    return "homeassistant/components" in str(integration.path)


def validate_requirements_format(integration: Integration) -> bool:
    """Validate pinned requirements for an integration."""

    manifest_requirements = integration.manifest.get("requirements", [])
    ok = True

    for raw_req in manifest_requirements:
        if " ==" in raw_req or "== " in raw_req:
            integration.add_error(
                "requirements", f'Requirement "{raw_req}" contains a space'
            )
            ok = False
            continue

        if raw_req.startswith("git+"):
            if _is_core_integration(integration):
                integration.add_error(
                    "requirements",
                    f"Requirement {raw_req} must pin a version for core integrations.",
                )
                ok = False
            continue

        try:
            requirement = Requirement(raw_req)
        except Exception as err:  # pragma: no cover - defensive
            integration.add_error(
                "requirements", f"Unable to parse requirement {raw_req}: {err}"
            )
            ok = False
            continue

        spec_set = requirement.specifier
        if _is_core_integration(integration):
            equality_specs = [spec for spec in spec_set if spec.operator == "=="]
            if not equality_specs:
                integration.add_error(
                    "requirements",
                    f'Requirement {raw_req} need to be pinned "<pkg name>==<version>".',
                )
                ok = False
            else:
                for spec in equality_specs:
                    try:
                        Version(spec.version)
                    except InvalidVersion:
                        integration.add_error(
                            "requirements",
                            f"Unable to parse package version ({spec.version}) for {requirement.name}.",
                        )
                        ok = False
        else:
            # For custom integrations we still validate equality specifiers if present
            for spec in spec_set:
                if spec.operator == "==":
                    try:
                        Version(spec.version)
                    except InvalidVersion:
                        integration.add_error(
                            "requirements",
                            f"Unable to parse package version ({spec.version}) for {requirement.name}.",
                        )
                        ok = False

    return ok


def _parse_specifier(version: str) -> SpecifierSet:
    return SpecifierSet(version.split(";", 1)[0])


def check_dependency_version_range(
    integration: Integration,
    package: str,
    *,
    pkg: str,
    version: str,
    package_exceptions: Iterable[str],
) -> bool:
    """Validate that the dependency range includes the prepare-update version."""

    target_version = PACKAGE_CHECK_PREPARE_UPDATE.get(pkg)
    if target_version is None:
        return True

    try:
        specifier = _parse_specifier(version)
    except Exception:
        integration.add_error(
            "requirements", f"Invalid version range specified: {version}"
        )
        return False

    allowed = Version(str(target_version)) in specifier
    if not allowed:
        integration.add_error(
            "requirements",
            f"Package version range {version} does not include {target_version}",
        )
    return allowed


def _compute_package_metadata(pkg: str) -> dict[str, set[str]]:
    cache = _packages_checked_files_cache.get(pkg)
    if cache is not None:
        return cache

    top_level: set[str] = set()
    file_names: set[str] = set()
    for package_path in files(pkg) or []:
        parts = package_path.parts
        if not parts:
            continue
        top = parts[0]
        if top.endswith(".dist-info"):
            continue
        if "/" in str(package_path):
            top_level.add(top)
        else:
            file_names.add(top)
    cache = {"top_level": top_level, "file_names": file_names}
    _packages_checked_files_cache[pkg] = cache
    return cache


def check_dependency_files(
    integration: Integration,
    package: str,
    pkg: str,
    package_exceptions: Iterable[str],
) -> bool:
    """Validate dependency file structure for forbidden directories/files."""

    metadata = _compute_package_metadata(pkg)
    top_level = metadata["top_level"]
    file_names = metadata["file_names"]

    ok = True
    forbidden_hits = top_level & FORBIDDEN_PACKAGE_NAMES
    for entry in forbidden_hits:
        message = (
            f"Package {pkg} has a forbidden top level directory '{entry}' in {package}"
        )
        ok = False
        if pkg in package_exceptions:
            integration.add_warning("requirements", message)
        else:
            integration.add_error("requirements", message)

    forbidden_files = file_names & FORBIDDEN_TOP_LEVEL_FILES
    for entry in forbidden_files:
        integration.add_error(
            "requirements",
            f"Package {pkg} has a forbidden file '{entry}' in {package}",
        )
        ok = False

    return ok


__all__ = [
    "FORBIDDEN_PACKAGE_NAMES",
    "PACKAGE_CHECK_PREPARE_UPDATE",
    "PACKAGE_CHECK_VERSION_RANGE",
    "_packages_checked_files_cache",
    "check_dependency_files",
    "check_dependency_version_range",
    "validate_requirements_format",
]
