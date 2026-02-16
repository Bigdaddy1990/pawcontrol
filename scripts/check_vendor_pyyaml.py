"""Monitor the vendored PyYAML release used by annotatedyaml.

This helper fetches the current PyPI release metadata and OSV vulnerability
records for PyYAML, compares them with the vendored version shipped under
``annotatedyaml/_vendor/yaml``, and reports drift or security issues. The
script is intentionally lightweight so it can run inside GitHub Actions on a
schedule without additional dependencies.
"""

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

from packaging.version import InvalidVersion, Version
from pip._vendor import requests

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
  """Raised when the monitoring routine cannot complete."""  # noqa: E111


@dataclass
class VulnerabilityRecord:
  """Details about a vulnerability affecting the vendored release."""  # noqa: E111

  identifier: str  # noqa: E111
  summary: str  # noqa: E111
  severity: str | None  # noqa: E111
  affected_version_range: str | None  # noqa: E111
  references: list[str]  # noqa: E111


@dataclass
class WheelProfile:
  """Wheel combination that should be tracked for availability."""  # noqa: E111

  python_tag: str  # noqa: E111
  platform_fragment: str  # noqa: E111


@dataclass
class WheelMatch:
  """Details about an available wheel for a tracked profile."""  # noqa: E111

  profile: WheelProfile  # noqa: E111
  release: Version | None  # noqa: E111
  filename: str  # noqa: E111
  url: str  # noqa: E111


@dataclass
class MonitoringResult:
  """Aggregated outcome of the monitoring run."""  # noqa: E111

  vendor_version: Version  # noqa: E111
  latest_release: Version | None  # noqa: E111
  latest_release_files: list[dict[str, Any]]  # noqa: E111
  vulnerabilities: list[VulnerabilityRecord]  # noqa: E111
  wheel_matches: list[WheelMatch]  # noqa: E111


def _parse_wheel_profile(value: str) -> WheelProfile:
  """Return a wheel profile parsed from the CLI representation."""  # noqa: E111

  if ":" not in value:  # noqa: E111
    raise argparse.ArgumentTypeError(
      "Wheel profile must follow <python_tag>:<platform_fragment> format."
    )
  python_tag, platform_fragment = value.split(":", 1)  # noqa: E111
  python_tag = python_tag.strip()  # noqa: E111
  platform_fragment = platform_fragment.strip()  # noqa: E111
  if not python_tag or not platform_fragment:  # noqa: E111
    raise argparse.ArgumentTypeError(
      "Wheel profile requires both a python tag and platform fragment."
    )
  return WheelProfile(python_tag=python_tag, platform_fragment=platform_fragment)  # noqa: E111


DEFAULT_WHEEL_PROFILES = (
  WheelProfile(python_tag="cp313", platform_fragment="manylinux"),
  WheelProfile(python_tag="cp313", platform_fragment="musllinux"),
)


def _normalise_wheel_profiles(args: argparse.Namespace) -> list[WheelProfile]:
  """Derive the list of wheel profiles that should be monitored."""  # noqa: E111

  if args.wheel_profile:  # noqa: E111
    return [
      WheelProfile(
        python_tag=profile.python_tag,
        platform_fragment=profile.platform_fragment,
      )
      for profile in args.wheel_profile
    ]
  if args.target_python_tag is not None or args.target_platform_fragment is not None:  # noqa: E111
    python_tag = args.target_python_tag or "cp313"
    platform_fragment = args.target_platform_fragment or "manylinux"
    return [WheelProfile(python_tag=python_tag, platform_fragment=platform_fragment)]
  return [  # noqa: E111
    WheelProfile(
      python_tag=profile.python_tag,
      platform_fragment=profile.platform_fragment,
    )
    for profile in DEFAULT_WHEEL_PROFILES
  ]


def parse_arguments() -> argparse.Namespace:
  """Parse command-line options."""  # noqa: E111

  parser = argparse.ArgumentParser(  # noqa: E111
    description=("Check the vendored PyYAML version against PyPI and OSV metadata."),
  )
  parser.add_argument(  # noqa: E111
    "--fail-on-outdated",
    action="store_true",
    help=(
      "Exit with status 1 when a newer stable PyYAML release is available on PyPI."
    ),
  )
  parser.add_argument(  # noqa: E111
    "--fail-severity",
    default="HIGH",
    choices=sorted(SEVERITY_ORDER),
    help=(
      "Lowest severity that triggers a non-zero exit when vulnerabilities "
      "affect the vendored version (default: HIGH)."
    ),
  )
  parser.add_argument(  # noqa: E111
    "--target-python-tag",
    default=None,
    help=(
      "Deprecated: prefer --wheel-profile. When provided, combines with "
      "--target-platform-fragment to build a single tracked profile."
    ),
  )
  parser.add_argument(  # noqa: E111
    "--target-platform-fragment",
    default=None,
    help=(
      "Deprecated: prefer --wheel-profile. When provided, combines with "
      "--target-python-tag to build a single tracked profile."
    ),
  )
  parser.add_argument(  # noqa: E111
    "--wheel-profile",
    action="append",
    default=[],
    type=_parse_wheel_profile,
    metavar="<python_tag>:<platform>",
    help=(
      "Wheel profile to track (repeatable). Defaults to cp313:manylinux "
      "and cp313:musllinux to cover PEP 600 and PEP 656 wheels."
    ),
  )
  parser.add_argument(  # noqa: E111
    "--metadata-path",
    help=(
      "Optional path where the monitoring summary should be written as "
      "JSON for downstream automation."
    ),
  )
  return parser.parse_args()  # noqa: E111


def load_vendor_version() -> Version:
  """Extract the vendored PyYAML version from annotatedyaml."""  # noqa: E111

  if not ANNOTATEDYAML_INIT.exists():  # noqa: E111
    raise MonitoringError(
      "annotatedyaml/_vendor/yaml/__init__.py is missing; vendored PyYAML "
      "cannot be inspected."
    )
  content = ANNOTATEDYAML_INIT.read_text(encoding="utf-8")  # noqa: E111
  match = re.search(r"__version__\s*=\s*[\"']([^\"']+)[\"']", content)  # noqa: E111
  if match is None:  # noqa: E111
    raise MonitoringError(
      "Could not locate __version__ assignment in vendored PyYAML module."
    )
  try:  # noqa: E111
    return Version(match.group(1))
  except InvalidVersion as exc:  # noqa: E111
    raise MonitoringError(
      f"Vendored PyYAML version '{match.group(1)}' is not a valid version."
    ) from exc


def fetch_pypi_metadata() -> dict[str, Any]:
  """Load the PyPI JSON metadata for PyYAML."""  # noqa: E111

  try:  # noqa: E111
    response = requests.get(PYPI_URL, timeout=20)
    response.raise_for_status()
  except requests.RequestException as exc:  # noqa: E111
    raise MonitoringError("Failed to fetch PyYAML metadata from PyPI") from exc
  data = response.json()  # noqa: E111
  if "releases" not in data:  # noqa: E111
    raise MonitoringError("PyPI response is missing release metadata.")
  return data  # noqa: E111


def select_latest_release(
  data: dict[str, Any],
) -> tuple[Version | None, list[dict[str, Any]]]:
  """Return the newest stable release and its file entries."""  # noqa: E111

  latest_version: Version | None = None  # noqa: E111
  latest_files: list[dict[str, Any]] = []  # noqa: E111
  for raw_version, files in data["releases"].items():  # noqa: E111
    try:
      parsed = Version(raw_version)  # noqa: E111
    except InvalidVersion:
      continue  # noqa: E111
    if parsed.is_prerelease or parsed.is_devrelease:
      continue  # noqa: E111
    if latest_version is None or parsed > latest_version:
      latest_version = parsed  # noqa: E111
      latest_files = files  # noqa: E111
  return latest_version, latest_files  # noqa: E111


def _convert_version(raw: str | None) -> Version | None:
  if raw in (None, "0"):  # noqa: E111
    return Version("0") if raw == "0" else None
  try:  # noqa: E111
    return Version(raw)
  except InvalidVersion:  # noqa: E111
    return None


def _range_contains_version(events: list[dict[str, str]], version: Version) -> bool:
  active_start: Version | None = None  # noqa: E111
  for event in events:  # noqa: E111
    if "introduced" in event:
      active_start = _convert_version(event.get("introduced"))  # noqa: E111
    elif "fixed" in event:
      if active_start is None:  # noqa: E111
        continue
      fixed_version = _convert_version(event.get("fixed"))  # noqa: E111
      if fixed_version is None:  # noqa: E111
        continue
      if active_start <= version < fixed_version:  # noqa: E111
        return True
      active_start = None  # noqa: E111
    elif "last_affected" in event:
      if active_start is None:  # noqa: E111
        continue
      last_version = _convert_version(event.get("last_affected"))  # noqa: E111
      if last_version is None:  # noqa: E111
        continue
      if active_start <= version <= last_version:  # noqa: E111
        return True
      active_start = None  # noqa: E111
  return bool(active_start is not None and active_start <= version)  # noqa: E111


def _format_range(events: list[dict[str, str]]) -> str | None:
  segments: list[str] = []  # noqa: E111
  active_start: str | None = None  # noqa: E111
  for event in events:  # noqa: E111
    if "introduced" in event:
      active_start = event["introduced"]  # noqa: E111
    elif "fixed" in event and active_start is not None:
      segments.append(f"[{active_start}, {event['fixed']})")  # noqa: E111
      active_start = None  # noqa: E111
    elif "last_affected" in event and active_start is not None:
      segments.append(f"[{active_start}, {event['last_affected']}]")  # noqa: E111
      active_start = None  # noqa: E111
  if not segments:  # noqa: E111
    return None
  return ", ".join(segments)  # noqa: E111


def _normalise_severity(raw: str | None) -> str | None:
  if raw is None:  # noqa: E111
    return None
  normalised = raw.strip().upper()  # noqa: E111
  if not normalised:  # noqa: E111
    return None
  if normalised == "MODERATE":  # noqa: E111
    normalised = "MEDIUM"
  return normalised if normalised in SEVERITY_ORDER else None  # noqa: E111


def _severity_from_cvss(score: float) -> str:
  if score >= 9.0:  # noqa: E111
    return "CRITICAL"
  if score >= 7.0:  # noqa: E111
    return "HIGH"
  if score >= 4.0:  # noqa: E111
    return "MEDIUM"
  if score > 0:  # noqa: E111
    return "LOW"
  return "LOW"  # noqa: E111


def _derive_severity(entry: dict[str, Any]) -> str:
  database_specific = entry.get("database_specific", {})  # noqa: E111
  severity = _normalise_severity(database_specific.get("severity"))  # noqa: E111
  if severity is not None:  # noqa: E111
    return severity
  severity_entries = entry.get("severity") or []  # noqa: E111
  highest_score: float | None = None  # noqa: E111
  for record in severity_entries:  # noqa: E111
    score = record.get("score")
    numeric: float | None
    if isinstance(score, (int, float)):
      numeric = float(score)  # noqa: E111
    elif isinstance(score, str):
      try:  # noqa: E111
        numeric = float(score)
      except ValueError:  # noqa: E111
        numeric = None
    else:
      numeric = None  # noqa: E111
    if numeric is None:
      continue  # noqa: E111
    if highest_score is None or numeric > highest_score:
      highest_score = numeric  # noqa: E111
  if highest_score is not None:  # noqa: E111
    return _severity_from_cvss(highest_score)
  return "CRITICAL"  # noqa: E111


def query_osv(vendor_version: Version) -> list[VulnerabilityRecord]:
  """Return vulnerabilities that still affect the vendored version."""  # noqa: E111

  payload = {  # noqa: E111
    "package": {"name": "PyYAML", "ecosystem": "PyPI"},
    "version": str(vendor_version),
  }
  try:  # noqa: E111
    response = requests.post(OSV_URL, json=payload, timeout=20)
    response.raise_for_status()
  except requests.RequestException as exc:  # noqa: E111
    raise MonitoringError("Failed to query OSV for PyYAML vulnerabilities") from exc
  data = response.json()  # noqa: E111
  entries: list[dict[str, Any]] = data.get("vulns") or data.get("vulnerabilities") or []  # noqa: E111
  results: list[VulnerabilityRecord] = []  # noqa: E111
  for entry in entries:  # noqa: E111
    affected = entry.get("affected", [])
    matches_version = False
    range_description: str | None = None
    for affected_entry in affected:
      for ranges in affected_entry.get("ranges", []):  # noqa: E111
        if ranges.get("type") != "ECOSYSTEM":
          continue  # noqa: E111
        events: list[dict[str, str]] = ranges.get("events", [])
        if _range_contains_version(events, vendor_version):
          matches_version = True  # noqa: E111
          if range_description is None:  # noqa: E111
            range_description = _format_range(events)
    if not matches_version:
      continue  # noqa: E111
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
  return results  # noqa: E111


def locate_target_wheel(
  data: dict[str, Any],
  *,
  python_tag: str,
  platform_fragment: str,
) -> tuple[Version | None, str, str]:
  """Find the newest release that ships a compatible wheel."""  # noqa: E111

  sorted_releases: list[tuple[Version, list[dict[str, Any]]]] = []  # noqa: E111
  for raw_version, files in data["releases"].items():  # noqa: E111
    try:
      parsed = Version(raw_version)  # noqa: E111
    except InvalidVersion:
      continue  # noqa: E111
    if parsed.is_prerelease or parsed.is_devrelease:
      continue  # noqa: E111
    sorted_releases.append((parsed, files))
  sorted_releases.sort(reverse=True)  # noqa: E111
  for version, files in sorted_releases:  # noqa: E111
    for file_entry in files:
      if file_entry.get("packagetype") != "bdist_wheel":  # noqa: E111
        continue
      filename = file_entry.get("filename", "")  # noqa: E111
      if (  # noqa: E111
        python_tag in filename
        and platform_fragment in filename
        and not file_entry.get("yanked", False)
      ):
        return version, filename, file_entry.get("url", "")
  return None, "", ""  # noqa: E111


def build_summary(result: MonitoringResult) -> str:
  """Compose a GitHub Actions step summary for the monitoring run."""  # noqa: E111

  latest_release_text = (  # noqa: E111
    f"`{result.latest_release}`" if result.latest_release is not None else "n/a"
  )
  summary_lines = [  # noqa: E111
    "## Vendored PyYAML status",
    "",
    f"* Vendored release: `{result.vendor_version}`",
    f"* Latest stable release on PyPI: {latest_release_text}",
  ]
  for match in result.wheel_matches:  # noqa: E111
    profile_label = f"{match.profile.python_tag} ({match.profile.platform_fragment})"
    if match.release is not None:
      summary_lines.append(  # noqa: E111
        "* ✅ Wheel for "
        f"`{profile_label}` discovered in PyYAML `{match.release}` - "
        "plan removal of the vendor copy."
      )
    else:
      summary_lines.append(  # noqa: E111
        "* ⚠️ No PyPI wheel matches the configured runner profile "
        f"`{profile_label}` yet; keep the vendor directory in place."
      )
  if result.vulnerabilities:  # noqa: E111
    summary_lines.append("*")
    summary_lines.append("* ⚠️ Vulnerabilities affecting the vendored release:")
    for vuln in result.vulnerabilities:
      severity = vuln.severity or "UNKNOWN"  # noqa: E111
      range_hint = (  # noqa: E111
        f" (affected range: {vuln.affected_version_range})"
        if vuln.affected_version_range
        else ""
      )
      summary_lines.append(  # noqa: E111
        f"  * `{vuln.identifier}` - {severity}{range_hint}: {vuln.summary}"
      )
      if vuln.references:  # noqa: E111
        summary_lines.append(f"    * References: {', '.join(vuln.references[:3])}")
  else:  # noqa: E111
    summary_lines.append(
      "* ✅ No published OSV vulnerabilities affect the vendored release."
    )
  summary_lines.append("")  # noqa: E111
  return "\n".join(summary_lines)  # noqa: E111


def build_metadata_document(result: MonitoringResult) -> dict[str, Any]:
  """Serialise the monitoring result into a JSON-serialisable mapping."""  # noqa: E111

  return {  # noqa: E111
    "vendor_version": str(result.vendor_version),
    "latest_release": str(result.latest_release)
    if result.latest_release is not None
    else None,
    "wheel_matches": [
      {
        "python_tag": match.profile.python_tag,
        "platform_fragment": match.profile.platform_fragment,
        "release": str(match.release) if match.release is not None else None,
        "filename": match.filename or None,
        "url": match.url or None,
      }
      for match in result.wheel_matches
    ],
    "vulnerabilities": [
      {
        "identifier": vuln.identifier,
        "summary": vuln.summary,
        "severity": vuln.severity,
        "affected_version_range": vuln.affected_version_range,
        "references": vuln.references,
      }
      for vuln in result.vulnerabilities
    ],
  }


def evaluate(
  *,
  fail_on_outdated: bool,
  fail_severity: str,
  wheel_profiles: list[WheelProfile],
) -> tuple[MonitoringResult, int]:
  """Run the monitoring routine and return the result plus exit code."""  # noqa: E111

  vendor_version = load_vendor_version()  # noqa: E111
  pypi_metadata = fetch_pypi_metadata()  # noqa: E111
  latest_release, latest_files = select_latest_release(pypi_metadata)  # noqa: E111
  vulnerabilities = query_osv(vendor_version)  # noqa: E111
  wheel_matches: list[WheelMatch] = []  # noqa: E111
  for profile in wheel_profiles:  # noqa: E111
    release, filename, url = locate_target_wheel(
      pypi_metadata,
      python_tag=profile.python_tag,
      platform_fragment=profile.platform_fragment,
    )
    wheel_matches.append(
      WheelMatch(profile=profile, release=release, filename=filename, url=url)
    )
  result = MonitoringResult(  # noqa: E111
    vendor_version=vendor_version,
    latest_release=latest_release,
    latest_release_files=latest_files,
    vulnerabilities=vulnerabilities,
    wheel_matches=wheel_matches,
  )

  exit_code = 0  # noqa: E111
  if vulnerabilities:  # noqa: E111
    highest_severity_value = max(
      SEVERITY_ORDER.get(vuln.severity or "", 0) for vuln in vulnerabilities
    )
    threshold_value = SEVERITY_ORDER.get(fail_severity.upper(), 3)
    if highest_severity_value >= threshold_value:
      print(  # noqa: E111
        "::error ::Vendored PyYAML is affected by at least one OSV advisory "
        f"with severity >= {fail_severity}."
      )
      exit_code = 1  # noqa: E111
    else:
      print(  # noqa: E111
        "::warning ::Vendored PyYAML is affected by OSV advisories, but the "
        f"severity stays below {fail_severity}."
      )
  else:  # noqa: E111
    print("::notice ::No OSV advisories currently affect the vendored PyYAML.")

  if latest_release is not None and latest_release > vendor_version:  # noqa: E111
    message = (
      "::warning ::Vendored PyYAML is older than the latest PyPI release "
      f"({vendor_version} < {latest_release})."
    )
    if fail_on_outdated:
      print(message.replace("::warning ::", "::error ::"))  # noqa: E111
      exit_code = 1  # noqa: E111
    else:
      print(message)  # noqa: E111
  else:  # noqa: E111
    print("::notice ::Vendored PyYAML matches the latest available release.")

  for match in wheel_matches:  # noqa: E111
    profile_label = f"{match.profile.python_tag} ({match.profile.platform_fragment})"
    if match.release is not None:
      release_url = f"https://pypi.org/project/PyYAML/{match.release}/"  # noqa: E111
      filename_hint = match.filename or "<unknown wheel>"  # noqa: E111
      print(  # noqa: E111
        "::notice ::Compatible PyYAML wheel discovered for "
        f"{profile_label} in release {match.release}: {filename_hint} - "
        "prepare vendor removal."
      )
      print(f"::notice ::Release notes: {release_url}")  # noqa: E111
      if match.url:  # noqa: E111
        print(f"::notice ::Download URL: {match.url}")
    else:
      print(  # noqa: E111
        "::notice ::No matching PyYAML wheel for the configured Home "
        f"Assistant runtime profile {profile_label} has been published yet."
      )
  return result, exit_code  # noqa: E111


def main() -> int:
  """Entry point for the monitoring script."""  # noqa: E111

  args = parse_arguments()  # noqa: E111
  wheel_profiles = _normalise_wheel_profiles(args)  # noqa: E111
  try:  # noqa: E111
    result, exit_code = evaluate(
      fail_on_outdated=args.fail_on_outdated,
      fail_severity=args.fail_severity,
      wheel_profiles=wheel_profiles,
    )
  except MonitoringError as exc:  # noqa: E111
    print(f"::error ::{exc}")
    return 2

  summary = build_summary(result)  # noqa: E111
  summary_path = os.environ.get("GITHUB_STEP_SUMMARY")  # noqa: E111
  if summary_path:  # noqa: E111
    with Path(summary_path).open("a", encoding="utf-8") as handle:
      handle.write(summary)  # noqa: E111
      if not summary.endswith("\n"):  # noqa: E111
        handle.write("\n")
  else:  # noqa: E111
    print(summary)
  if args.metadata_path:  # noqa: E111
    metadata = build_metadata_document(result)
    metadata_path = Path(args.metadata_path)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
      json.dumps(metadata, indent=2, sort_keys=True) + "\n",
      encoding="utf-8",
    )
  return exit_code  # noqa: E111


if __name__ == "__main__":
  sys.exit(main())  # noqa: E111
