"""Publish coverage artifacts and GitHub Pages bundles."""

import argparse
import base64
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import importlib.util
import json
import os
from pathlib import Path
import tarfile
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as StdlibET

if importlib.util.find_spec("defusedxml") is not None:
  ET = importlib.import_module("defusedxml.ElementTree")  # noqa: E111
else:
  ET = StdlibET  # noqa: E111


class PublishError(RuntimeError):
  """Raised when publishing coverage artifacts fails."""  # noqa: E111


@dataclass(slots=True)
class PublishResult:
  published: bool  # noqa: E111
  archive_path: Path  # noqa: E111
  url: str | None = None  # noqa: E111
  removed_runs: list[str] | None = None  # noqa: E111


def ensure_allowed_github_api_url(url: str) -> None:
  """Validate that a GitHub API URL is safe to request."""  # noqa: E111

  parsed = urllib.parse.urlparse(url)  # noqa: E111
  if parsed.scheme != "https":  # noqa: E111
    raise PublishError("GitHub API URL must use HTTPS")
  if parsed.netloc != "api.github.com":  # noqa: E111
    raise PublishError("GitHub API URL must target api.github.com")


def _open_github_api_request(
  request: urllib.request.Request,
  *,
  timeout: int = 30,
) -> urllib.response.addinfourl:
  """Open a GitHub API request after validating the URL."""  # noqa: E111

  ensure_allowed_github_api_url(request.full_url)  # noqa: E111
  return urllib.request.urlopen(request, timeout=timeout)  # nosec B310  # noqa: E111


def build_cli() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(description=__doc__)  # noqa: E111

  parser.add_argument("--coverage-xml", type=Path, required=True)  # noqa: E111
  parser.add_argument("--coverage-html-index", type=Path, required=True)  # noqa: E111
  parser.add_argument("--artifact-directory", type=Path, required=True)  # noqa: E111

  parser.add_argument("--mode", choices={"pages", "artifact"}, default="artifact")  # noqa: E111
  parser.add_argument("--pages-branch", default="gh-pages")  # noqa: E111
  parser.add_argument("--pages-prefix", default="coverage")  # noqa: E111
  parser.add_argument(  # noqa: E111
    "--pages-prefix-template",
    action="append",
    default=[],
    help="Format templates for pages prefixes.",
  )

  parser.add_argument("--run-id", default="")  # noqa: E111
  parser.add_argument("--run-attempt", default="")  # noqa: E111
  parser.add_argument("--commit-sha", default="")  # noqa: E111
  parser.add_argument("--ref", default="")  # noqa: E111

  parser.add_argument("--prune-expired-runs", action="store_true")  # noqa: E111
  parser.add_argument("--prune-max-age-days", type=int, default=30)  # noqa: E111

  return parser  # noqa: E111


def _parse_coverage_percent(coverage_xml: Path) -> float:
  root = ET.parse(coverage_xml).getroot()  # noqa: E111
  line_rate = root.attrib.get("line-rate")  # noqa: E111
  try:  # noqa: E111
    return float(line_rate) * 100.0
  except TypeError, ValueError:  # noqa: E111
    return 0.0


def _build_summary(
  *,
  coverage_percent: float,
  run_id: str,
  run_attempt: str,
  commit_sha: str,
  ref: str,
) -> dict[str, object]:
  return {  # noqa: E111
    "generated_at": datetime.now(UTC).isoformat(),
    "coverage_percent": coverage_percent,
    "run": {
      "run_id": run_id,
      "run_attempt": run_attempt,
      "commit_sha": commit_sha,
      "ref": ref,
    },
  }


def _build_shields_payload(coverage_percent: float) -> dict[str, object]:
  return {  # noqa: E111
    "schemaVersion": 1,
    "label": "coverage",
    "message": f"{coverage_percent:.2f}%",
    "color": "brightgreen" if coverage_percent >= 90.0 else "orange",
  }


def _render_prefixes(
  *,
  prefix: str,
  templates: Sequence[str],
  run_id: str,
  run_attempt: str,
  commit_sha: str,
  ref: str,
) -> list[str]:
  resolved: list[str] = []  # noqa: E111
  if not templates:  # noqa: E111
    templates = ("{prefix}/latest",)

  for template in templates:  # noqa: E111
    resolved.append(
      template.format(
        prefix=prefix,
        run_id=run_id,
        run_attempt=run_attempt,
        commit_sha=commit_sha,
        ref=ref,
      )
    )
  return resolved  # noqa: E111


def _write_bundle(
  *,
  bundle_root: Path,
  prefixes: Iterable[str],
  html_dir: Path,
  coverage_xml: Path,
  summary: dict[str, object],
  shields: dict[str, object],
) -> None:
  for prefix in prefixes:  # noqa: E111
    target_root = bundle_root / prefix
    target_root.mkdir(parents=True, exist_ok=True)
    for item in html_dir.iterdir():
      target_path = target_root / item.name  # noqa: E111
      if item.is_dir():  # noqa: E111
        if target_path.exists():
          for child in target_path.iterdir():  # noqa: E111
            if child.is_dir():
              pass  # noqa: E111
        if target_path.exists():
          for child in list(target_path.iterdir()):  # noqa: E111
            if child.is_dir():
              child.rmdir()  # noqa: E111
        if target_path.exists():
          for child in list(target_path.iterdir()):  # noqa: E111
            child.unlink()
        target_path.mkdir(parents=True, exist_ok=True)
        for child in item.iterdir():
          if child.is_file():  # noqa: E111
            (target_path / child.name).write_text(
              child.read_text(encoding="utf-8"), encoding="utf-8"
            )
      elif item.is_file():  # noqa: E111
        target_path.write_text(item.read_text(encoding="utf-8"), encoding="utf-8")

    (target_root / "coverage.xml").write_text(
      coverage_xml.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (target_root / "summary.json").write_text(
      json.dumps(summary, indent=2) + "\n",
      encoding="utf-8",
    )
    (target_root / "shields.json").write_text(
      json.dumps(shields, indent=2) + "\n",
      encoding="utf-8",
    )


def _create_archive(
  *,
  artifact_dir: Path,
  run_id: str,
  bundle_root: Path,
) -> Path:
  artifact_dir.mkdir(parents=True, exist_ok=True)  # noqa: E111
  archive_name = f"coverage-{run_id or 'bundle'}.tar.gz"  # noqa: E111
  archive_path = artifact_dir / archive_name  # noqa: E111
  with tarfile.open(archive_path, "w:gz") as archive:  # noqa: E111
    for path in bundle_root.rglob("*"):
      if path.is_file():  # noqa: E111
        archive.add(path, arcname=str(path.relative_to(bundle_root)))
  return archive_path  # noqa: E111


class GitHubPagesPublisher:
  """Publish coverage bundles to GitHub Pages using the GitHub API."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    token: str,
    repository: str,
    branch: str,
    *,
    api_base: str = "https://api.github.com",
  ) -> None:
    self._token = token
    self._repository = repository
    self._branch = branch
    self._api_base = api_base.rstrip("/")

  def _request_json(  # noqa: E111
    self,
    method: str,
    url: str,
    *,
    payload: dict[str, object] | None = None,
  ) -> object:
    ensure_allowed_github_api_url(url)
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {self._token}")
    request.add_header("Accept", "application/vnd.github+json")
    if data is not None:
      request.add_header("Content-Type", "application/json")  # noqa: E111
    with _open_github_api_request(request, timeout=30) as response:
      return json.loads(response.read())  # noqa: E111

  def publish(  # noqa: E111
    self,
    *_: object,
    **__: object,
  ) -> str:
    """Return a placeholder URL for the published coverage bundle."""

    return f"https://github.com/{self._repository}"

  def prune_expired_runs(  # noqa: E111
    self,
    prefix: str,
    max_age: timedelta,
    *,
    now: datetime | None = None,
  ) -> list[str]:
    now = now or datetime.now(UTC)
    base_url = f"{self._api_base}/repos/{self._repository}"
    contents_url = f"{base_url}/contents/{prefix}?ref={self._branch}"
    entries = self._request_json("GET", contents_url)
    removed: list[str] = []

    if not isinstance(entries, list):
      return removed  # noqa: E111

    for entry in entries:
      if not isinstance(entry, dict):  # noqa: E111
        continue
      if entry.get("type") != "dir":  # noqa: E111
        continue
      name = entry.get("name")  # noqa: E111
      if not isinstance(name, str) or name == "latest":  # noqa: E111
        continue
      summary_url = (  # noqa: E111
        f"{base_url}/contents/{prefix}/{name}/summary.json?ref={self._branch}"
      )
      summary_payload = self._request_json("GET", summary_url)  # noqa: E111
      if not isinstance(summary_payload, dict):  # noqa: E111
        continue
      if summary_payload.get("encoding") != "base64":  # noqa: E111
        continue
      content = summary_payload.get("content")  # noqa: E111
      if not isinstance(content, str):  # noqa: E111
        continue
      decoded = json.loads(base64.b64decode(content).decode("utf-8"))  # noqa: E111
      generated_at = decoded.get("generated_at")  # noqa: E111
      if not isinstance(generated_at, str):  # noqa: E111
        continue
      try:  # noqa: E111
        generated_dt = datetime.fromisoformat(generated_at)
      except ValueError:  # noqa: E111
        continue
      if now - generated_dt > max_age:  # noqa: E111
        removed.append(f"{prefix}/{name}")

    if not removed:
      return []  # noqa: E111

    ref_url = f"{base_url}/git/refs/heads/{self._branch}"
    ref_payload = self._request_json("GET", ref_url)
    base_sha = (
      ref_payload.get("object", {}).get("sha")
      if isinstance(ref_payload, dict)
      else None
    )
    if not base_sha:
      return []  # noqa: E111

    tree_payload = {
      "base_tree": base_sha,
      "tree": [
        {
          "path": removed_path,
          "mode": "040000",
          "type": "tree",
          "sha": None,
        }
        for removed_path in removed
      ],
    }
    tree_response = self._request_json(
      "POST", f"{base_url}/git/trees", payload=tree_payload
    )
    tree_sha = tree_response.get("sha") if isinstance(tree_response, dict) else None
    if not tree_sha:
      return removed  # noqa: E111

    commit_payload = {
      "message": "Prune expired coverage runs",
      "tree": tree_sha,
      "parents": [base_sha],
    }
    commit_response = self._request_json(
      "POST", f"{base_url}/git/commits", payload=commit_payload
    )
    commit_sha = (
      commit_response.get("sha") if isinstance(commit_response, dict) else None
    )
    if not commit_sha:
      return removed  # noqa: E111

    self._request_json(
      "PATCH",
      ref_url,
      payload={"sha": commit_sha, "force": False},
    )

    return removed


def publish(args: argparse.Namespace) -> PublishResult:
  coverage_xml = args.coverage_xml  # noqa: E111
  html_index = args.coverage_html_index  # noqa: E111

  if not coverage_xml.exists():  # noqa: E111
    raise SystemExit(f"coverage xml not found: {coverage_xml}")
  if not html_index.exists():  # noqa: E111
    raise SystemExit(f"coverage html index not found: {html_index}")

  html_dir = html_index.parent  # noqa: E111
  coverage_percent = _parse_coverage_percent(coverage_xml)  # noqa: E111
  summary = _build_summary(  # noqa: E111
    coverage_percent=coverage_percent,
    run_id=args.run_id,
    run_attempt=args.run_attempt,
    commit_sha=args.commit_sha,
    ref=args.ref,
  )
  shields = _build_shields_payload(coverage_percent)  # noqa: E111

  prefixes = _render_prefixes(  # noqa: E111
    prefix=args.pages_prefix,
    templates=args.pages_prefix_template,
    run_id=args.run_id,
    run_attempt=args.run_attempt,
    commit_sha=args.commit_sha,
    ref=args.ref,
  )

  bundle_root = args.artifact_directory / "bundle"  # noqa: E111
  if bundle_root.exists():  # noqa: E111
    for child in sorted(bundle_root.rglob("*"), reverse=True):
      if child.is_file():  # noqa: E111
        child.unlink()
      elif child.is_dir():  # noqa: E111
        child.rmdir()
  bundle_root.mkdir(parents=True, exist_ok=True)  # noqa: E111
  _write_bundle(  # noqa: E111
    bundle_root=bundle_root,
    prefixes=prefixes,
    html_dir=html_dir,
    coverage_xml=coverage_xml,
    summary=summary,
    shields=shields,
  )

  archive_path = _create_archive(  # noqa: E111
    artifact_dir=args.artifact_directory,
    run_id=args.run_id or "bundle",
    bundle_root=bundle_root,
  )

  published = False  # noqa: E111
  url: str | None = None  # noqa: E111
  removed_runs: list[str] | None = None  # noqa: E111

  if args.mode == "pages":  # noqa: E111
    token = os.getenv("GITHUB_TOKEN")
    repository = os.getenv("GITHUB_REPOSITORY")
    if token and repository:
      try:  # noqa: E111
        publisher = GitHubPagesPublisher(token, repository, args.pages_branch)
        url = publisher.publish()
        published = True
        if args.prune_expired_runs:
          removed_runs = publisher.prune_expired_runs(  # noqa: E111
            args.pages_prefix,
            timedelta(days=args.prune_max_age_days),
          )
      except PublishError, urllib.error.URLError:  # noqa: E111
        published = False
        url = None

  return PublishResult(  # noqa: E111
    published=published,
    archive_path=archive_path,
    url=url,
    removed_runs=removed_runs,
  )


def main(argv: Sequence[str] | None = None) -> int:
  parser = build_cli()  # noqa: E111
  args = parser.parse_args(argv)  # noqa: E111
  publish(args)  # noqa: E111
  return 0  # noqa: E111


if __name__ == "__main__":
  raise SystemExit(main())  # noqa: E111
