"""Tests for scripts.check_legacy_exception_syntax."""

from argparse import Namespace
from pathlib import Path

from scripts import check_legacy_exception_syntax as module


def test_find_legacy_handlers_detects_python2_multi_exception(tmp_path: Path) -> None:
    """Legacy comma-separated handlers should be reported with line numbers."""
    source = tmp_path / "legacy_sample.py"
    source.write_text(
        "\n".join([
            "try:",
            "    pass",
            "except ValueError, TypeError:",
            "    pass",
            "except (ValueError, TypeError):",
            "    pass",
        ]),
        encoding="utf-8",
    )

    assert module._find_legacy_handlers(source) == [3]


def test_main_skips_missing_paths_and_succeeds(
    monkeypatch: object, capsys: object
) -> None:
    """Missing paths should be skipped without failing the guard."""
    monkeypatch.setattr(module, "_parse_args", lambda: Namespace(paths=["missing.py"]))

    assert module.main() == 0
    output = capsys.readouterr().out
    assert "Skipping missing path" in output
    assert "No legacy multi-exception syntax found." in output


def test_main_reports_findings_for_single_file(
    tmp_path: Path, monkeypatch: object, capsys: object
) -> None:
    """A Python file path should be scanned directly and fail when syntax is present."""
    source = tmp_path / "legacy_handler.py"
    source.write_text(
        "\n".join([
            "try:",
            "    pass",
            "except TypeError, ValueError:",
            "    pass",
        ]),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "_parse_args", lambda: Namespace(paths=[str(source)]))

    assert module.main() == 1
    output = capsys.readouterr().out
    assert "Legacy Python 2 multi-exception syntax detected:" in output
    assert f"{source}:3" in output


def test_main_handles_directory_with_no_findings(
    tmp_path: Path, monkeypatch: object, capsys: object
) -> None:
    """Directory scans should pass when all handlers use Python 3 tuple syntax."""
    source = tmp_path / "modern_handler.py"
    source.write_text(
        "\n".join([
            "try:",
            "    pass",
            "except (TypeError, ValueError):",
            "    pass",
        ]),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "_parse_args", lambda: Namespace(paths=[str(tmp_path)]))

    assert module.main() == 0
    output = capsys.readouterr().out
    assert "No legacy multi-exception syntax found." in output
