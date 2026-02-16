"""Regression tests for the coverage publishing helper."""

from __future__ import annotations

import base64
import datetime as dt
import json
import tarfile
import urllib.error
import urllib.request

import pytest
from scripts import publish_coverage


@pytest.mark.ci_only
def test_publish_coverage_degrades_without_network(tmp_path, monkeypatch) -> None:
  """The publisher should degrade to an archive when GitHub is unavailable."""  # noqa: E111

  coverage_xml = tmp_path / "coverage.xml"  # noqa: E111
  coverage_xml.write_text(  # noqa: E111
    """<?xml version='1.0' ?><coverage line-rate='0.9523'></coverage>""",
    encoding="utf-8",
  )
  html_root = tmp_path / "generated" / "coverage"  # noqa: E111
  html_root.mkdir(parents=True)  # noqa: E111
  (html_root / "index.html").write_text("<html></html>", encoding="utf-8")  # noqa: E111
  (html_root / "style.css").write_text("body {color: #333;}", encoding="utf-8")  # noqa: E111
  artifact_dir = tmp_path / "artifacts"  # noqa: E111

  monkeypatch.delenv("GITHUB_TOKEN", raising=False)  # noqa: E111
  monkeypatch.setenv("GITHUB_REPOSITORY", "pawcontrol/pawcontrol")  # noqa: E111

  exit_code = publish_coverage.main([  # noqa: E111
    "--coverage-xml",
    str(coverage_xml),
    "--coverage-html-index",
    str(html_root / "index.html"),
    "--artifact-directory",
    str(artifact_dir),
    "--mode",
    "pages",
    "--run-id",
    "test-run",
    "--run-attempt",
    "3",
    "--commit-sha",
    "deadbeef",
    "--ref",
    "refs/heads/main",
  ])

  assert exit_code == 0  # noqa: E111
  archive_path = artifact_dir / "coverage-test-run.tar.gz"  # noqa: E111
  assert archive_path.is_file(), "Fallback archive was not created"  # noqa: E111

  with tarfile.open(archive_path, "r:gz") as archive:  # noqa: E111
    members = {member.name for member in archive.getmembers()}
    assert "coverage/latest/index.html" in members
    assert "coverage/latest/coverage.xml" in members
    assert "coverage/latest/shields.json" in members
    summary_file = archive.extractfile("coverage/latest/summary.json")
    assert summary_file is not None
    summary = json.load(summary_file)

  assert summary["run"]["run_attempt"] == "3"  # noqa: E111
  assert summary["coverage_percent"] == pytest.approx(95.23, rel=1e-3)  # noqa: E111


@pytest.mark.ci_only
def test_publish_coverage_supports_custom_prefix_templates(
  tmp_path, monkeypatch
) -> None:
  """Custom prefix templates should produce the expected archive layout."""  # noqa: E111

  coverage_xml = tmp_path / "coverage.xml"  # noqa: E111
  coverage_xml.write_text(  # noqa: E111
    """<?xml version='1.0' ?><coverage line-rate='0.9000'></coverage>""",
    encoding="utf-8",
  )
  html_root = tmp_path / "generated" / "coverage"  # noqa: E111
  html_root.mkdir(parents=True)  # noqa: E111
  (html_root / "index.html").write_text("<html></html>", encoding="utf-8")  # noqa: E111
  artifact_dir = tmp_path / "artifacts"  # noqa: E111

  monkeypatch.delenv("GITHUB_TOKEN", raising=False)  # noqa: E111
  monkeypatch.setenv("GITHUB_REPOSITORY", "pawcontrol/pawcontrol")  # noqa: E111

  exit_code = publish_coverage.main([  # noqa: E111
    "--coverage-xml",
    str(coverage_xml),
    "--coverage-html-index",
    str(html_root / "index.html"),
    "--artifact-directory",
    str(artifact_dir),
    "--mode",
    "pages",
    "--pages-prefix",
    "coverage",
    "--pages-prefix-template",
    "{prefix}/latest",
    "--pages-prefix-template",
    "runs/{run_id}",
    "--pages-prefix-template",
    "attempts/{run_id}/{run_attempt}",
    "--run-id",
    "custom-run",
    "--run-attempt",
    "2",
  ])

  assert exit_code == 0  # noqa: E111
  archive_path = artifact_dir / "coverage-custom-run.tar.gz"  # noqa: E111
  assert archive_path.is_file(), "Fallback archive was not created"  # noqa: E111

  with tarfile.open(archive_path, "r:gz") as archive:  # noqa: E111
    members = {member.name for member in archive.getmembers()}

  assert "coverage/latest/index.html" in members  # noqa: E111
  assert "runs/custom-run/index.html" in members  # noqa: E111
  assert "attempts/custom-run/2/index.html" in members  # noqa: E111


def test_github_pages_publisher_prunes_expired_runs(monkeypatch) -> None:
  """Expired coverage runs should be deleted via the Git data API."""  # noqa: E111

  now = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)  # noqa: E111
  old_timestamp = now - dt.timedelta(days=45)  # noqa: E111
  recent_timestamp = now - dt.timedelta(days=5)  # noqa: E111
  old_summary = {  # noqa: E111
    "encoding": "base64",
    "content": base64.b64encode(
      json.dumps({"generated_at": old_timestamp.isoformat()}).encode("utf-8")
    ).decode("ascii"),
  }
  recent_summary = {  # noqa: E111
    "encoding": "base64",
    "content": base64.b64encode(
      json.dumps({"generated_at": recent_timestamp.isoformat()}).encode("utf-8")
    ).decode("ascii"),
  }
  captured_payloads: dict[str, dict[str, object]] = {}  # noqa: E111

  class DummyResponse:  # noqa: E111
    def __init__(self, payload: object, status: int = 200) -> None:
      self._payload = payload  # noqa: E111
      self.status = status  # noqa: E111

    def read(self) -> bytes:
      return json.dumps(self._payload).encode("utf-8")  # noqa: E111

    def __enter__(self) -> DummyResponse:
      return self  # noqa: E111

    def __exit__(self, *exc: object) -> None:
      return None  # noqa: E111

  def fake_urlopen(request: urllib.request.Request, timeout: int = 0) -> DummyResponse:  # noqa: E111
    url = request.full_url
    method = request.get_method()
    if url.endswith("/contents/coverage?ref=gh-pages") and method == "GET":
      return DummyResponse([  # noqa: E111
        {"type": "dir", "name": "latest"},
        {"type": "dir", "name": "run-new"},
        {"type": "dir", "name": "run-old"},
      ])
    if (
      url.endswith("/contents/coverage/run-old/summary.json?ref=gh-pages")
      and method == "GET"
    ):
      return DummyResponse(old_summary)  # noqa: E111
    if (
      url.endswith("/contents/coverage/run-new/summary.json?ref=gh-pages")
      and method == "GET"
    ):
      return DummyResponse(recent_summary)  # noqa: E111
    if url.endswith("/git/refs/heads/gh-pages") and method == "GET":
      return DummyResponse({"object": {"sha": "base-sha"}})  # noqa: E111
    if url.endswith("/git/trees") and method == "POST":
      payload = json.loads(request.data.decode("utf-8"))  # noqa: E111
      captured_payloads[url] = payload  # noqa: E111
      return DummyResponse({"sha": "tree-sha"})  # noqa: E111
    if url.endswith("/git/commits") and method == "POST":
      return DummyResponse({"sha": "commit-sha"})  # noqa: E111
    if url.endswith("/git/refs/heads/gh-pages") and method == "PATCH":
      return DummyResponse({})  # noqa: E111
    raise AssertionError(f"Unexpected request {method} {url}")

  monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)  # noqa: E111
  publisher = publish_coverage.GitHubPagesPublisher("token", "owner/repo", "gh-pages")  # noqa: E111

  removed = publisher.prune_expired_runs("coverage", dt.timedelta(days=30), now=now)  # noqa: E111

  assert removed == ["coverage/run-old"]  # noqa: E111
  tree_payload = captured_payloads["https://api.github.com/repos/owner/repo/git/trees"]  # noqa: E111
  assert tree_payload["base_tree"] == "base-sha"  # noqa: E111
  assert tree_payload["tree"] == [  # noqa: E111
    {
      "path": "coverage/run-old",
      "mode": "040000",
      "type": "tree",
      "sha": None,
    }
  ]


def test_publish_prune_expired_runs_degrades_on_failure(tmp_path, monkeypatch) -> None:
  """Pruning should degrade gracefully when the API is offline."""  # noqa: E111

  coverage_xml = tmp_path / "coverage.xml"  # noqa: E111
  coverage_xml.write_text(  # noqa: E111
    """<?xml version='1.0' ?><coverage line-rate='0.9523'></coverage>""",
    encoding="utf-8",
  )
  html_root = tmp_path / "generated" / "coverage"  # noqa: E111
  html_root.mkdir(parents=True)  # noqa: E111
  (html_root / "index.html").write_text("<html></html>", encoding="utf-8")  # noqa: E111
  artifact_dir = tmp_path / "artifacts"  # noqa: E111

  monkeypatch.setenv("GITHUB_TOKEN", "token")  # noqa: E111
  monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")  # noqa: E111
  monkeypatch.setattr(  # noqa: E111
    urllib.request,
    "urlopen",
    lambda *args, **kwargs: (_ for _ in ()).throw(urllib.error.URLError("offline")),
  )

  args = publish_coverage.build_cli().parse_args([  # noqa: E111
    "--coverage-xml",
    str(coverage_xml),
    "--coverage-html-index",
    str(html_root / "index.html"),
    "--artifact-directory",
    str(artifact_dir),
    "--mode",
    "pages",
    "--run-id",
    "offline-test",
    "--prune-expired-runs",
  ])

  result = publish_coverage.publish(args)  # noqa: E111

  assert not result.published  # noqa: E111
  assert result.archive_path.is_file()  # noqa: E111


def test_ensure_allowed_github_api_url_rejects_insecure_scheme() -> None:
  """Only HTTPS GitHub API URLs should be accepted."""  # noqa: E111

  with pytest.raises(publish_coverage.PublishError):  # noqa: E111
    publish_coverage.ensure_allowed_github_api_url(
      "http://api.github.com/repos/test/test"
    )


def test_ensure_allowed_github_api_url_rejects_foreign_host() -> None:
  """Non-GitHub hosts must be rejected before making a request."""  # noqa: E111

  with pytest.raises(publish_coverage.PublishError):  # noqa: E111
    publish_coverage.ensure_allowed_github_api_url(
      "https://example.com/repos/test/test"
    )


def test_ensure_allowed_github_api_url_accepts_expected_endpoint() -> None:
  """Valid GitHub API URLs should pass validation."""  # noqa: E111

  publish_coverage.ensure_allowed_github_api_url(  # noqa: E111
    "https://api.github.com/repos/test/test"
  )


def test_publish_uses_custom_prune_max_age(tmp_path, monkeypatch) -> None:
  """Prune window should respect the --prune-max-age-days argument."""  # noqa: E111

  coverage_xml = tmp_path / "coverage.xml"  # noqa: E111
  coverage_xml.write_text(  # noqa: E111
    """<?xml version='1.0' ?><coverage line-rate='0.9523'></coverage>""",
    encoding="utf-8",
  )
  html_root = tmp_path / "generated" / "coverage"  # noqa: E111
  html_root.mkdir(parents=True)  # noqa: E111
  (html_root / "index.html").write_text("<html></html>", encoding="utf-8")  # noqa: E111
  artifact_dir = tmp_path / "artifacts"  # noqa: E111

  monkeypatch.setenv("GITHUB_TOKEN", "token")  # noqa: E111
  monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")  # noqa: E111

  captured_window: dt.timedelta | None = None  # noqa: E111

  class _DummyPublisher:  # noqa: E111
    def __init__(self, *_: object) -> None:
      pass  # noqa: E111

    def publish(self, *_: object, **__: object) -> str:
      return "https://example.com/coverage/latest/index.html"  # noqa: E111

    def prune_expired_runs(self, prefix: str, max_age: dt.timedelta) -> list[str]:
      nonlocal captured_window  # noqa: E111
      captured_window = max_age  # noqa: E111
      return []  # noqa: E111

  monkeypatch.setattr(publish_coverage, "GitHubPagesPublisher", _DummyPublisher)  # noqa: E111

  args = publish_coverage.build_cli().parse_args([  # noqa: E111
    "--coverage-xml",
    str(coverage_xml),
    "--coverage-html-index",
    str(html_root / "index.html"),
    "--artifact-directory",
    str(artifact_dir),
    "--mode",
    "pages",
    "--run-id",
    "custom-age",
    "--prune-expired-runs",
    "--prune-max-age-days",
    "5",
  ])

  result = publish_coverage.publish(args)  # noqa: E111

  assert result.published is True  # noqa: E111
  assert captured_window == dt.timedelta(days=5)  # noqa: E111
