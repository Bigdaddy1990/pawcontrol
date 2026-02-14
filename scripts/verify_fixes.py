#!/usr/bin/env python3
"""Verification script for PawControl v1.0.1 bug fixes.

This script verifies all fixes from the 2026-02-14 bug fix release:
- Fix #1: Duplicate pyright comment removed
- Fix #2: Type annotation on DOG_ID_PATTERN
- Fix #3: Cache memory leak fixed

Run this after applying fixes to ensure everything is correct.

Usage:
    python scripts/verify_fixes.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Final

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

INIT_FILE: Final = PROJECT_ROOT / "custom_components" / "pawcontrol" / "__init__.py"
CONST_FILE: Final = PROJECT_ROOT / "custom_components" / "pawcontrol" / "const.py"

def check_fix_1_duplicate_comment() -> bool:
    """Verify Fix #1: Duplicate pyright comment is removed."""
    print("Checking Fix #1: Duplicate pyright comment...")
    
    with open(INIT_FILE, encoding="utf-8") as f:
        content = f.read()
    
    # Check for duplicate comment pattern
    pattern = r"# pyright: ignore\[reportGeneralTypeIssues\]\s+# pyright: ignore\[reportGeneralTypeIssues\]"
    duplicates = re.findall(pattern, content)
    
    if duplicates:
        print(f"  ❌ FAIL: Found {len(duplicates)} duplicate pyright comments")
        return False
    
    # Check that single comment exists on async_setup_entry
    if "async def async_setup_entry" in content:
        # Find the line
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if "async def async_setup_entry" in line:
                if "# pyright: ignore[reportGeneralTypeIssues]" in line:
                    # Check it's only once
                    count = line.count("# pyright: ignore[reportGeneralTypeIssues]")
                    if count == 1:
                        print(f"  ✓ PASS: Single pyright comment found (line {i+1})")
                        return True
                    else:
                        print(f"  ❌ FAIL: Found {count} pyright comments on line {i+1}")
                        return False
    
    print("  ❌ FAIL: async_setup_entry function not found")
    return False


def check_fix_2_type_annotation() -> bool:
    """Verify Fix #2: DOG_ID_PATTERN has proper type annotation."""
    print("Checking Fix #2: Type annotation on DOG_ID_PATTERN...")
    
    with open(CONST_FILE, encoding="utf-8") as f:
        content = f.read()
    
    # Check for correct annotation
    correct_pattern = r'DOG_ID_PATTERN:\s*Final\[re\.Pattern\[str\]\]\s*='
    
    if re.search(correct_pattern, content):
        print("  ✓ PASS: DOG_ID_PATTERN has correct type annotation")
        return True
    
    # Check for old incorrect pattern
    incorrect_pattern = r'DOG_ID_PATTERN:\s*Final\s*='
    if re.search(incorrect_pattern, content):
        print("  ❌ FAIL: DOG_ID_PATTERN still has incomplete type annotation")
        return False
    
    print("  ❌ FAIL: DOG_ID_PATTERN not found")
    return False


def check_fix_3_cache_leak() -> bool:
    """Verify Fix #3: Cache memory leak is fixed."""
    print("Checking Fix #3: Cache memory leak fix...")
    
    with open(INIT_FILE, encoding="utf-8") as f:
        content = f.read()
    
    # Find get_platforms_for_profile_and_modules function
    func_pattern = r'def get_platforms_for_profile_and_modules\('
    if not re.search(func_pattern, content):
        print("  ❌ FAIL: get_platforms_for_profile_and_modules function not found")
        return False
    
    # Check for size enforcement BEFORE insertion
    size_check_pattern = r'if len\(_PLATFORM_CACHE\) >= _MAX_CACHE_SIZE:'
    cache_insert_pattern = r'_PLATFORM_CACHE\[cache_key\] = \(ordered_platforms, now\)'
    
    # Find both patterns
    size_check_match = re.search(size_check_pattern, content)
    cache_insert_match = re.search(cache_insert_pattern, content)
    
    if not size_check_match:
        print("  ❌ FAIL: Size enforcement check not found")
        return False
    
    if not cache_insert_match:
        print("  ❌ FAIL: Cache insertion not found")
        return False
    
    # Verify size check comes BEFORE insertion
    if size_check_match.start() < cache_insert_match.start():
        print("  ✓ PASS: Size enforcement check found before cache insertion")
        
        # Check for the comment
        if "prevent unbounded growth" in content:
            print("  ✓ PASS: Documentation comment found")
            return True
        else:
            print("  ⚠ WARNING: Documentation comment missing but logic is correct")
            return True
    else:
        print("  ❌ FAIL: Size check comes after cache insertion")
        return False


def check_cache_constants() -> bool:
    """Verify cache constants are correctly defined."""
    print("Checking cache constants...")
    
    with open(INIT_FILE, encoding="utf-8") as f:
        content = f.read()
    
    checks = {
        "_MAX_CACHE_SIZE": r'_MAX_CACHE_SIZE:\s*Final\[int\]\s*=\s*100',
        "_CACHE_TTL_SECONDS": r'_CACHE_TTL_SECONDS:\s*Final\[int\]\s*=\s*3600',
    }
    
    all_passed = True
    for const_name, pattern in checks.items():
        if re.search(pattern, content):
            print(f"  ✓ PASS: {const_name} correctly defined")
        else:
            print(f"  ❌ FAIL: {const_name} not found or incorrect")
            all_passed = False
    
    return all_passed


def verify_imports() -> bool:
    """Verify required imports are present."""
    print("Checking imports...")
    
    with open(CONST_FILE, encoding="utf-8") as f:
        const_content = f.read()
    
    # Check for re import in const.py
    if "import re" in const_content:
        print("  ✓ PASS: 're' module imported in const.py")
    else:
        print("  ❌ FAIL: 're' module not imported in const.py")
        return False
    
    with open(INIT_FILE, encoding="utf-8") as f:
        init_content = f.read()
    
    # Check for time import
    if "import time" in init_content:
        print("  ✓ PASS: 'time' module imported in __init__.py")
    else:
        print("  ❌ FAIL: 'time' module not imported in __init__.py")
        return False
    
    return True


def main() -> int:
    """Run all verification checks."""
    print("=" * 60)
    print("PawControl v1.0.1 Bug Fix Verification")
    print("=" * 60)
    print()
    
    results = {
        "Fix #1 (Duplicate pyright comment)": check_fix_1_duplicate_comment(),
        "Fix #2 (Type annotation)": check_fix_2_type_annotation(),
        "Fix #3 (Cache memory leak)": check_fix_3_cache_leak(),
        "Cache constants": check_cache_constants(),
        "Imports": verify_imports(),
    }
    
    print()
    print("=" * 60)
    print("VERIFICATION RESULTS")
    print("=" * 60)
    
    for check_name, passed in results.items():
        status = "✓ PASS" if passed else "❌ FAIL"
        print(f"{status}: {check_name}")
    
    print()
    
    passed_count = sum(results.values())
    total_count = len(results)
    
    if passed_count == total_count:
        print(f"✓ ALL CHECKS PASSED ({passed_count}/{total_count})")
        print()
        print("Next steps:")
        print("  1. Run: mypy --strict custom_components/pawcontrol")
        print("  2. Run: pytest -q --cov custom_components/pawcontrol")
        print("  3. Update CHANGELOG.md with v1.0.1 entry")
        print("  4. Commit changes and tag release")
        return 0
    else:
        print(f"❌ SOME CHECKS FAILED ({passed_count}/{total_count} passed)")
        print()
        print("Please review the failures above and apply fixes manually.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
