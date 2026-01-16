"""Publish coverage artifacts.

This helper is intentionally lightweight. The reusable workflow optionally calls it to
prepare a GitHub Pages bundle containing the HTML coverage report and a small metadata
file.

The workflow passes paths for the generated coverage XML and the HTML index.
When running in "pages" mode we simply copy the HTML report directory into the
requested artifact directory.

This script does *not* push to GitHub Pages by itself; the workflow is responsible for
uploading the prepared bundle.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

LOGGER = logging.getLogger(__name__)

API_ROOT = "https://api.github.com"
DEFAULT_TIMEOUT = 15
REPOSITORY_SLUG_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
LINE_RATE_PATTERN = re.compile(r"line-rate=['\"](?P<value>[0-9]+(?:\.[0-9]+)?)['\"]")
DEFAULT_PREFIX_TEMPLATES = ("{prefix}/{run_id}", "{prefix}/latest")
PRUNE_MAX_AGE = dt.timedelta(days=30)
ALLOWED_URL_SCHEMES = frozenset({"https"})
_API_ROOT_COMPONENTS = urlsplit(API_ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare GitHub Pages artifact for coverage"
    )
    parser.add_argument(
        "--coverage-html-index", required=True, help="Path to coverage HTML index.html"
    )
    parser.add_argument(
        "--public-dir", required=True, help="Output directory for Pages artifact"
    )
    parser.add_argument(
        "--mode",
        default="pages",
        choices=("pages",),
        help="Publishing mode (reserved for future use)",
    )
class PublishError(RuntimeError):
    """Raised when the GitHub Pages publication fails."""


@dataclasses.dataclass(slots=True)
class FilePayload:
    """In-memory representation of a file destined for publication."""

    relative_path: str
    content: bytes

    def as_tarinfo(self, target: str) -> tuple[tarfile.TarInfo, io.BytesIO]:
        """Create tar metadata for this payload under ``target``."""

        data_stream = io.BytesIO(self.content)
        info = tarfile.TarInfo(target)
        info.size = len(self.content)
        info.mtime = int(dt.datetime.now(dt.UTC).timestamp())
        info.mode = 0o644
        return info, data_stream


@dataclasses.dataclass(slots=True)
class CoverageDataset:
    """Container for the generated coverage outputs."""

    xml_path: Path
    html_index: Path
    run_metadata: Mapping[str, str]
    html_root: Path = dataclasses.field(init=False)
    _coverage_percent: float = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        if not self.xml_path.is_file():
            raise FileNotFoundError(f"Coverage XML not found: {self.xml_path}")
        if not self.html_index.is_file():
            raise FileNotFoundError(f"Coverage HTML index not found: {self.html_index}")
        self.html_root = self.html_index.parent
        self._coverage_percent = self._parse_coverage_percent()

    def build_payloads(self) -> list[FilePayload]:
        """Return the payloads required for publication."""

        payloads: list[FilePayload] = []
        payloads.append(FilePayload("coverage.xml", self.xml_path.read_bytes()))
        payloads.extend(
            FilePayload(
                str(file_path.relative_to(self.html_root)).replace("\\", "/"),
                file_path.read_bytes(),
            )
            for file_path in sorted(self._iter_html_files())
        )
        summary = self._build_summary_payload()
        payloads.append(FilePayload("summary.json", summary))
        payloads.append(
            FilePayload("shields.json", self._build_shields_payload(summary))
        )
        payloads.append(FilePayload("metadata.json", self._build_metadata_payload()))
        return payloads

    def _iter_html_files(self) -> Iterator[Path]:
        for path in self.html_root.rglob("*"):
            if path.is_file():
                yield path

    def _parse_coverage_percent(self) -> float:
        xml_data = self.xml_path.read_text(encoding="utf-8")
        match = LINE_RATE_PATTERN.search(xml_data)
        if match is None:
            raise ValueError("Invalid coverage.xml line-rate: missing attribute")
        line_rate = match.group("value")
        try:
            return round(float(line_rate) * 100, 2)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"Invalid coverage.xml line-rate: {line_rate!r}"
            ) from error

    def _build_summary_payload(self) -> bytes:
        timestamp = dt.datetime.now(dt.UTC).isoformat()
        summary = {
            "schema": 1,
            "generated_at": timestamp,
            "coverage_percent": self._coverage_percent,
            "coverage_label": f"{self._coverage_percent:.2f}%",
            "run": dict(self.run_metadata),
        }
        return json.dumps(summary, indent=2, sort_keys=True).encode("utf-8")

    def _build_shields_payload(self, summary_bytes: bytes) -> bytes:
        summary = json.loads(summary_bytes)
        percent = float(summary["coverage_percent"])
        color = coverage_color(percent)
        shields = {
            "schemaVersion": 1,
            "label": "Coverage",
            "message": f"{percent:.1f}%",
            "color": color,
        }
        return json.dumps(shields, separators=(",", ":")).encode("utf-8")

    def _build_metadata_payload(self) -> bytes:
        metadata = {
            "schema": 1,
            "html_root": str(self.html_root),
            "files": sorted(
                str(path.relative_to(self.html_root)).replace("\\", "/")
                for path in self._iter_html_files()
            ),
        }
        metadata.update(self.run_metadata)
        return json.dumps(metadata, indent=2, sort_keys=True).encode("utf-8")


def coverage_color(percent: float) -> str:
    """Return a shields.io-compatible color for the coverage percentage."""

    if percent >= 95:
        return "brightgreen"
    if percent >= 90:
        return "green"
    if percent >= 80:
        return "yellowgreen"
    if percent >= 70:
        return "yellow"
    if percent >= 60:
        return "orange"
    return "red"


@dataclasses.dataclass(slots=True)
class PublishResult:
    """Represents the result of the publication step."""

    published: bool
    archive_path: Path
    publish_url: str | None



def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument("--coverage-xml", type=Path, required=True)
    parser.add_argument("--coverage-html-index", type=Path, required=True)
    parser.add_argument("--artifact-directory", type=Path, required=True)

    parser.add_argument("--mode", choices={"pages", "artifact"}, default="artifact")
    parser.add_argument("--pages-branch", default="gh-pages")
    parser.add_argument("--pages-prefix", default="coverage")

    parser.add_argument("--run-id", default="")
    parser.add_argument("--run-attempt", default="")
    parser.add_argument("--commit-sha", default="")
    parser.add_argument("--ref", default="")

    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    coverage_xml = args.coverage_xml
    html_index = args.coverage_html_index

    if not coverage_xml.exists():
        raise SystemExit(f"coverage xml not found: {coverage_xml}")
    if not html_index.exists():
        raise SystemExit(f"coverage html index not found: {html_index}")

    artifact_dir = args.artifact_directory
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # Copy full HTML directory (index.html lives inside)
    html_dir = html_index.parent
    target_html_dir = artifact_dir / "html"

    if target_html_dir.exists():
        shutil.rmtree(target_html_dir)

    shutil.copytree(html_dir, target_html_dir)

    meta = {
        "mode": args.mode,
        "pages_branch": args.pages_branch,
        "pages_prefix": args.pages_prefix,
        "run_id": args.run_id,
        "run_attempt": args.run_attempt,
        "commit_sha": args.commit_sha,
        "ref": args.ref,
        "coverage_xml": str(coverage_xml),
        "coverage_html_index": str(html_index),
    }

    (artifact_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    # Provide a stable entry-point index for consumers.
    (artifact_dir / "index.html").write_text(
        (target_html_dir / "index.html").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    print(f"Prepared coverage bundle in {artifact_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
