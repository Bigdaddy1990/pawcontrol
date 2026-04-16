"""Tests for scripts.enforce_test_todo_policy."""

from pathlib import Path
import sys

from scripts import enforce_test_todo_policy

TODO_TOKEN = "TO" + "DO"


def test_find_todos_reports_matches(tmp_path: Path) -> None:  # noqa: D103
    test_file = tmp_path / "test_example.py"
    todo_line = f"assert True  # {TODO_TOKEN}: replace with real assertion"
    test_file.write_text(
        f"def test_example():\n    {todo_line}\n",
        encoding="utf-8",
    )

    findings = enforce_test_todo_policy._find_todos(test_file)

    assert findings == [(2, todo_line)]


def test_main_fails_when_todo_is_present(tmp_path: Path, monkeypatch) -> None:  # noqa: D103
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_example.py").write_text(
        f"def test_example():\n    assert True  # {TODO_TOKEN} remove\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["enforce_test_todo_policy"])

    assert enforce_test_todo_policy.main() == 1


def test_main_passes_when_no_todo_marker_exists(tmp_path: Path, monkeypatch) -> None:  # noqa: D103
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_example.py").write_text(
        "def test_example():\n    assert True\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["enforce_test_todo_policy"])

    assert enforce_test_todo_policy.main() == 0
