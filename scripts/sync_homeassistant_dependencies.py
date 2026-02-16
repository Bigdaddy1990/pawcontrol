"""Synchronise dependencies with the upstream Home Assistant repository."""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile
import tomllib

from packaging.requirements import Requirement
from packaging.specifiers import Specifier
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version
from pip._vendor import requests

from scripts import check_vendor_pyyaml as vendor_monitor

# Paths relative to the Home Assistant core repository root.
HA_REQUIREMENTS = "requirements.txt"
HA_REQUIREMENTS_TEST = "requirements_test.txt"
HA_PACKAGE_CONSTRAINTS = "homeassistant/package_constraints.txt"
HA_PYPROJECT = "pyproject.toml"

VENDOR_ROOT = Path("annotatedyaml/_vendor")
VENDOR_LICENSE = VENDOR_ROOT / "PyYAML_LICENSE"
VENDOR_PACKAGE = VENDOR_ROOT / "yaml"
DEFAULT_METADATA_PATH = Path("generated/vendor_pyyaml_status.json")

# Default branch used when downloading reference files from GitHub.
DEFAULT_REFERENCE_URL = "https://raw.githubusercontent.com/home-assistant/core/dev"


@dataclass(frozen=True)
class ReferenceRequirement:
  """Reference requirement definition sourced from Home Assistant."""  # noqa: E111

  requirement: Requirement  # noqa: E111

  @property  # noqa: E111
  def specifier(self) -> str:  # noqa: E111
    return str(self.requirement.specifier)

  @property  # noqa: E111
  def marker(self) -> str | None:  # noqa: E111
    return str(self.requirement.marker) if self.requirement.marker else None

  @property  # noqa: E111
  def version_hint(self) -> Version | None:  # noqa: E111
    return highest_version(self.requirement.specifier)


class ReferenceLoader:
  """Load reference files from a local checkout or GitHub."""  # noqa: E111

  def __init__(self, *, root: Path | None, base_url: str) -> None:  # noqa: E111
    self._root = root
    self._base_url = base_url.rstrip("/")

  def load_text(self, relative: str) -> str:  # noqa: E111
    if self._root is not None:
      return (self._root / relative).read_text(encoding="utf-8")  # noqa: E111
    url = f"{self._base_url}/{relative}"
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return response.text


class DependencySynchroniser:
  """Synchronise local dependency files against Home Assistant references."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    *,
    loader: ReferenceLoader,
    manifest_path: Path,
    requirements_files: Iterable[Path],
    metadata_path: Path,
  ) -> None:
    self._loader = loader
    self._manifest_path = manifest_path
    self._requirements_files = list(requirements_files)
    self._metadata_path = metadata_path

  def load_reference_requirements(self) -> dict[str, ReferenceRequirement]:  # noqa: E111
    """Return a mapping of canonical package names to reference specs."""

    mapping: dict[str, ReferenceRequirement] = {}
    for relative in (
      HA_REQUIREMENTS,
      HA_REQUIREMENTS_TEST,
      HA_PACKAGE_CONSTRAINTS,
    ):
      text = self._loader.load_text(relative)  # noqa: E111
      update_mapping_from_lines(mapping, text.splitlines())  # noqa: E111

    pyproject_text = self._loader.load_text(HA_PYPROJECT)
    project_data = tomllib.loads(pyproject_text)
    for requirement in project_data.get("project", {}).get("dependencies", []):
      update_mapping(mapping, Requirement(requirement))  # noqa: E111

    return mapping

  def update_manifest_requirements(  # noqa: E111
    self,
    *,
    reference: Mapping[str, ReferenceRequirement],
  ) -> bool:
    """Update manifest requirements to match Home Assistant versions."""

    data = json.loads(self._manifest_path.read_text(encoding="utf-8"))
    requirements: list[str] = data.get("requirements", [])
    updated = False
    new_requirements: list[str] = []
    for requirement_entry in requirements:
      requirement = Requirement(requirement_entry)  # noqa: E111
      canonical = canonicalize_name(requirement.name)  # noqa: E111
      reference_requirement = reference.get(canonical)  # noqa: E111
      if reference_requirement is None:  # noqa: E111
        new_requirements.append(requirement_entry)
        continue
      new_requirement = compose_requirement(requirement, reference_requirement)  # noqa: E111
      new_requirements.append(new_requirement)  # noqa: E111
      if new_requirement != requirement_entry:  # noqa: E111
        updated = True
    if updated:
      data["requirements"] = new_requirements  # noqa: E111
      self._manifest_path.write_text(  # noqa: E111
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
      )
    return updated

  def update_requirement_files(  # noqa: E111
    self,
    *,
    reference: Mapping[str, ReferenceRequirement],
  ) -> bool:
    """Update local requirement files in place."""

    changed = False
    for path in self._requirements_files:
      file_changed = update_requirement_file(path, reference)  # noqa: E111
      changed = changed or file_changed  # noqa: E111
    return changed

  def sync_vendor_pyyaml(  # noqa: E111
    self,
    *,
    reference: Mapping[str, ReferenceRequirement],
    skip: bool,
    archive: Path | None,
  ) -> bool:
    """Synchronise the vendored PyYAML package with the reference version."""

    if skip:
      return False  # noqa: E111

    reference_requirement = reference.get("pyyaml")
    if reference_requirement is None or reference_requirement.version_hint is None:
      return False  # noqa: E111

    target_version = reference_requirement.version_hint
    try:
      current_version = vendor_monitor.load_vendor_version()  # noqa: E111
    except vendor_monitor.MonitoringError:
      current_version = None  # noqa: E111
    if current_version == target_version:
      return False  # noqa: E111

    if archive is None:
      archive = download_pyyaml_source(target_version)  # noqa: E111
    extract_pyyaml_archive(archive, target_version)
    return True

  def update_vendor_metadata(self) -> None:  # noqa: E111
    """Regenerate the vendored PyYAML metadata snapshot."""

    result, _ = vendor_monitor.evaluate(
      fail_on_outdated=False,
      fail_severity="HIGH",
      wheel_profiles=list(vendor_monitor.DEFAULT_WHEEL_PROFILES),
    )
    metadata = vendor_monitor.build_metadata_document(result)
    self._metadata_path.parent.mkdir(parents=True, exist_ok=True)
    self._metadata_path.write_text(
      json.dumps(metadata, indent=2, sort_keys=True) + "\n",
      encoding="utf-8",
    )


def update_mapping(
  mapping: dict[str, ReferenceRequirement], requirement: Requirement
) -> None:
  """Insert or replace a requirement in the mapping based on specificity."""  # noqa: E111

  canonical = canonicalize_name(requirement.name)  # noqa: E111
  existing = mapping.get(canonical)  # noqa: E111
  candidate = ReferenceRequirement(requirement=requirement)  # noqa: E111
  if existing is None:  # noqa: E111
    mapping[canonical] = candidate
    return

  if requirement_priority(candidate.requirement) > requirement_priority(  # noqa: E111
    existing.requirement
  ):
    mapping[canonical] = candidate
    return

  existing_version = existing.version_hint  # noqa: E111
  candidate_version = candidate.version_hint  # noqa: E111
  if existing_version is None:  # noqa: E111
    if candidate_version is not None:
      mapping[canonical] = candidate  # noqa: E111
    return
  if candidate_version is None:  # noqa: E111
    return
  if candidate_version > existing_version:  # noqa: E111
    mapping[canonical] = candidate


def update_mapping_from_lines(
  mapping: dict[str, ReferenceRequirement], lines: Iterable[str]
) -> None:
  """Update the mapping with requirement lines from a text file."""  # noqa: E111

  for raw_line in lines:  # noqa: E111
    line = raw_line.strip()
    if not line or line.startswith("#"):
      continue  # noqa: E111
    if line.startswith("-r"):
      continue  # noqa: E111
    try:
      requirement = Requirement(line)  # noqa: E111
    except Exception:
      continue  # noqa: E111
    update_mapping(mapping, requirement)


def highest_version(specifier_set: Iterable[Specifier]) -> Version | None:
  """Return the highest version referenced by the specifier set."""  # noqa: E111

  highest: Version | None = None  # noqa: E111
  for specifier in specifier_set:  # noqa: E111
    try:
      version = Version(specifier.version)  # noqa: E111
    except InvalidVersion, TypeError:
      continue  # noqa: E111
    if highest is None or version > highest:
      highest = version  # noqa: E111
  return highest  # noqa: E111


def requirement_priority(requirement: Requirement) -> int:
  """Return a numeric priority score for a requirement specifier."""  # noqa: E111

  if not requirement.specifier:  # noqa: E111
    return 0
  priority = 0  # noqa: E111
  for specifier in requirement.specifier:  # noqa: E111
    if specifier.operator in {"==", "==="}:
      priority = max(priority, 4)  # noqa: E111
    elif specifier.operator == ">=":
      priority = max(priority, 3)  # noqa: E111
    elif specifier.operator == "~=":
      priority = max(priority, 2)  # noqa: E111
    else:
      priority = max(priority, 1)  # noqa: E111
  return priority  # noqa: E111


def compose_requirement(
  requirement: Requirement, reference: ReferenceRequirement
) -> str:
  """Compose a requirement string using the reference specifier."""  # noqa: E111

  extras = sorted(requirement.extras)  # noqa: E111
  pieces: list[str] = [requirement.name]  # noqa: E111
  if extras:  # noqa: E111
    pieces[0] += f"[{','.join(extras)}]"
  specifier = reference.specifier or str(requirement.specifier)  # noqa: E111
  if specifier:  # noqa: E111
    pieces[0] += specifier
  marker = reference.marker or (str(requirement.marker) if requirement.marker else "")  # noqa: E111
  if marker:  # noqa: E111
    pieces[0] += f"; {marker}"
  return pieces[0]  # noqa: E111


def split_comment(line: str) -> tuple[str, str]:
  """Split a requirement line into requirement text and trailing comment."""  # noqa: E111

  hash_index = line.find("#")  # noqa: E111
  if hash_index == -1:  # noqa: E111
    return line.rstrip(), ""
  return line[:hash_index].rstrip(), line[hash_index:]  # noqa: E111


def update_requirement_file(
  path: Path, reference: Mapping[str, ReferenceRequirement]
) -> bool:
  """Rewrite a requirements file based on the reference mapping."""  # noqa: E111

  lines = path.read_text(encoding="utf-8").splitlines()  # noqa: E111
  new_lines: list[str] = []  # noqa: E111
  changed = False  # noqa: E111
  for line in lines:  # noqa: E111
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped.startswith("-r"):
      new_lines.append(line)  # noqa: E111
      continue  # noqa: E111
    requirement_part, comment = split_comment(line)
    try:
      requirement = Requirement(requirement_part)  # noqa: E111
    except Exception:
      new_lines.append(line)  # noqa: E111
      continue  # noqa: E111
    canonical = canonicalize_name(requirement.name)
    reference_requirement = reference.get(canonical)
    if reference_requirement is None:
      new_lines.append(line)  # noqa: E111
      continue  # noqa: E111
    updated_requirement = compose_requirement(requirement, reference_requirement)
    if comment:
      updated_requirement = f"{updated_requirement}  {comment.strip()}"  # noqa: E111
    if updated_requirement != line:
      changed = True  # noqa: E111
    new_lines.append(updated_requirement)
  if changed:  # noqa: E111
    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
  return changed  # noqa: E111


def download_pyyaml_source(version: Version) -> Path:
  """Download the PyYAML source distribution for the given version."""  # noqa: E111

  metadata = vendor_monitor.fetch_pypi_metadata()  # noqa: E111
  release_files = metadata.get("releases", {}).get(str(version), [])  # noqa: E111
  for entry in release_files:  # noqa: E111
    if entry.get("packagetype") != "sdist":
      continue  # noqa: E111
    url = entry.get("url")
    if not url:
      continue  # noqa: E111
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    suffix = ".tar.gz" if not url.endswith(".zip") else ".zip"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
      handle.write(response.content)  # noqa: E111
      archive_path = Path(handle.name)  # noqa: E111
    return archive_path
  raise RuntimeError(f"Unable to locate PyYAML {version} source distribution")  # noqa: E111


def _safe_tar_members(handle: tarfile.TarFile) -> Iterable[tarfile.TarInfo]:
  """Yield safe tar members, rejecting traversal and special file entries."""  # noqa: E111

  for member in handle.getmembers():  # noqa: E111
    member_path = PurePosixPath(member.name)
    if member_path.is_absolute() or any(part == ".." for part in member_path.parts):
      raise RuntimeError(  # noqa: E111
        f"Refusing to extract unsafe archive member: {member.name}",
      )
    if not (member.isfile() or member.isdir()):
      continue  # noqa: E111
    yield member


def extract_pyyaml_archive(archive: Path, version: Version) -> None:
  """Extract a PyYAML archive into the vendored directory."""  # noqa: E111

  with tempfile.TemporaryDirectory() as temp_dir:  # noqa: E111
    with tarfile.open(archive, "r:gz") as handle:
      handle.extractall(  # noqa: E111
        path=temp_dir,
        members=_safe_tar_members(handle),
        filter="data",
      )
    candidates = list(Path(temp_dir).glob("PyYAML-*")) + list(
      Path(temp_dir).glob("pyyaml-*")
    )
    if not candidates:
      raise RuntimeError("PyYAML archive did not contain an expected root folder")  # noqa: E111
    extracted_root = candidates[0]
    yaml_source = extracted_root / "lib" / "yaml"
    if not yaml_source.exists():
      yaml_source = extracted_root / "yaml"  # noqa: E111
    if not yaml_source.exists():
      raise RuntimeError("PyYAML archive did not contain the yaml package")  # noqa: E111
    if VENDOR_PACKAGE.exists():
      shutil.rmtree(VENDOR_PACKAGE)  # noqa: E111
    shutil.copytree(yaml_source, VENDOR_PACKAGE)
    license_file = extracted_root / "LICENSE"
    if license_file.exists():
      shutil.copyfile(license_file, VENDOR_LICENSE)  # noqa: E111
  archive.unlink(missing_ok=True)  # noqa: E111


def parse_arguments() -> argparse.Namespace:
  """Parse CLI arguments for the synchronisation routine."""  # noqa: E111

  parser = argparse.ArgumentParser(  # noqa: E111
    description="Synchronise local dependency versions with Home Assistant core",
  )
  parser.add_argument(  # noqa: E111
    "--home-assistant-root",
    type=Path,
    default=None,
    help="Optional path to a Home Assistant core checkout for offline syncing.",
  )
  parser.add_argument(  # noqa: E111
    "--reference-url",
    default=DEFAULT_REFERENCE_URL,
    help="Base URL for fetching Home Assistant reference files.",
  )
  parser.add_argument(  # noqa: E111
    "--manifest-path",
    type=Path,
    default=Path("custom_components/pawcontrol/manifest.json"),
    help="Path to the integration manifest to update.",
  )
  parser.add_argument(  # noqa: E111
    "--requirements-file",
    action="append",
    type=Path,
    default=[],
    help="Additional requirements files to synchronise (repeatable).",
  )
  parser.add_argument(  # noqa: E111
    "--metadata-path",
    type=Path,
    default=DEFAULT_METADATA_PATH,
    help="Path for the generated vendor metadata snapshot.",
  )
  parser.add_argument(  # noqa: E111
    "--skip-pyyaml-sync",
    action="store_true",
    help="Skip synchronising the vendored PyYAML package.",
  )
  parser.add_argument(  # noqa: E111
    "--pyyaml-archive",
    type=Path,
    default=None,
    help="Use a pre-downloaded PyYAML source archive instead of downloading via pip.",
  )
  parser.add_argument(  # noqa: E111
    "--skip-pyyaml-metadata",
    action="store_true",
    help="Skip regenerating the vendor PyYAML status metadata.",
  )
  return parser.parse_args()  # noqa: E111


def main() -> int:
  """CLI entry point for the dependency synchroniser."""  # noqa: E111

  args = parse_arguments()  # noqa: E111
  requirements_files = args.requirements_file or [  # noqa: E111
    Path("requirements.txt"),
    Path("requirements_test.txt"),
  ]

  loader = ReferenceLoader(root=args.home_assistant_root, base_url=args.reference_url)  # noqa: E111
  synchroniser = DependencySynchroniser(  # noqa: E111
    loader=loader,
    manifest_path=args.manifest_path,
    requirements_files=requirements_files,
    metadata_path=args.metadata_path,
  )
  reference_map = synchroniser.load_reference_requirements()  # noqa: E111

  manifest_changed = synchroniser.update_manifest_requirements(reference=reference_map)  # noqa: E111
  requirements_changed = synchroniser.update_requirement_files(reference=reference_map)  # noqa: E111
  vendor_changed = synchroniser.sync_vendor_pyyaml(  # noqa: E111
    reference=reference_map,
    skip=args.skip_pyyaml_sync,
    archive=args.pyyaml_archive,
  )
  if not args.skip_pyyaml_metadata:  # noqa: E111
    synchroniser.update_vendor_metadata()

  if any((manifest_changed, requirements_changed, vendor_changed)):  # noqa: E111
    return 1
  return 0  # noqa: E111


if __name__ == "__main__":
  raise SystemExit(main())  # noqa: E111
