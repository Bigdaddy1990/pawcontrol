"""Tests for the localization flag synchronization helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from script import sync_localization_flags


def _build_translations(
    label_en: str, label_de: str
) -> dict[str, dict[str, dict[str, str]]]:
    return {
        "en": {"common": {"setup_flags_panel_flag_test": label_en}},
        "de": {"common": {"setup_flags_panel_flag_test": label_de}},
    }


def test_update_markdown_table_writes_expected_rows(tmp_path: Path) -> None:
    """The Markdown helper should replace the setup-flags table in-place."""

    markdown = tmp_path / "diagnostik.md"
    markdown.write_text(
        "\n".join(
            [
                "Intro",
                "| Übersetzungsschlüssel | Englisch (`en`) | Deutsch (`de`) |",
                "| --- | --- | --- |",
                "| component.pawcontrol.common.setup_flags_panel_flag_test | old | alt |",
                "Outro",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    updated = sync_localization_flags._update_markdown_table(
        markdown,
        ["setup_flags_panel_flag_test"],
        _build_translations("English", "Deutsch"),
        ["en", "de"],
        check_only=False,
    )

    assert updated is True
    content = markdown.read_text(encoding="utf-8")
    assert (
        "| component.pawcontrol.common.setup_flags_panel_flag_test | English | Deutsch |"
        in content
    )


def test_update_markdown_table_check_mode_detects_drift(tmp_path: Path) -> None:
    """Check-only runs should fail when the Markdown table differs."""

    markdown = tmp_path / "diagnostik.md"
    markdown.write_text(
        "\n".join(
            [
                "Intro",
                "| Übersetzungsschlüssel | Englisch (`en`) | Deutsch (`de`) |",
                "| --- | --- | --- |",
                "| component.pawcontrol.common.setup_flags_panel_flag_test | English | Deutsch |",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit):
        sync_localization_flags._update_markdown_table(
            markdown,
            ["setup_flags_panel_flag_test"],
            _build_translations("Updated", "Deutsch"),
            ["en", "de"],
            check_only=True,
        )
