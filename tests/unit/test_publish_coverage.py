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
    """The publisher should degrade to an archive when GitHub is unavailable."""

    coverage_xml = tmp_path / "coverage.xml"
    coverage_xml.write_text(
        """<?xml version='1.0' ?><coverage line-rate='0.9523'></coverage>""",
        encoding="utf-8",
    )
    html_root = tmp_path / "generated" / "coverage"
    html_root.mkdir(parents=True)
    (html_root / "index.html").write_text("<html></html>", encoding="utf-8")
    (html_root / "style.css").write_text("body {color: #333;}", encoding="utf-8")
    artifact_dir = tmp_path / "artifacts"

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_REPOSITORY", "pawcontrol/pawcontrol")

    exit_code = publish_coverage.main(
        [
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
        ]
    )

    assert exit_code == 0
    archive_path = artifact_dir / "coverage-test-run.tar.gz"
    assert archive_path.is_file(), "Fallback archive was not created"

    with tarfile.open(archive_path, "r:gz") as archive:
        members = {member.name for member in archive.getmembers()}
        assert "coverage/latest/index.html" in members
        assert "coverage/latest/coverage.xml" in members
        assert "coverage/latest/shields.json" in members
        summary_file = archive.extractfile("coverage/latest/summary.json")
        assert summary_file is not None
        summary = json.load(summary_file)

    assert summary["run"]["run_attempt"] == "3"
    assert summary["coverage_percent"] == pytest.approx(95.23, rel=1e-3)


@pytest.mark.ci_only
def test_publish_coverage_supports_custom_prefix_templates(
    tmp_path, monkeypatch
) -> None:
    """Custom prefix templates should produce the expected archive layout."""

    coverage_xml = tmp_path / "coverage.xml"
    coverage_xml.write_text(
        """<?xml version='1.0' ?><coverage line-rate='0.9000'></coverage>""",
        encoding="utf-8",
    )
    html_root = tmp_path / "generated" / "coverage"
    html_root.mkdir(parents=True)
    (html_root / "index.html").write_text("<html></html>", encoding="utf-8")
    artifact_dir = tmp_path / "artifacts"

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_REPOSITORY", "pawcontrol/pawcontrol")

    exit_code = publish_coverage.main(
        [
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
        ]
    )

    assert exit_code == 0
    archive_path = artifact_dir / "coverage-custom-run.tar.gz"
    assert archive_path.is_file(), "Fallback archive was not created"

    with tarfile.open(archive_path, "r:gz") as archive:
        members = {member.name for member in archive.getmembers()}

    assert "coverage/latest/index.html" in members
    assert "runs/custom-run/index.html" in members
    assert "attempts/custom-run/2/index.html" in members


def test_github_pages_publisher_prunes_expired_runs(monkeypatch) -> None:
    """Expired coverage runs should be deleted via the Git data API."""

    now = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
    old_timestamp = now - dt.timedelta(days=45)
    recent_timestamp = now - dt.timedelta(days=5)
    old_summary = {
        "encoding": "base64",
        "content": base64.b64encode(
            json.dumps({"generated_at": old_timestamp.isoformat()}).encode("utf-8")
        ).decode("ascii"),
    }
    recent_summary = {
        "encoding": "base64",
        "content": base64.b64encode(
            json.dumps({"generated_at": recent_timestamp.isoformat()}).encode("utf-8")
        ).decode("ascii"),
    }
    captured_payloads: dict[str, dict[str, object]] = {}

    class DummyResponse:
        def __init__(self, payload: object, status: int = 200) -> None:
            self._payload = payload
            self.status = status

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

        def __enter__(self) -> DummyResponse:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    def fake_urlopen(
        request: urllib.request.Request, timeout: int = 0
    ) -> DummyResponse:
        url = request.full_url
        method = request.get_method()
        if url.endswith("/contents/coverage?ref=gh-pages") and method == "GET":
            return DummyResponse(
                [
                    {"type": "dir", "name": "latest"},
                    {"type": "dir", "name": "run-new"},
                    {"type": "dir", "name": "run-old"},
                ]
            )
        if (
            url.endswith("/contents/coverage/run-old/summary.json?ref=gh-pages")
            and method == "GET"
        ):
            return DummyResponse(old_summary)
        if (
            url.endswith("/contents/coverage/run-new/summary.json?ref=gh-pages")
            and method == "GET"
        ):
            return DummyResponse(recent_summary)
        if url.endswith("/git/refs/heads/gh-pages") and method == "GET":
            return DummyResponse({"object": {"sha": "base-sha"}})
        if url.endswith("/git/trees") and method == "POST":
            payload = json.loads(request.data.decode("utf-8"))
            captured_payloads[url] = payload
            return DummyResponse({"sha": "tree-sha"})
        if url.endswith("/git/commits") and method == "POST":
            return DummyResponse({"sha": "commit-sha"})
        if url.endswith("/git/refs/heads/gh-pages") and method == "PATCH":
            return DummyResponse({})
        raise AssertionError(f"Unexpected request {method} {url}")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    publisher = publish_coverage.GitHubPagesPublisher("token", "owner/repo", "gh-pages")

    removed = publisher.prune_expired_runs("coverage", dt.timedelta(days=30), now=now)

    assert removed == ["coverage/run-old"]
    tree_payload = captured_payloads[
        "https://api.github.com/repos/owner/repo/git/trees"
    ]
    assert tree_payload["base_tree"] == "base-sha"
    assert tree_payload["tree"] == [
        {
            "path": "coverage/run-old",
            "mode": "040000",
            "type": "tree",
            "sha": None,
        }
    ]


def test_publish_prune_expired_runs_degrades_on_failure(tmp_path, monkeypatch) -> None:
    """Pruning should degrade gracefully when the API is offline."""

    coverage_xml = tmp_path / "coverage.xml"
    coverage_xml.write_text(
        """<?xml version='1.0' ?><coverage line-rate='0.9523'></coverage>""",
        encoding="utf-8",
    )
    html_root = tmp_path / "generated" / "coverage"
    html_root.mkdir(parents=True)
    (html_root / "index.html").write_text("<html></html>", encoding="utf-8")
    artifact_dir = tmp_path / "artifacts"

    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(urllib.error.URLError("offline")),
    )

    args = publish_coverage.build_cli().parse_args(
        [
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
        ]
    )

    result = publish_coverage.publish(args)

    assert not result.published
    assert result.archive_path.is_file()


def test_ensure_allowed_github_api_url_rejects_insecure_scheme() -> None:
    """Only HTTPS GitHub API URLs should be accepted."""

    with pytest.raises(publish_coverage.PublishError):
        publish_coverage.ensure_allowed_github_api_url(
            "http://api.github.com/repos/test/test"
        )


def test_ensure_allowed_github_api_url_rejects_foreign_host() -> None:
    """Non-GitHub hosts must be rejected before making a request."""

    with pytest.raises(publish_coverage.PublishError):
        publish_coverage.ensure_allowed_github_api_url(
            "https://example.com/repos/test/test"
        )


def test_ensure_allowed_github_api_url_accepts_expected_endpoint() -> None:
    """Valid GitHub API URLs should pass validation."""

    publish_coverage.ensure_allowed_github_api_url(
        "https://api.github.com/repos/test/test"
    )


def test_publish_uses_custom_prune_max_age(tmp_path, monkeypatch) -> None:
    """Prune window should respect the --prune-max-age-days argument."""

    coverage_xml = tmp_path / "coverage.xml"
    coverage_xml.write_text(
        """<?xml version='1.0' ?><coverage line-rate='0.9523'></coverage>""",
        encoding="utf-8",
    )
    html_root = tmp_path / "generated" / "coverage"
    html_root.mkdir(parents=True)
    (html_root / "index.html").write_text("<html></html>", encoding="utf-8")
    artifact_dir = tmp_path / "artifacts"

    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

    captured_window: dt.timedelta | None = None

    class _DummyPublisher:
        def __init__(self, *_: object) -> None:
            pass

        def publish(self, *_: object, **__: object) -> str:
            return "https://example.com/coverage/latest/index.html"

        def prune_expired_runs(self, prefix: str, max_age: dt.timedelta) -> list[str]:
            nonlocal captured_window
            captured_window = max_age
            return []

    monkeypatch.setattr(publish_coverage, "GitHubPagesPublisher", _DummyPublisher)

    args = publish_coverage.build_cli().parse_args(
        [
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
        ]
    )

    result = publish_coverage.publish(args)

    assert result.published is True
    assert captured_window == dt.timedelta(days=5)
