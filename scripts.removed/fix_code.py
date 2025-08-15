#!/usr/bin/env python3
"""
Automatisches Code-Quality Fix Script

Führt alle verfügbaren Code-Verbesserungen aus:
- Ruff formatting & linting mit auto-fix
- Import organization  
- Code simplification
- Modern Python upgrades
- NoQA annotation für unfixable issues

Usage:
    python scripts/fix_code.py          # Fix all files
    python scripts/fix_code.py --check  # Only check, don't fix
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd: list[str], description: str) -> bool:
    """Run a command and return success status."""
    print(f"🔧 {description}...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            print(f"   ⚠️  Issues found: {result.stdout.strip()}")
            print(f"   ⚠️  Errors: {result.stderr.strip()}")
        else:
            print(f"   ✅ {description} completed")
        return result.returncode == 0
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False


def main():
    """Run all code quality fixes."""
    check_only = "--check" in sys.argv
    
    if check_only:
        print("🔍 CHECKING code quality (no changes will be made)")
    else:
        print("🛠️  FIXING code quality issues automatically")
    
    # Commands to run
    commands = [
        # 1. Format everything
        (["ruff", "format", "." if not check_only else "--check", "."], 
         "Ruff formatting"),
        
        # 2. Fix all auto-fixable issues
        (["ruff", "check", ".", "--fix" if not check_only else "", "--unsafe-fixes", "--show-fixes"], 
         "Auto-fixing lint issues"),
        
        # 3. Import sorting
        (["ruff", "check", ".", "--select", "I", "--fix" if not check_only else ""], 
         "Organizing imports"),
        
        # 4. Python upgrades
        (["ruff", "check", ".", "--select", "UP", "--fix" if not check_only else ""], 
         "Applying Python upgrades"),
        
        # 5. Code simplification  
        (["ruff", "check", ".", "--select", "SIM", "--fix" if not check_only else ""], 
         "Simplifying code"),
        
        # 6. Remove unused imports/variables
        (["ruff", "check", ".", "--select", "F401,F841", "--fix" if not check_only else ""], 
         "Removing unused code"),
        
        # 7. Add noqa for unfixable issues (only if fixing)
        (["ruff", "check", ".", "--add-noqa"] if not check_only else [], 
         "Adding noqa annotations"),
        
        # 8. Final cleanup pass
        (["ruff", "check", ".", "--extend-select", "RUF100", "--fix" if not check_only else ""], 
         "Final cleanup"),
        
        # 9. Final validation
        (["ruff", "check", "."], 
         "Final validation"),
    ]
    
    success_count = 0
    total_count = 0
    
    for cmd, description in commands:
        if not cmd:  # Skip empty commands
            continue
            
        total_count += 1
        cmd_filtered = [arg for arg in cmd if arg]  # Remove empty strings
        
        if run_command(cmd_filtered, description):
            success_count += 1
    
    print(f"\n📊 Results: {success_count}/{total_count} operations successful")
    
    if check_only:
        if success_count == total_count:
            print("✅ Code quality check passed!")
            return 0
        else:
            print("❌ Code quality issues found. Run without --check to fix.")
            return 1
    else:
        print("🎉 Code quality fixes applied!")
        print("\n💡 Next steps:")
        print("   1. Review changes with: git diff")
        print("   2. Test your code still works")
        print("   3. Commit changes: git add . && git commit -m '🤖 Auto-fix code quality'")
        return 0


if __name__ == "__main__":
    # Ensure we're in the right directory
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    
    import os
    os.chdir(repo_root)
    
    exit(main())
