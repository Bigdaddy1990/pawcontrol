"""Ensure docstring lint regressions are prevented via Ruff diagnostics."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

DEFAULT_BASELINE = Path("generated/lint_baselines/docstring_missing.json")
RUFF_ARGS = (
    "check",
    "custom_components/pawcontrol",
    "--select",
    "D1",
    "--output-format",
    "json",
)


def _resolve_ruff_command() -> list[str]:
    """Return a fully-qualified command for invoking Ruff safely.

    The command is built using ``python -m ruff`` when possible so that the
    interpreter already running this script is re-used.  Falling back to a
    ``ruff`` binary from ``PATH`` uses the absolute path detected by
    :func:`shutil.which` to avoid executing an unexpected executable that might
    be shadowing the desired one.
    """

    if importlib.util.find_spec("ruff") is not None:
        return [sys.executable, "-m", "ruff", *RUFF_ARGS]

    resolved = shutil.which("ruff")
    if not resolved:
        raise SystemExit(
            "Unable to locate the Ruff executable. Ensure it is installed and on PATH."
        )

    return [resolved, *RUFF_ARGS]


def load_baseline(path: Path) -> list[dict[str, object]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise SystemExit(
            f"Baseline file '{path}' is missing. Run with --update-baseline to create it."
        ) from exc


def write_baseline(path: Path, diagnostics: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(diagnostics, handle, indent=2)
        handle.write("\n")


def collect_diagnostics(
    repo_root: Path, command: Sequence[str]
) -> list[dict[str, object]]:
    try:
        process = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            cwd=repo_root,
            check=False,
        )
    except FileNotFoundError as exc:
        raise SystemExit(
            f"Failed to execute Ruff command '{command[0]}': {exc.strerror}."
        ) from exc
    if process.returncode not in (0, 1):
        sys.stderr.write(process.stdout)
        sys.stderr.write(process.stderr)
        raise SystemExit(process.returncode)

    raw = json.loads(process.stdout) if process.stdout.strip() else []

    diagnostics = []
    for entry in raw:
        filename = Path(entry["filename"]).resolve()
        try:
            relative = filename.relative_to(repo_root)
        except ValueError:
            relative = filename
        diagnostics.append(
            {
                "code": entry["code"],
                "path": relative.as_posix(),
                "line": entry["location"]["row"],
                "message": entry["message"],
            }
        )

    diagnostics.sort(key=lambda item: (item["path"], item["line"], item["code"]))
    return diagnostics


def compare(
    baseline: list[dict[str, object]],
    diagnostics: list[dict[str, object]],
) -> tuple[set[tuple[str, int, str]], set[tuple[str, int, str]]]:
    baseline_keys = {
        (item["path"], int(item["line"]), item["code"]) for item in baseline
    }
    current_keys = {
        (item["path"], int(item["line"]), item["code"]) for item in diagnostics
    }
    new_failures = current_keys - baseline_keys
    resolved = baseline_keys - current_keys
    return new_failures, resolved


def format_entry(entry: tuple[str, int, str]) -> str:
    path, line, code = entry
    return f"{path}:{line} ({code})"


def run() -> int:
    parser = argparse.ArgumentParser(
        description="Fail if new docstring lint violations are introduced.",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Update the baseline to match the current state of docstring violations.",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE,
        help="Path to the docstring baseline file.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    ruff_command = _resolve_ruff_command()
    diagnostics = collect_diagnostics(repo_root, ruff_command)

    if args.update_baseline:
        write_baseline(args.baseline, diagnostics)
        print(
            f"Docstring baseline updated with {len(diagnostics)} entries at {args.baseline}.",
        )
        return 0

    baseline = load_baseline(args.baseline)
    new_failures, resolved = compare(baseline, diagnostics)

    exit_code = 0
    if new_failures:
        exit_code = 1
        print("New docstring violations detected:")
        for entry in sorted(new_failures):
            print(f"  - {format_entry(entry)}")
        print(
            "\nAdd docstrings or update the baseline once the violations are resolved."
        )

    if resolved:
        exit_code = 1
        print("Existing baseline violations resolved. Please update the baseline:")
        for entry in sorted(resolved):
            print(f"  - {format_entry(entry)}")
        print(
            "\nRun 'python scripts/enforce_docstring_baseline.py --update-baseline' "
            "after removing resolved entries to keep the baseline in sync."
        )

    if exit_code == 0:
        print("Docstring baseline check passed: no new violations introduced.")
    return exit_code


if __name__ == "__main__":
    sys.exit(run())
