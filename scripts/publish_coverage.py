"""Publish coverage artifacts.

This helper is intentionally lightweight. The reusable workflow optionally calls it to
prepare a GitHub Pages bundle containing the HTML coverage report and a small metadata
file.

The workflow passes paths for the generated coverage XML and the HTML index.
When running in "pages" mode we simply copy the HTML report directory into the
requested artifact directory.

This script does *not* push to GitHub Pages by itself; the workflow is responsible for
uploading the prepared bundle.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument("--coverage-xml", type=Path, required=True)
    parser.add_argument("--coverage-html-index", type=Path, required=True)
    parser.add_argument("--artifact-directory", type=Path, required=True)

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare GitHub Pages artifact for coverage"
    )
    parser.add_argument(
        "--coverage-html-index", required=True, help="Path to coverage HTML index.html"
    )
    parser.add_argument(
        "--public-dir", required=True, help="Output directory for Pages artifact"
    )
    parser.add_argument(
        "--mode",
        default="pages",
        choices=("pages",),
        help="Publishing mode (reserved for future use)",
    )

    args = parser.parse_args()

    index_path = Path(args.coverage_html_index).resolve()
    public_dir = Path(args.public_dir).resolve()

    if not index_path.exists():
        raise FileNotFoundError(f"Coverage HTML index not found: {index_path}")
    parser.add_argument("--mode", choices={"pages", "artifact"}, default="artifact")
    parser.add_argument("--pages-branch", default="gh-pages")
    parser.add_argument("--pages-prefix", default="coverage")

    parser.add_argument("--run-id", default="")
    parser.add_argument("--run-attempt", default="")
    parser.add_argument("--commit-sha", default="")
    parser.add_argument("--ref", default="")

    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    coverage_xml = args.coverage_xml
    html_index = args.coverage_html_index

    if not coverage_xml.exists():
        raise SystemExit(f"coverage xml not found: {coverage_xml}")
    if not html_index.exists():
        raise SystemExit(f"coverage html index not found: {html_index}")

    artifact_dir = args.artifact_directory
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # Copy full HTML directory (index.html lives inside)
    html_dir = html_index.parent
    target_html_dir = artifact_dir / "html"

    if target_html_dir.exists():
        shutil.rmtree(target_html_dir)

    shutil.copytree(html_dir, target_html_dir)

    meta = {
        "mode": args.mode,
        "pages_branch": args.pages_branch,
        "pages_prefix": args.pages_prefix,
        "run_id": args.run_id,
        "run_attempt": args.run_attempt,
        "commit_sha": args.commit_sha,
        "ref": args.ref,
        "coverage_xml": str(coverage_xml),
        "coverage_html_index": str(html_index),
    }

    (artifact_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    # Provide a stable entry-point index for consumers.
    (artifact_dir / "index.html").write_text(
        (target_html_dir / "index.html").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    print(f"Prepared coverage bundle in {artifact_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
