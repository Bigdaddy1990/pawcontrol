"""Publish lightweight coverage artifacts to GitHub Pages or local archives.

This module uploads the generated coverage summary to the configured GitHub
Pages branch and emits a tarball fallback that CI can surface as an artifact.
It is intentionally defensive: network failures or missing credentials degrade
into a local archive so quality gates can still expose coverage results.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import dataclasses
import datetime as dt
import io
import json
import logging
import os
import re
import tarfile
import urllib.error
import urllib.request
import urllib.response
from collections.abc import Iterable, Iterator, Mapping, MutableMapping, Sequence
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


class GitHubPagesPublisher:
    """Publish coverage assets to a GitHub Pages branch using the git data API."""

    def __init__(
        self, token: str, repository: str, branch: str, timeout: int = DEFAULT_TIMEOUT
    ) -> None:
        if not token:
            raise PublishError("Missing GITHUB_TOKEN - cannot publish to GitHub Pages")
        if not repository or not REPOSITORY_SLUG_PATTERN.fullmatch(repository):
            raise PublishError(f"Invalid repository slug: {repository!r}")
        self._token = token
        self._repository = repository
        self._branch = branch
        self._timeout = timeout

    def publish(
        self, payloads: Iterable[FilePayload], landing_path: str | None = None
    ) -> str:
        """Publish payloads to the configured GitHub Pages branch."""

        base_sha = self._fetch_branch_head()
        tree_entries = []
        for payload in payloads:
            blob_sha = self._create_blob(payload.content)
            tree_entries.append(
                {
                    "path": payload.relative_path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob_sha,
                }
            )
        commit_message = "Publish coverage report"
        self._commit_tree(base_sha, tree_entries, commit_message)
        owner, repo = self._repository.split("/", 1)
        base_url = f"https://{owner}.github.io/{repo}"
        if landing_path:
            landing_path = landing_path.lstrip("/")
            return f"{base_url}/{landing_path}"
        return f"{base_url}/"

    def _create_blob(self, content: bytes) -> str:
        encoded = base64.b64encode(content).decode("ascii")
        blob = self._request(
            "POST",
            f"/repos/{self._repository}/git/blobs",
            {"content": encoded, "encoding": "base64"},
        )
        return blob["sha"]

    def _fetch_branch_head(self) -> str:
        ref = cast(
            Mapping[str, Any],
            self._request(
                "GET", f"/repos/{self._repository}/git/refs/heads/{self._branch}"
            ),
        )
        branch_object = cast(Mapping[str, Any], ref["object"])
        return cast(str, branch_object["sha"])

    def _commit_tree(
        self,
        base_sha: str,
        tree_entries: Sequence[Mapping[str, object]],
        message: str,
    ) -> str:
        tree = cast(
            Mapping[str, Any],
            self._request(
                "POST",
                f"/repos/{self._repository}/git/trees",
                {"base_tree": base_sha, "tree": list(tree_entries)},
            ),
        )
        commit = cast(
            Mapping[str, Any],
            self._request(
                "POST",
                f"/repos/{self._repository}/git/commits",
                {"message": message, "tree": tree["sha"], "parents": [base_sha]},
            ),
        )
        self._request(
            "PATCH",
            f"/repos/{self._repository}/git/refs/heads/{self._branch}",
            {"sha": commit["sha"], "force": True},
        )
        return cast(str, commit["sha"])

    def _request(
        self, method: str, path: str, payload: MutableMapping[str, object] | None = None
    ) -> Any:
        url = f"{API_ROOT}{path}"
        data: bytes | None = None
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "pawcontrol-coverage-publisher",
        }
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with open_github_api_url(request, timeout=self._timeout) as response:
                response_data = response.read()
                status = getattr(response, "status", None)
                if status is None:
                    status = response.getcode()
                if status is None:
                    status = 200
        except urllib.error.HTTPError as error:
            raise PublishError(
                f"GitHub API error {error.code}: {error.reason}"
            ) from error
        except urllib.error.URLError as error:
            raise PublishError(f"Network error: {error.reason}") from error
        if not 200 <= status < 300:
            raise PublishError(f"GitHub API returned status {status} for {path}")
        if not response_data:
            return {}
        return json.loads(response_data.decode("utf-8"))

    def prune_expired_runs(
        self,
        prefix: str,
        max_age: dt.timedelta,
        *,
        now: dt.datetime | None = None,
    ) -> list[str]:
        """Delete coverage run directories older than ``max_age``."""

        now = now or dt.datetime.now(dt.UTC)
        normalized_prefix = prefix.strip("/")
        if not normalized_prefix:
            return []
        contents = self._request(
            "GET",
            f"/repos/{self._repository}/contents/{normalized_prefix}?ref={self._branch}",
        )
        if not isinstance(contents, list):
            return []
        expired_paths: list[str] = []
        for entry in contents:
            if not isinstance(entry, Mapping):
                continue
            if entry.get("type") != "dir":
                continue
            run_id = str(entry.get("name", ""))
            if not run_id or run_id == "latest":
                continue
            generated_at = self._load_run_timestamp(normalized_prefix, run_id)
            if generated_at is None:
                continue
            if now - generated_at > max_age:
                expired_paths.append(f"{normalized_prefix}/{run_id}")
        if not expired_paths:
            return []
        base_sha = self._fetch_branch_head()
        tree_entries: list[dict[str, object]] = [
            {
                "path": path,
                "mode": "040000",
                "type": "tree",
                "sha": None,
            }
            for path in expired_paths
        ]
        self._commit_tree(base_sha, tree_entries, "Prune expired coverage runs")
        return expired_paths

    def _load_run_timestamp(self, prefix: str, run_id: str) -> dt.datetime | None:
        summary = self._request(
            "GET",
            f"/repos/{self._repository}/contents/{prefix}/{run_id}/summary.json?ref={self._branch}",
        )
        if not isinstance(summary, Mapping):
            return None
        content = summary.get("content")
        encoding = summary.get("encoding")
        if not isinstance(content, str) or encoding != "base64":
            return None
        try:
            decoded = base64.b64decode(content.encode("ascii"))
            payload = json.loads(decoded.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, binascii.Error):
            return None
        generated_at = payload.get("generated_at")
        if not isinstance(generated_at, str):
            return None
        try:
            timestamp = dt.datetime.fromisoformat(generated_at)
        except ValueError:
            return None
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=dt.UTC)
        return timestamp.astimezone(dt.UTC)


def ensure_allowed_github_api_url(url: str) -> None:
    """Validate that ``url`` targets the GitHub API using an allowed scheme."""

    parsed = urlsplit(url)
    if parsed.scheme not in ALLOWED_URL_SCHEMES:
        raise PublishError(f"Refusing to access URL with disallowed scheme: {url!r}")
    if parsed.netloc != _API_ROOT_COMPONENTS.netloc:
        raise PublishError(f"Refusing to access URL outside GitHub API host: {url!r}")
    if not url.startswith(f"{API_ROOT}/"):
        raise PublishError(f"Refusing to access unexpected URL: {url!r}")


def open_github_api_url(
    request: urllib.request.Request, *, timeout: float | int | None
) -> urllib.response.addinfourl:
    """Open ``request`` after enforcing GitHub API scheme restrictions."""

    url = getattr(request, "full_url", request.get_full_url())
    ensure_allowed_github_api_url(url)
    opener = urllib.request.build_opener()
    return opener.open(request, timeout=timeout)


def duplicate_payloads(
    payloads: Iterable[FilePayload], prefixes: Iterable[str]
) -> list[FilePayload]:
    """Return payloads duplicated under multiple prefixes."""

    duplicated: list[FilePayload] = []
    for payload in payloads:
        for prefix in prefixes:
            relative_path = (
                f"{prefix}/{payload.relative_path}" if prefix else payload.relative_path
            )
            duplicated.append(FilePayload(relative_path, payload.content))
    return duplicated


def create_archive(payloads: Iterable[FilePayload], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(destination, "w:gz") as archive:
        for payload in payloads:
            info, buffer = payload.as_tarinfo(payload.relative_path)
            archive.addfile(info, buffer)
    return destination


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--coverage-xml", required=True, type=Path, help="Path to coverage.xml"
    )
    parser.add_argument(
        "--coverage-html-index",
        required=True,
        type=Path,
        help="Path to the generated coverage index.html",
    )
    parser.add_argument(
        "--artifact-directory",
        type=Path,
        default=Path("generated/coverage/artifacts"),
        help="Directory where fallback archives are stored",
    )
    parser.add_argument("--mode", choices=("pages", "archive"), default="pages")
    parser.add_argument("--pages-branch", default="gh-pages")
    parser.add_argument("--pages-prefix", default="coverage")
    parser.add_argument(
        "--pages-prefix-template",
        dest="pages_prefix_templates",
        action="append",
        help=(
            "Template for GitHub Pages prefixes. Supports {prefix}, {run_id}, "
            "and {run_attempt}. May be supplied multiple times."
        ),
    )
    parser.add_argument("--run-id", default=os.getenv("GITHUB_RUN_ID", "manual"))
    parser.add_argument("--run-attempt", default=os.getenv("GITHUB_RUN_ATTEMPT", "1"))
    parser.add_argument("--commit-sha", default=os.getenv("GITHUB_SHA", ""))
    parser.add_argument("--ref", default=os.getenv("GITHUB_REF", ""))
    parser.add_argument(
        "--prune-expired-runs",
        action="store_true",
        help=(
            "Prune coverage/<run_id> directories older than the configured retention from the Pages branch"
        ),
    )
    parser.add_argument(
        "--prune-max-age-days",
        type=int,
        default=int(PRUNE_MAX_AGE.days),
        help=(
            "Maximum age in days for coverage/<run_id> directories when pruning. "
            "Defaults to 30 days."
        ),
    )
    return parser


def publish(args: argparse.Namespace) -> PublishResult:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run_metadata = {
        "run_id": str(args.run_id),
        "run_attempt": str(args.run_attempt),
    }
    if args.commit_sha:
        run_metadata["commit_sha"] = str(args.commit_sha)
    if args.ref:
        run_metadata["ref"] = str(args.ref)
    dataset = CoverageDataset(args.coverage_xml, args.coverage_html_index, run_metadata)
    payloads = dataset.build_payloads()
    prefix_root = str(args.pages_prefix).strip("/")
    templates = (
        args.pages_prefix_templates
        if args.pages_prefix_templates
        else list(DEFAULT_PREFIX_TEMPLATES)
    )
    template_context = {
        "prefix": prefix_root,
        "run_id": str(args.run_id),
        "run_attempt": str(args.run_attempt),
    }
    prefixes = [
        template.format(**template_context).strip("/") for template in templates
    ]
    prefixes = list(dict.fromkeys(prefixes))
    duplicated_payloads = duplicate_payloads(payloads, prefixes)
    archive_name = f"coverage-{args.run_id}.tar.gz"
    archive_path = args.artifact_directory / archive_name
    archive = create_archive(duplicated_payloads, archive_path)
    LOGGER.info("Created coverage archive at %s", archive)
    publish_url: str | None = None
    published = False
    prune_requested = bool(getattr(args, "prune_expired_runs", False))
    prune_age_days = getattr(args, "prune_max_age_days", int(PRUNE_MAX_AGE.days))
    try:
        prune_age_days = int(prune_age_days)
    except (TypeError, ValueError):
        prune_age_days = int(PRUNE_MAX_AGE.days)
    if prune_age_days < 0:
        prune_age_days = 0
    prune_window = dt.timedelta(days=prune_age_days)

    if args.mode == "pages":
        token = os.getenv("GITHUB_TOKEN", "")
        repository = os.getenv("GITHUB_REPOSITORY", "")
        try:
            publisher = GitHubPagesPublisher(token, repository, args.pages_branch)
        except PublishError as error:
            LOGGER.warning("GitHub Pages upload skipped: %s", error)
        else:
            try:
                publish_url = publisher.publish(
                    duplicated_payloads,
                    landing_path=f"{args.pages_prefix}/latest/index.html",
                )
                LOGGER.info("Published coverage to GitHub Pages at %s", publish_url)
                published = True
            except PublishError as error:
                LOGGER.warning("GitHub Pages upload skipped: %s", error)
            if prune_requested:
                prune_prefix = prefix_root or str(args.pages_prefix).strip("/")
                try:
                    removed = publisher.prune_expired_runs(prune_prefix, prune_window)
                except PublishError as error:
                    LOGGER.info("Coverage prune skipped: %s", error)
                else:
                    if removed:
                        LOGGER.info(
                            "Pruned %d expired coverage runs from GitHub Pages",
                            len(removed),
                        )
            if published:
                return PublishResult(True, archive, publish_url)
    return PublishResult(False, archive, publish_url)


def main(argv: list[str] | None = None) -> int:
    parser = build_cli()
    args = parser.parse_args(argv)
    result = publish(args)
    if not result.published:
        LOGGER.info("Coverage archive available at %s", result.archive_path)
    else:
        LOGGER.info("Coverage published to %s", result.publish_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
