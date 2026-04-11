"""Tests for scripts.sync_contributor_guides."""

from pathlib import Path

import pytest
from scripts import sync_contributor_guides


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_load_canonical_block_uses_sync_markers(tmp_path: Path, monkeypatch) -> None:
    """Only the fenced sync block should be exported when markers exist."""
    canonical = tmp_path / "copilot-instructions.md"
    _write(
        canonical,
        "header\n<!-- SYNC:START -->\nline-a\nline-b\n<!-- SYNC:END -->\nfooter\n",
    )
    monkeypatch.setattr(sync_contributor_guides, "CANONICAL_SOURCE", canonical)

    block = sync_contributor_guides._load_canonical_block()

    assert block == "<!-- SYNC:START -->\nline-a\nline-b\n<!-- SYNC:END -->"


def test_load_canonical_block_wraps_entire_file_without_markers(
    tmp_path: Path, monkeypatch
) -> None:
    """The full file should be wrapped when no sync markers are present."""
    canonical = tmp_path / "copilot-instructions.md"
    _write(canonical, "line-a\nline-b\n")
    monkeypatch.setattr(sync_contributor_guides, "CANONICAL_SOURCE", canonical)

    block = sync_contributor_guides._load_canonical_block()

    assert block == "<!-- SYNC:START -->\nline-a\nline-b\n<!-- SYNC:END -->"


def test_apply_sync_block_replaces_existing_region(tmp_path: Path) -> None:
    """Applying a block should preserve prefix and suffix content."""
    target = tmp_path / "target.md"
    _write(target, "prefix\n<!-- SYNC:START -->\nold\n<!-- SYNC:END -->\nsuffix\n")

    original, updated = sync_contributor_guides._apply_sync_block(
        target,
        "<!-- SYNC:START -->\nnew\n<!-- SYNC:END -->",
    )

    assert "old" in original
    assert updated == "prefix\n<!-- SYNC:START -->\nnew\n<!-- SYNC:END -->\nsuffix\n"


def test_apply_sync_block_requires_markers(tmp_path: Path) -> None:
    """Applying sync should fail fast when the target has no sync markers."""
    target = tmp_path / "target.md"
    _write(target, "prefix\nno markers here\nsuffix\n")

    with pytest.raises(ValueError):
        sync_contributor_guides._apply_sync_block(
            target,
            "<!-- SYNC:START -->\nnew\n<!-- SYNC:END -->",
        )


def test_main_check_mode_reports_out_of_date_file(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """Check mode should exit non-zero when a target file is stale."""
    canonical = tmp_path / "canonical.md"
    target = tmp_path / "target.md"
    _write(canonical, "new text\n")
    _write(target, "<!-- SYNC:START -->\nold text\n<!-- SYNC:END -->\n")
    monkeypatch.setattr(sync_contributor_guides, "CANONICAL_SOURCE", canonical)
    monkeypatch.setattr(sync_contributor_guides, "TARGETS", [target])
    monkeypatch.setattr(
        "sys.argv",
        ["sync_contributor_guides.py", "--check"],
    )

    result = sync_contributor_guides.main()

    output = capsys.readouterr().out
    assert result == 1
    assert "is out of date" in output


def test_main_updates_target_when_not_in_check_mode(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """Sync mode should rewrite stale targets and return success."""
    canonical = tmp_path / "canonical.md"
    target = tmp_path / "target.md"
    _write(canonical, "new text\n")
    _write(target, "<!-- SYNC:START -->\nold text\n<!-- SYNC:END -->\n")
    monkeypatch.setattr(sync_contributor_guides, "CANONICAL_SOURCE", canonical)
    monkeypatch.setattr(sync_contributor_guides, "TARGETS", [target])
    monkeypatch.setattr("sys.argv", ["sync_contributor_guides.py"])

    result = sync_contributor_guides.main()

    output = capsys.readouterr().out
    assert result == 0
    assert "Synced" in output
    assert target.read_text(encoding="utf-8") == (
        "<!-- SYNC:START -->\nnew text\n<!-- SYNC:END -->\n"
    )


def test_main_reports_when_already_synced(tmp_path: Path, monkeypatch, capsys) -> None:
    """No-op runs should print the already-synced message."""
    canonical = tmp_path / "canonical.md"
    target = tmp_path / "target.md"
    _write(canonical, "new text\n")
    _write(target, "<!-- SYNC:START -->\nnew text\n<!-- SYNC:END -->\n")
    monkeypatch.setattr(sync_contributor_guides, "CANONICAL_SOURCE", canonical)
    monkeypatch.setattr(sync_contributor_guides, "TARGETS", [target])
    monkeypatch.setattr("sys.argv", ["sync_contributor_guides.py"])

    result = sync_contributor_guides.main()

    output = capsys.readouterr().out
    assert result == 0
    assert "already match" in output


def test_main_check_mode_reports_when_already_synced(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """Check mode should still return success for already-synced guides."""
    canonical = tmp_path / "canonical.md"
    target = tmp_path / "target.md"
    _write(canonical, "new text\n")
    _write(target, "<!-- SYNC:START -->\nnew text\n<!-- SYNC:END -->\n")
    monkeypatch.setattr(sync_contributor_guides, "CANONICAL_SOURCE", canonical)
    monkeypatch.setattr(sync_contributor_guides, "TARGETS", [target])
    monkeypatch.setattr("sys.argv", ["sync_contributor_guides.py", "--check"])

    result = sync_contributor_guides.main()

    output = capsys.readouterr().out
    assert result == 0
    assert "already match" in output
