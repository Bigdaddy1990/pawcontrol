"""Tests for ``scripts.fix_typing_issues``."""

from pathlib import Path
from typing import Any

from scripts.fix_typing_issues import (
  FixStats,
  MypyError,
  _apply_single_error_fix,
  _remove_redundant_cast,
  parse_mypy_errors,
)


def test_parse_mypy_errors_extracts_error_code(tmp_path: Path) -> None:
  """The parser should keep path, line and error code."""
  output = (
    'custom_components/pawcontrol/module.py:10: error: Redundant cast to "int" '
    "[redundant-cast]"
  )

  parsed = parse_mypy_errors(output, tmp_path)

  assert len(parsed) == 1
  expected_path = (tmp_path / "custom_components/pawcontrol/module.py").resolve()
  assert parsed[0].path == expected_path
  assert parsed[0].line == 10
  assert parsed[0].code == "redundant-cast"


def test_remove_redundant_cast_strips_cast_wrapper() -> None:
  """Redundant cast wrappers should be dropped."""
  line = "value = cast(int, config.get('answer', 0))"

  updated, changed = _remove_redundant_cast(line)

  assert changed is True
  assert updated == "value = config.get('answer', 0)"


def test_apply_single_error_fix_for_unused_ignore() -> None:
  """Unused MyPy ignores should be removed from the line."""
  stats = FixStats()
  error = MypyError(
    path=Path("custom_components/pawcontrol/module.py"),
    line=4,
    message='Unused "type: ignore" comment',
    code="unused-ignore",
  )

  updated, changed = _apply_single_error_fix(
    error, "value = 1  # type: ignore[arg-type]", stats
  )

  assert changed is True
  assert updated == "value = 1"
  assert stats.unused_ignore == 1


def test_apply_single_error_fix_for_type_arg_callable() -> None:
  """Bare Callable annotations should get default type arguments."""
  stats = FixStats()
  error = MypyError(
    path=Path("custom_components/pawcontrol/module.py"),
    line=12,
    message='Missing type parameters for generic type "Callable"',
    code="type-arg",
  )

  updated, changed = _apply_single_error_fix(
    error,
    "handler: Callable = callback",
    stats,
  )

  assert changed is True
  assert updated == "handler: Callable[..., Any] = callback"
  assert stats.callable_type_arg == 1


def test_apply_single_error_fix_for_type_arg_task() -> None:
  """Bare asyncio Task annotations should get a value type."""
  stats = FixStats()
  error = MypyError(
    path=Path("custom_components/pawcontrol/module.py"),
    line=18,
    message='Missing type parameters for generic type "Task"',
    code="type-arg",
  )

  updated, changed = _apply_single_error_fix(
    error,
    "job: Task | None = None",
    stats,
  )

  assert changed is True
  assert updated == "job: Task[Any] | None = None"
  assert stats.task_type_arg == 1
