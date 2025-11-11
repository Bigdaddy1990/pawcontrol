"""Audit PawControl modules for untyped dictionary aliases.

This helper scans Python sources for ``dict[str, Any]`` and similar patterns so
contributors can keep migrating the integration toward TypedDicts and PEP 695
aliases.  The tool is intentionally lightweight so it can run inside the
repository's strict lint environment without additional dependencies.

Usage::

    python -m script.check_typed_dicts --path custom_components/pawcontrol

Pass ``--fail-on-findings`` to exit with status ``1`` when the scan discovers
matches.  This is useful for pre-commit hooks or CI jobs that should block
regressions once the migration finishes.
"""

from __future__ import annotations

import re
import sys
from argparse import ArgumentParser, Namespace
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

PATTERNS: dict[str, re.Pattern[str]] = {
    "dict[str, Any]": re.compile(r"dict\[\s*str\s*,\s*Any\s*\]"),
    "Mapping[str, Any]": re.compile(r"Mapping\[\s*str\s*,\s*Any\s*\]"),
    "MutableMapping[str, Any]": re.compile(r"MutableMapping\[\s*str\s*,\s*Any\s*\]"),
}

PYTHON_EXTENSIONS: tuple[str, ...] = (".py",)


@dataclass(frozen=True, slots=True)
class Finding:
    """Represents a static analysis match returned by the audit."""

    path: Path
    line_number: int
    pattern: str
    line: str


def _iter_python_files(paths: Iterable[Path]) -> Iterable[Path]:
    for base in paths:
        if base.is_file() and base.suffix in PYTHON_EXTENSIONS:
            yield base
            continue
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if path.name == "__init__.py" and path.parent.name == "__pycache__":
                continue
            yield path


def _scan_file(path: Path) -> list[Finding]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as err:  # pragma: no cover - filesystem failure surfaces to caller
        raise RuntimeError(f"Failed to read {path}: {err}") from err

    findings: list[Finding] = []
    for name, pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            line_number = text.count("\n", 0, match.start()) + 1
            line_start = text.rfind("\n", 0, match.start()) + 1
            line_end = text.find("\n", match.end())
            if line_end == -1:
                line_end = len(text)
            findings.append(
                Finding(
                    path=path,
                    line_number=line_number,
                    pattern=name,
                    line=text[line_start:line_end].strip(),
                )
            )
    return findings


def _parse_args(argv: list[str]) -> Namespace:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        action="append",
        type=Path,
        default=[Path("custom_components/pawcontrol")],
        help="Directory or file to scan. Repeat for additional locations.",
    )
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Exit with status 1 if any matches are found.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    findings: list[Finding] = []

    for path in args.path:
        if not path.exists():
            raise SystemExit(f"Scan path does not exist: {path}")
        for file_path in _iter_python_files([path]):
            findings.extend(_scan_file(file_path))

    if not findings:
        print("No untyped dictionary aliases detected.")
        return 0

    project_root = Path.cwd().resolve()
    for finding in sorted(findings, key=lambda item: (item.path, item.line_number)):
        resolved = finding.path.resolve()
        try:
            rel_path = resolved.relative_to(project_root)
        except ValueError:
            rel_path = resolved
        print(f"{rel_path}:{finding.line_number}: {finding.pattern}: {finding.line}")

    print(f"Total findings: {len(findings)}")

    if args.fail_on_findings:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - manual invocation helper
    raise SystemExit(main())
