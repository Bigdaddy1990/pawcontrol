"""Publish coverage HTML to GitHub Pages artifact.

This is used by the reusable-python-tests workflow when `publish-pages` is enabled.
It collects the HTML coverage report and places it into a public directory
that can be uploaded via `actions/upload-pages-artifact`.

The workflow passes:
  - --coverage-html-index: path to the HTML coverage index (e.g. htmlcov/index.html)
  - --public-dir: output directory for pages artifact (e.g. public)

The script is intentionally lightweight and has no external dependencies.
"""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


def _copytree(src: Path, dst: Path) -> None:
    """Copy a directory tree (dst is overwritten if it exists)."""
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare GitHub Pages artifact for coverage")
    parser.add_argument("--coverage-html-index", required=True, help="Path to coverage HTML index.html")
    parser.add_argument("--public-dir", required=True, help="Output directory for Pages artifact")
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

    html_root = index_path.parent

    public_dir.mkdir(parents=True, exist_ok=True)

    # Copy coverage HTML to public/coverage
    coverage_dst = public_dir / "coverage"
    _copytree(html_root, coverage_dst)

    # Ensure GitHub Pages does not try to treat this as a Jekyll site.
    (public_dir / ".nojekyll").write_text("", encoding="utf-8")

    # Create a tiny landing page.
    rel_index = Path("coverage") / index_path.name
    landing = """<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Paw Control – Coverage</title>
  </head>
  <body>
    <h1>Paw Control – Coverage report</h1>
    <p><a href=\"{href}\">Open coverage report</a></p>
  </body>
</html>
""".format(href=str(rel_index).replace(os.sep, "/"))

    (public_dir / "index.html").write_text(landing, encoding="utf-8")

    print(f"Prepared Pages artifact in: {public_dir}")
    print(f"Coverage report copied to: {coverage_dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
