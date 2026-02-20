"""Ensure assistant contributor guides stay aligned with the canonical content."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MARKER_START = "<!-- SYNC:START -->"
MARKER_END = "<!-- SYNC:END -->"
CANONICAL_PATH = ROOT / ".github" / "copilot-instructions.md"
TARGETS = (
    ROOT / ".claude" / "agents" / "copilot-instructions.md",
    ROOT / ".gemini" / "styleguide.md",
)


def _synced_block(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    start = content.index(MARKER_START) + len(MARKER_START)
    end = content.index(MARKER_END)
    return _normalise_markdown(content[start:end])


def _normalise_markdown(content: str) -> str:
    """Return markdown content with stable line endings and trailing spacing."""
    return "\n".join(line.rstrip() for line in content.strip().splitlines())


def test_assistant_guides_match_canonical() -> None:
    canonical = _normalise_markdown(CANONICAL_PATH.read_text(encoding="utf-8"))
    for target in TARGETS:
        assert _synced_block(target) == canonical, target
