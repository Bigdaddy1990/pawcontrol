"""Tests for ``scripts.fix_mypy_issues``."""

from __future__ import annotations

from pathlib import Path

from scripts.fix_mypy_issues import (
    _build_utils_stub,
    _extract_public_names,
    _remove_redundant_cast,
    _remove_unused_ignore,
)


def test_remove_redundant_cast_from_line() -> None:
    """The cast wrapper should be removed while preserving expression."""
    updated, changed = _remove_redundant_cast("value = cast(int, config.get('x', 1))")

    assert changed is True
    assert updated == "value = config.get('x', 1)"


def test_remove_unused_ignore_from_line_list() -> None:
    """Unused ignore comments should be stripped from target lines."""
    lines = ["a = 1", "b = 2  # type: ignore[arg-type]"]

    changed = _remove_unused_ignore(lines, 2)

    assert changed is True
    assert lines[1] == "b = 2"


def test_extract_public_names_prefers_static_all(tmp_path: Path) -> None:
    """When ``__all__`` is present, names should come from it."""
    module = tmp_path / "example.py"
    module.write_text(
        '"""x"""\n__all__ = ["alpha", "beta"]\n' "def hidden() -> None:\n    pass\n",
        encoding="utf-8",
    )

    exported = _extract_public_names(module)

    assert exported == ["alpha", "beta"]


def test_build_utils_stub_contains_expected_exports() -> None:
    """Generated stub should include canonical utils exports."""
    content = _build_utils_stub()

    assert "from ._legacy import *" in content
    assert "serialize_entity_attributes" in content
    assert "__all__: list[str] = [" in content
