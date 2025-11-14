"""Monitor the vendored PyYAML release used by annotatedyaml.

This helper fetches the current PyPI release metadata and OSV vulnerability
records for PyYAML, compares them with the vendored version shipped under
``annotatedyaml/_vendor/yaml``, and reports drift or security issues. The
script is intentionally lightweight so it can run inside GitHub Actions on a
schedule without additional dependencies.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pip._vendor import requests
from pip._vendor.packaging.version import InvalidVersion, Version

ANNOTATEDYAML_INIT = Path("annotatedyaml/_vendor/yaml/__init__.py")
PYPI_URL = "https://pypi.org/pypi/PyYAML/json"
OSV_URL = "https://api.osv.dev/v1/query"

SEVERITY_ORDER: dict[str, int] = {
    "CRITICAL": 4,
    "HIGH": 3,
    "MODERATE": 2,
    "MEDIUM": 2,
    "LOW": 1,
}


class MonitoringError(RuntimeError):
    """Raised when the monitoring routine cannot complete."""


@dataclass
class VulnerabilityRecord:
    """Details about a vulnerability affecting the vendored release."""

    identifier: str
    summary: str
    severity: str | None
    affected_version_range: str | None
    references: list[str]


@dataclass
class MonitoringResult:
    """Aggregated outcome of the monitoring run."""

    vendor_version: Version
    latest_release: Version | None
    latest_release_files: list[dict[str, Any]]
    vulnerabilities: list[VulnerabilityRecord]
    target_wheel_release: Version | None
    target_wheel_platform: str


def parse_arguments() -> argparse.Namespace:
    """Parse command-line options."""

    parser = argparse.ArgumentParser(
        description=(
            "Check the vendored PyYAML version against PyPI and OSV metadata."
        ),
    )
    parser.add_argument(
        "--fail-on-outdated",
        action="store_true",
        help=(
            "Exit with status 1 when a newer stable PyYAML release is available "
            "on PyPI."
        ),
    )
    parser.add_argument(
        "--fail-severity",
        default="HIGH",
        choices=sorted(SEVERITY_ORDER),
        help=(
            "Lowest severity that triggers a non-zero exit when vulnerabilities "
            "affect the vendored version (default: HIGH)."
        ),
    )
    parser.add_argument(
        "--target-python-tag",
        default="cp313",
        help=(
            "Wheel tag that signals Home Assistant can consume the upstream "
            "binary without a source build (default: cp313)."
        ),
    )
    parser.add_argument(
        "--target-platform-fragment",
        default="manylinux",
        help=(
            "Substring that must be present in the wheel filename to consider "
            "it suitable for Home Assistant runners (default: manylinux)."
        ),
    )
    return parser.parse_args()


def load_vendor_version() -> Version:
    """Extract the vendored PyYAML version from annotatedyaml."""

    if not ANNOTATEDYAML_INIT.exists():
        raise MonitoringError(
            "annotatedyaml/_vendor/yaml/__init__.py is missing; vendored PyYAML "
            "cannot be inspected."
        )
    content = ANNOTATEDYAML_INIT.read_text(encoding="utf-8")
    match = re.search(r"__version__\s*=\s*\"([^\"]+)\"", content)
    if match is None:
        raise MonitoringError(
            "Could not locate __version__ assignment in vendored PyYAML module."
        )
    try:
        return Version(match.group(1))
    except InvalidVersion as exc:
        raise MonitoringError(
            f"Vendored PyYAML version '{match.group(1)}' is not a valid version."
        ) from exc


def fetch_pypi_metadata() -> dict[str, Any]:
    """Load the PyPI JSON metadata for PyYAML."""

    try:
        response = requests.get(PYPI_URL, timeout=20)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise MonitoringError("Failed to fetch PyYAML metadata from PyPI") from exc
    data = response.json()
    if "releases" not in data:
        raise MonitoringError("PyPI response is missing release metadata.")
    return data


def select_latest_release(
    data: dict[str, Any],
) -> tuple[Version | None, list[dict[str, Any]]]:
    """Return the newest stable release and its file entries."""

    latest_version: Version | None = None
    latest_files: list[dict[str, Any]] = []
    for raw_version, files in data["releases"].items():
        try:
            parsed = Version(raw_version)
        except InvalidVersion:
            continue
        if parsed.is_prerelease or parsed.is_devrelease:
            continue
        if latest_version is None or parsed > latest_version:
            latest_version = parsed
            latest_files = files
    return latest_version, latest_files


def _convert_version(raw: str | None) -> Version | None:
    if raw in (None, "0"):
        return Version("0") if raw == "0" else None
    try:
        return Version(raw)
    except InvalidVersion:
        return None


def _range_contains_version(events: list[dict[str, str]], version: Version) -> bool:
    active_start: Version | None = None
    for event in events:
        if "introduced" in event:
            active_start = _convert_version(event.get("introduced"))
        elif "fixed" in event:
            if active_start is None:
                continue
            fixed_version = _convert_version(event.get("fixed"))
            if fixed_version is None:
                continue
            if active_start <= version < fixed_version:
                return True
            active_start = None
        elif "last_affected" in event:
            if active_start is None:
                continue
            last_version = _convert_version(event.get("last_affected"))
            if last_version is None:
                continue
            if active_start <= version <= last_version:
                return True
            active_start = None
    return bool(active_start is not None and active_start <= version)


def _format_range(events: list[dict[str, str]]) -> str | None:
    segments: list[str] = []
    active_start: str | None = None
    for event in events:
        if "introduced" in event:
            active_start = event["introduced"]
        elif "fixed" in event and active_start is not None:
            segments.append(f"[{active_start}, {event['fixed']})")
            active_start = None
        elif "last_affected" in event and active_start is not None:
            segments.append(f"[{active_start}, {event['last_affected']}]")
            active_start = None
    if not segments:
        return None
    return ", ".join(segments)


def _normalise_severity(raw: str | None) -> str | None:
    if raw is None:
        return None
    normalised = raw.strip().upper()
    if not normalised:
        return None
    if normalised == "MODERATE":
        normalised = "MEDIUM"
    return normalised if normalised in SEVERITY_ORDER else None


def _severity_from_cvss(score: float) -> str:
    if score >= 9.0:
        return "CRITICAL"
    if score >= 7.0:
        return "HIGH"
    if score >= 4.0:
        return "MEDIUM"
    if score > 0:
        return "LOW"
    return "LOW"


def _derive_severity(entry: dict[str, Any]) -> str:
    database_specific = entry.get("database_specific", {})
    severity = _normalise_severity(database_specific.get("severity"))
    if severity is not None:
        return severity
    severity_entries = entry.get("severity") or []
    highest_score: float | None = None
    for record in severity_entries:
        score = record.get("score")
        numeric: float | None
        if isinstance(score, (int, float)):
            numeric = float(score)
        elif isinstance(score, str):
            try:
                numeric = float(score)
            except ValueError:
                numeric = None
        else:
            numeric = None
        if numeric is None:
            continue
        if highest_score is None or numeric > highest_score:
            highest_score = numeric
    if highest_score is not None:
        return _severity_from_cvss(highest_score)
    return "CRITICAL"


def query_osv(vendor_version: Version) -> list[VulnerabilityRecord]:
    """Return vulnerabilities that still affect the vendored version."""

    payload = {
        "package": {"name": "PyYAML", "ecosystem": "PyPI"},
        "version": str(vendor_version),
    }
    try:
        response = requests.post(OSV_URL, json=payload, timeout=20)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise MonitoringError("Failed to query OSV for PyYAML vulnerabilities") from exc
    data = response.json()
    entries: list[dict[str, Any]] = (
        data.get("vulns") or data.get("vulnerabilities") or []
    )
    results: list[VulnerabilityRecord] = []
    for entry in entries:
        affected = entry.get("affected", [])
        matches_version = False
        range_description: str | None = None
        for affected_entry in affected:
            for ranges in affected_entry.get("ranges", []):
                if ranges.get("type") != "ECOSYSTEM":
                    continue
                events: list[dict[str, str]] = ranges.get("events", [])
                if _range_contains_version(events, vendor_version):
                    matches_version = True
                    if range_description is None:
                        range_description = _format_range(events)
        if not matches_version:
            continue
        severity = _derive_severity(entry)
        references = [
            ref.get("url") for ref in entry.get("references", []) if ref.get("url")
        ]
        results.append(
            VulnerabilityRecord(
                identifier=entry.get("id", "unknown"),
                summary=entry.get("summary", "No summary provided."),
                severity=severity,
                affected_version_range=range_description,
                references=references,
            )
        )
    return results


def locate_target_wheel(
    data: dict[str, Any],
    *,
    python_tag: str,
    platform_fragment: str,
) -> tuple[Version | None, str]:
    """Find the newest release that ships a compatible wheel."""

    sorted_releases: list[tuple[Version, list[dict[str, Any]]]] = []
    for raw_version, files in data["releases"].items():
        try:
            parsed = Version(raw_version)
        except InvalidVersion:
            continue
        if parsed.is_prerelease or parsed.is_devrelease:
            continue
        sorted_releases.append((parsed, files))
    sorted_releases.sort(reverse=True)
    for version, files in sorted_releases:
        for file_entry in files:
            if file_entry.get("packagetype") != "bdist_wheel":
                continue
            filename = file_entry.get("filename", "")
            if (
                python_tag in filename
                and platform_fragment in filename
                and not file_entry.get("yanked", False)
            ):
                return version, filename
    return None, ""


def build_summary(result: MonitoringResult) -> str:
    """Compose a GitHub Actions step summary for the monitoring run."""

    latest_release_text = (
        f"`{result.latest_release}`" if result.latest_release is not None else "n/a"
    )
    summary_lines = [
        "## Vendored PyYAML status",
        "",
        f"* Vendored release: `{result.vendor_version}`",
        f"* Latest stable release on PyPI: {latest_release_text}",
    ]
    if result.target_wheel_release is not None:
        summary_lines.append(
            f"* ✅ Wheel for `{result.target_wheel_platform}` discovered in PyYAML "
            f"`{result.target_wheel_release}` - plan removal of the vendor copy."
        )
    else:
        summary_lines.append(
            "* ⚠️ No PyPI wheel matches the configured Home Assistant runner profile yet; "
            "keep the vendor directory in place."
        )
    if result.vulnerabilities:
        summary_lines.append("*")
        summary_lines.append("* ⚠️ Vulnerabilities affecting the vendored release:")
        for vuln in result.vulnerabilities:
            severity = vuln.severity or "UNKNOWN"
            range_hint = (
                f" (affected range: {vuln.affected_version_range})"
                if vuln.affected_version_range
                else ""
            )
            summary_lines.append(
                f"  * `{vuln.identifier}` - {severity}{range_hint}: {vuln.summary}"
            )
            if vuln.references:
                summary_lines.append(
                    f"    * References: {', '.join(vuln.references[:3])}"
                )
    else:
        summary_lines.append(
            "* ✅ No published OSV vulnerabilities affect the vendored release."
        )
    summary_lines.append("")
    return "\n".join(summary_lines)


def evaluate(
    *,
    fail_on_outdated: bool,
    fail_severity: str,
    python_tag: str,
    platform_fragment: str,
) -> tuple[MonitoringResult, int]:
    """Run the monitoring routine and return the result plus exit code."""

    vendor_version = load_vendor_version()
    pypi_metadata = fetch_pypi_metadata()
    latest_release, latest_files = select_latest_release(pypi_metadata)
    vulnerabilities = query_osv(vendor_version)
    target_release, wheel_filename = locate_target_wheel(
        pypi_metadata,
        python_tag=python_tag,
        platform_fragment=platform_fragment,
    )
    result = MonitoringResult(
        vendor_version=vendor_version,
        latest_release=latest_release,
        latest_release_files=latest_files,
        vulnerabilities=vulnerabilities,
        target_wheel_release=target_release,
        target_wheel_platform=f"{python_tag} ({platform_fragment})",
    )

    exit_code = 0
    if vulnerabilities:
        highest_severity_value = max(
            SEVERITY_ORDER.get(vuln.severity or "", 0) for vuln in vulnerabilities
        )
        threshold_value = SEVERITY_ORDER.get(fail_severity.upper(), 3)
        if highest_severity_value >= threshold_value:
            print(
                "::error ::Vendored PyYAML is affected by at least one OSV advisory "
                f"with severity >= {fail_severity}."
            )
            exit_code = 1
        else:
            print(
                "::warning ::Vendored PyYAML is affected by OSV advisories, but the "
                f"severity stays below {fail_severity}."
            )
    else:
        print("::notice ::No OSV advisories currently affect the vendored PyYAML.")

    if latest_release is not None and latest_release > vendor_version:
        message = (
            "::warning ::Vendored PyYAML is older than the latest PyPI release "
            f"({vendor_version} < {latest_release})."
        )
        if fail_on_outdated:
            print(message.replace("::warning ::", "::error ::"))
            exit_code = 1
        else:
            print(message)
    else:
        print("::notice ::Vendored PyYAML matches the latest available release.")

    if target_release is not None:
        release_url = f"https://pypi.org/project/PyYAML/{target_release}/"
        print(
            "::notice ::Compatible PyYAML wheel discovered in release "
            f"{target_release}: {wheel_filename} - prepare vendor removal."
        )
        print(f"::notice ::Release notes: {release_url}")
    else:
        print(
            "::notice ::No matching PyYAML wheel for the configured Home Assistant "
            "runtime profile has been published yet."
        )
    return result, exit_code


def main() -> int:
    """Entry point for the monitoring script."""

    args = parse_arguments()
    try:
        result, exit_code = evaluate(
            fail_on_outdated=args.fail_on_outdated,
            fail_severity=args.fail_severity,
            python_tag=args.target_python_tag,
            platform_fragment=args.target_platform_fragment,
        )
    except MonitoringError as exc:
        print(f"::error ::{exc}")
        return 2

    summary = build_summary(result)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as handle:
            handle.write(summary)
            if not summary.endswith("\n"):
                handle.write("\n")
    else:
        print(summary)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
