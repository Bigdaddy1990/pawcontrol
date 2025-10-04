"""Ensure docstring lint regressions are prevented via Ruff diagnostics."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
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


def _execute_ruff(repo_root: Path, args: Sequence[str]) -> tuple[int, str, str]:
    """Run Ruff using its Python entrypoint and capture output."""

    try:
        from ruff import __main__ as ruff_main
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Ruff is not installed. Install it in the active environment to run the check."
        ) from exc

    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    previous_cwd = Path.cwd()
    try:
        os.chdir(repo_root)
        if hasattr(ruff_main, "main"):
            with (
                contextlib.redirect_stdout(stdout_buffer),
                contextlib.redirect_stderr(stderr_buffer),
            ):
                exit_code = ruff_main.main(list(args))
        else:
            ruff_bin = Path(ruff_main.find_ruff_bin())
            completed = subprocess.run(
                [str(ruff_bin), *args],
                check=False,
                capture_output=True,
                text=True,
            )
            exit_code = completed.returncode
            stdout_buffer.write(completed.stdout)
            stderr_buffer.write(completed.stderr)
    finally:
        os.chdir(previous_cwd)

    return exit_code, stdout_buffer.getvalue(), stderr_buffer.getvalue()


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


def collect_diagnostics(repo_root: Path) -> list[dict[str, object]]:
    exit_code, stdout, stderr = _execute_ruff(repo_root, RUFF_ARGS)
    if exit_code not in (0, 1):
        sys.stderr.write(stdout)
        sys.stderr.write(stderr)
        raise SystemExit(exit_code)

    raw = json.loads(stdout) if stdout.strip() else []

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
    diagnostics = collect_diagnostics(repo_root)

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
