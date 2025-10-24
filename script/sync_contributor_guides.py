"""Synchronise assistant contributor guides with the canonical instructions.

This utility mirrors `.github/copilot-instructions.md` into the assistant-
scoped contributor guides so Copilot, Claude, and Gemini stay aligned. The
script replaces the content between the `SYNC:START`/`SYNC:END` markers in each
assistant file with the canonical document. Run the script without arguments to
update the guides or pass ``--check`` to verify that they are already in sync.
"""

from __future__ import annotations

import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_PATH = REPO_ROOT / ".github" / "copilot-instructions.md"
TARGETS = (
    REPO_ROOT / ".claude" / "agents" / "copilot-instructions.md",
    REPO_ROOT / ".gemini" / "styleguide.md",
)
MARKER_START = "<!-- SYNC:START -->"
MARKER_END = "<!-- SYNC:END -->"


def _replacement_block() -> str:
    canonical = CANONICAL_PATH.read_text(encoding="utf-8").strip()
    return f"\n{canonical}\n"


def _extract_marked_region(content: str, path: Path) -> tuple[int, int]:
    try:
        start = content.index(MARKER_START)
        end = content.index(MARKER_END)
    except ValueError as exc:  # pragma: no cover - explicit error message below
        raise ValueError(
            f"Missing contributor guide sync markers in {path}."
        ) from exc

    if end <= start:
        raise ValueError(
            f"Contributor guide sync markers are misordered in {path}."
        )

    return start + len(MARKER_START), end


def _sync_file(path: Path, replacement: str, check_only: bool) -> bool:
    content = path.read_text(encoding="utf-8")
    block_start, block_end = _extract_marked_region(content, path)
    current = content[block_start:block_end]

    if current.strip() == replacement.strip():
        return False

    if check_only:
        raise SystemExit(
            f"{path} is out of date. Run `python -m script.sync_contributor_guides` to refresh it."
        )

    new_content = (
        content[:block_start].rstrip()
        + "\n"
        + replacement.strip()
        + "\n"
        + content[block_end:]
    )
    path.write_text(new_content, encoding="utf-8")
    return True


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only verify that contributor guides are in sync.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    replacement = _replacement_block()
    changed = False

    for target in TARGETS:
        changed |= _sync_file(target, replacement, args.check)

    if changed:
        print("Updated contributor guide sync markers.")
    elif not args.check:
        print("Contributor guides already up to date.")


if __name__ == "__main__":
    main()
