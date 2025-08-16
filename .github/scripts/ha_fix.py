from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]  # repo/
COMPONENT_DIR = REPO_ROOT / "custom_components"  # scope fixes to code

RUFF_PKGS = ["ruff>=0.5.0"]

def run(cmd: list[str]) -> int:
    print("+", " ".join(cmd), flush=True)
    return subprocess.call(cmd)

def ensure_tools() -> None:
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    run([sys.executable, "-m", "pip", "install", *RUFF_PKGS])

def ruff_check(check_only: bool) -> int:
    paths = [str(COMPONENT_DIR), "tests"]
    rc1 = run(["ruff", "check", *paths] + ([] if not check_only else [] if False else (["--fix"] if not check_only else [])))
    if check_only:
        # In check mode, don't modify files; just report issues
        rc1 = run(["ruff", "check", *paths])
    rc2 = run(["ruff", "format", *paths] + (["--check"] if check_only else []))
    return 0 if rc1 == 0 and rc2 == 0 else 1

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="do not modify files")
    args = ap.parse_args()

    if not COMPONENT_DIR.exists():
        print(f"ERR: {COMPONENT_DIR} not found", file=sys.stderr)
        return 2

    ensure_tools()
    return ruff_check(check_only=args.check)

if __name__ == "__main__":
    sys.exit(main())
