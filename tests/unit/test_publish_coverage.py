"""Regression tests for the coverage publishing helper."""

from __future__ import annotations

import json
import tarfile

import pytest
from script import publish_coverage


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
