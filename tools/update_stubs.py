#!/usr/bin/env python3
"""Update Home Assistant stub metadata for PawControl.

This helper keeps the lightweight Home Assistant stubs in sync with the
upstream release cadence. It records the target release, the source used to
generate or validate stub contracts, and a compact digest of the referenced
release notes. The metadata keeps CI and local workflows aligned without
requiring the full upstream repository during quick checks.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen

DEFAULT_OUTPUT: Final[Path] = Path('tests/helpers/homeassistant_stub_metadata.json')
DEFAULT_TARGETS: Final[tuple[str, ...]] = (
    'config_entries',
    'diagnostics',
    'device_registry',
    'entity_registry',
    'repairs',
)


def _read_notes_from_url(url: str) -> str:
    """Return the contents of ``url`` as text, tolerating network failures."""

    parsed = urlparse(url)
    if parsed.scheme not in {'http', 'https'}:
        return ''

    try:
        with urlopen(url, timeout=10) as response:
            charset = response.headers.get_content_charset() or 'utf-8'
            return response.read().decode(charset)
    except (OSError, URLError):
        return ''


def _load_release_notes(path: Path | None, url: str | None) -> str:
    """Load release notes from a local file or remote source."""

    if path is not None and path.exists():
        return path.read_text(encoding='utf-8')

    if url:
        return _read_notes_from_url(url)

    return ''


def _extract_note_summary(notes: str, *, max_lines: int = 20) -> list[str]:
    """Return a compact summary of the provided release notes."""

    if not notes:
        return []

    summary: list[str] = []
    for line in notes.splitlines():
        if line.startswith('#'):
            continue
        line = line.strip()
        if not line:
            continue
        summary.append(line)
        if len(summary) >= max_lines:
            break

    return summary


def _build_metadata(
    *,
    version: str,
    notes_source: str,
    notes: str,
    targets: tuple[str, ...],
) -> dict[str, Any]:
    """Construct a JSON-serialisable metadata payload."""

    return {
        'version': version,
        'notes_source': notes_source,
        'updated_at': datetime.now(UTC).isoformat(),
        'targets': sorted(targets),
        'note_summary': _extract_note_summary(notes),
    }


def update_stub_metadata(
    *,
    version: str,
    output: Path = DEFAULT_OUTPUT,
    notes_path: Path | None = None,
    notes_url: str | None = None,
    targets: tuple[str, ...] = DEFAULT_TARGETS,
) -> Path:
    """Create or refresh the stub metadata file."""

    notes = _load_release_notes(notes_path, notes_url)
    source = str(notes_path) if notes_path else (notes_url or 'unspecified')
    metadata = _build_metadata(
        version=version,
        notes_source=source,
        notes=notes,
        targets=targets,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding='utf-8')
    return output


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(
        description='Update Home Assistant stub metadata for PawControl.'
    )
    parser.add_argument(
        '--version',
        required=True,
        help='Home Assistant Core release version used for stub validation.',
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Target metadata path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        '--notes-path',
        type=Path,
        help='Optional path to a local release notes file.',
    )
    parser.add_argument(
        '--notes-url',
        help='Optional URL to fetch Home Assistant release notes.',
    )
    parser.add_argument(
        '--targets',
        nargs='*',
        help='Override the stub target modules recorded in the metadata.',
    )
    return parser.parse_args()


def main() -> None:
    """Entry point for the CLI."""

    args = parse_args()
    target_modules = tuple(args.targets) if args.targets else DEFAULT_TARGETS
    output_path = update_stub_metadata(
        version=args.version,
        output=args.output,
        notes_path=args.notes_path,
        notes_url=args.notes_url,
        targets=target_modules,
    )
    print(f"Updated stub metadata at {output_path}")


if __name__ == '__main__':
    main()
