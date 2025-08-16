#!/usr/bin/env python3
"""
Home Assistant konforme Code-Quality Tools

Wrapper für die offiziellen HA Development Tools:
- pyupgrade (Python 3.12+)
- ruff (linting + auto-fix)
- pre-commit hooks

Basiert auf Home Assistant Core Development Guidelines.

Usage:
    python scripts/ha_fix.py          # Apply all HA auto-fixes
    python scripts/ha_fix.py --check  # Only check, don't fix
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd: list[str], description: str, check_only: bool = False) -> bool:
    """Run a HA development command."""
    print(f"🔧 {description}...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            if result.stdout.strip():
                print(f"   ⚠️  {result.stdout.strip()}")
            if result.stderr.strip():
                print(f"   ❌ {result.stderr.strip()}")
            return False
        else:
            print(f"   ✅ {description} completed")
            return True
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False


def main():
    """Run Home Assistant code quality tools."""
    check_only = "--check" in sys.argv
    
    if check_only:
        print("🔍 CHECKING with Home Assistant tools (no changes)")
    else:
        print("🛠️  APPLYING Home Assistant auto-fixes")
    
    # Home Assistant Standard Tools (in order)
    commands = [
        # 1. pyupgrade (HA uses this for Python upgrades)
        (["/usr/bin/env python3", "-m", "pyupgrade", "--py312-plus"] + 
         [str(f) for f in Path(".").rglob("*.py") if "custom_components" in str(f) or "tests" in str(f)],
         "pyupgrade (Python 3.12+)"),

        # 2. ruff check + auto-fix (HA uses this)
        (["ruff", "check"] + ([] if check_only else ["--fix"]) + ["custom_components", "tests"],
         "ruff linting"),
        
        # 3. ruff format (additional formatting)
        (["ruff", "format"] + (["--check"] if check_only else []) + ["custom_components", "tests"],
         "ruff formatting"),
        
        # 4. pre-commit hooks (if available)
        (["pre-commit", "run", "--all-files"] + ([] if not check_only else []),
         "pre-commit hooks"),
    ]
    
    success_count = 0
    total_count = len(commands)
    
    for cmd, description in commands:
        if run_command(cmd, description, check_only):
            success_count += 1
    
    print(f"\n📊 Results: {success_count}/{total_count} HA tools successful")
    
    if check_only:
        if success_count == total_count:
            print("✅ Home Assistant code quality check passed!")
            return 0
        else:
            print("❌ Code quality issues found. Run without --check to fix.")
            return 1
    else:
        print("🎉 Home Assistant auto-fixes applied!")
        print("\n💡 Next steps:")
        print("   1. Review changes: git diff")
        print("   2. Test: pytest tests/")
        print("   3. Commit: git commit -m '🤖 Apply HA auto-fixes'")
        return 0


if __name__ == "__main__":
    # Ensure we're in the repo root
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    
    import os
    os.chdir(repo_root)
    
    exit(main())
