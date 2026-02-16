"""Synchronise assistant-specific contributor guides with the canonical copy."""

import argparse
from pathlib import Path

SYNC_START = "<!-- SYNC:START -->"
SYNC_END = "<!-- SYNC:END -->"
REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_SOURCE = REPO_ROOT / ".github" / "copilot-instructions.md"
TARGETS = [
  REPO_ROOT / ".claude" / "agents" / "copilot-instructions.md",
  REPO_ROOT / ".gemini" / "styleguide.md",
]


def _load_canonical_block() -> str:
  content = CANONICAL_SOURCE.read_text(encoding="utf-8")  # noqa: E111
  if SYNC_START in content and SYNC_END in content:  # noqa: E111
    start = content.index(SYNC_START) + len(SYNC_START)
    end = content.index(SYNC_END, start)
    block = content[start:end].strip("\n")
  else:  # noqa: E111
    block = content.strip("\n")
  return f"{SYNC_START}\n{block}\n{SYNC_END}"  # noqa: E111


def _apply_sync_block(target: Path, block: str) -> tuple[str, str]:
  text = target.read_text(encoding="utf-8")  # noqa: E111
  start = text.index(SYNC_START)  # noqa: E111
  end = text.index(SYNC_END, start) + len(SYNC_END)  # noqa: E111
  return text, text[:start] + block + text[end:]  # noqa: E111


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)  # noqa: E111
  parser.add_argument(  # noqa: E111
    "--check",
    action="store_true",
    help="only verify the files are synced",
  )
  args = parser.parse_args()  # noqa: E111

  block = _load_canonical_block()  # noqa: E111
  had_changes = False  # noqa: E111

  for target in TARGETS:  # noqa: E111
    original, updated = _apply_sync_block(target, block)
    if updated != original:
      if args.check:  # noqa: E111
        print(f"{target} is out of date with {CANONICAL_SOURCE}")
      else:  # noqa: E111
        target.write_text(updated, encoding="utf-8")
        print(f"Synced {target} with {CANONICAL_SOURCE}")
      had_changes = True  # noqa: E111

  if args.check and had_changes:  # noqa: E111
    return 1
  if not had_changes:  # noqa: E111
    print("Contributor guides already match the canonical instructions.")
  return 0  # noqa: E111


if __name__ == "__main__":
  raise SystemExit(main())  # noqa: E111
