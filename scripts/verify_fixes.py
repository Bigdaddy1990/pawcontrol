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

from pathlib import Path
import re
import sys
from typing import Final

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

INIT_FILE: Final = PROJECT_ROOT / "custom_components" / "pawcontrol" / "__init__.py"
CONST_FILE: Final = PROJECT_ROOT / "custom_components" / "pawcontrol" / "const.py"
PYRIGHT_IGNORE_COMMENT: Final = "# pyright: ignore[reportGeneralTypeIssues]"


def check_fix_1_duplicate_comment() -> bool:
  """Verify Fix #1: Duplicate pyright comment is removed."""  # noqa: E111
  print("Checking Fix #1: Duplicate pyright comment...")  # noqa: E111

  with open(INIT_FILE, encoding="utf-8") as f:  # noqa: E111
    content = f.read()

  # Check for duplicate comment pattern  # noqa: E114
  pattern = r"# pyright: ignore\[reportGeneralTypeIssues\]\s+# pyright: ignore\[reportGeneralTypeIssues\]"  # noqa: E111, E501
  duplicates = re.findall(pattern, content)  # noqa: E111

  if duplicates:  # noqa: E111
    print(f"  ❌ FAIL: Found {len(duplicates)} duplicate pyright comments")
    return False

  # Check that single comment exists on async_setup_entry  # noqa: E114
  if "async def async_setup_entry" in content:  # noqa: E111
    # Find the line
    lines = content.split("\n")
    for i, line in enumerate(lines):
      if "async def async_setup_entry" in line and PYRIGHT_IGNORE_COMMENT in line:  # noqa: E111
        # Check it's only once
        count = line.count(PYRIGHT_IGNORE_COMMENT)
        if count == 1:
          print(f"  ✓ PASS: Single pyright comment found (line {i + 1})")  # noqa: E111
          return True  # noqa: E111
        else:
          print(f"  ❌ FAIL: Found {count} pyright comments on line {i + 1}")  # noqa: E111
          return False  # noqa: E111

  print("  ❌ FAIL: async_setup_entry function not found")  # noqa: E111
  return False  # noqa: E111


def check_fix_2_type_annotation() -> bool:
  """Verify Fix #2: DOG_ID_PATTERN has proper type annotation."""  # noqa: E111
  print("Checking Fix #2: Type annotation on DOG_ID_PATTERN...")  # noqa: E111

  with open(CONST_FILE, encoding="utf-8") as f:  # noqa: E111
    content = f.read()

  # Check for correct annotation  # noqa: E114
  correct_pattern = r"DOG_ID_PATTERN:\s*Final\[re\.Pattern\[str\]\]\s*="  # noqa: E111

  if re.search(correct_pattern, content):  # noqa: E111
    print("  ✓ PASS: DOG_ID_PATTERN has correct type annotation")
    return True

  # Check for old incorrect pattern  # noqa: E114
  incorrect_pattern = r"DOG_ID_PATTERN:\s*Final\s*="  # noqa: E111
  if re.search(incorrect_pattern, content):  # noqa: E111
    print("  ❌ FAIL: DOG_ID_PATTERN still has incomplete type annotation")
    return False

  print("  ❌ FAIL: DOG_ID_PATTERN not found")  # noqa: E111
  return False  # noqa: E111


def check_fix_3_cache_leak() -> bool:
  """Verify Fix #3: Cache memory leak is fixed."""  # noqa: E111
  print("Checking Fix #3: Cache memory leak fix...")  # noqa: E111

  with open(INIT_FILE, encoding="utf-8") as f:  # noqa: E111
    content = f.read()

  # Find get_platforms_for_profile_and_modules function  # noqa: E114
  func_pattern = r"def get_platforms_for_profile_and_modules\("  # noqa: E111
  if not re.search(func_pattern, content):  # noqa: E111
    print("  ❌ FAIL: get_platforms_for_profile_and_modules function not found")
    return False

  # Check for size enforcement BEFORE insertion  # noqa: E114
  size_check_pattern = r"if len\(_PLATFORM_CACHE\) >= _MAX_CACHE_SIZE:"  # noqa: E111
  cache_insert_pattern = r"_PLATFORM_CACHE\[cache_key\] = \(ordered_platforms, now\)"  # noqa: E111

  # Find both patterns  # noqa: E114
  size_check_match = re.search(size_check_pattern, content)  # noqa: E111
  cache_insert_match = re.search(cache_insert_pattern, content)  # noqa: E111

  if not size_check_match:  # noqa: E111
    print("  ❌ FAIL: Size enforcement check not found")
    return False

  if not cache_insert_match:  # noqa: E111
    print("  ❌ FAIL: Cache insertion not found")
    return False

  # Verify size check comes BEFORE insertion  # noqa: E114
  if size_check_match.start() < cache_insert_match.start():  # noqa: E111
    print("  ✓ PASS: Size enforcement check found before cache insertion")

    # Check for the comment
    if "prevent unbounded growth" in content:
      print("  ✓ PASS: Documentation comment found")  # noqa: E111
      return True  # noqa: E111
    else:
      print("  ⚠ WARNING: Documentation comment missing but logic is correct")  # noqa: E111
      return True  # noqa: E111
  else:  # noqa: E111
    print("  ❌ FAIL: Size check comes after cache insertion")
    return False


def check_cache_constants() -> bool:
  """Verify cache constants are correctly defined."""  # noqa: E111
  print("Checking cache constants...")  # noqa: E111

  with open(INIT_FILE, encoding="utf-8") as f:  # noqa: E111
    content = f.read()

  checks = {  # noqa: E111
    "_MAX_CACHE_SIZE": r"_MAX_CACHE_SIZE:\s*Final\[int\]\s*=\s*100",
    "_CACHE_TTL_SECONDS": r"_CACHE_TTL_SECONDS:\s*Final\[int\]\s*=\s*3600",
  }

  all_passed = True  # noqa: E111
  for const_name, pattern in checks.items():  # noqa: E111
    if re.search(pattern, content):
      print(f"  ✓ PASS: {const_name} correctly defined")  # noqa: E111
    else:
      print(f"  ❌ FAIL: {const_name} not found or incorrect")  # noqa: E111
      all_passed = False  # noqa: E111

  return all_passed  # noqa: E111


def verify_imports() -> bool:
  """Verify required imports are present."""  # noqa: E111
  print("Checking imports...")  # noqa: E111

  with open(CONST_FILE, encoding="utf-8") as f:  # noqa: E111
    const_content = f.read()

  # Check for re import in const.py  # noqa: E114
  if "import re" in const_content:  # noqa: E111
    print("  ✓ PASS: 're' module imported in const.py")
  else:  # noqa: E111
    print("  ❌ FAIL: 're' module not imported in const.py")
    return False

  with open(INIT_FILE, encoding="utf-8") as f:  # noqa: E111
    init_content = f.read()

  # Check for time import  # noqa: E114
  if "import time" in init_content:  # noqa: E111
    print("  ✓ PASS: 'time' module imported in __init__.py")
  else:  # noqa: E111
    print("  ❌ FAIL: 'time' module not imported in __init__.py")
    return False

  return True  # noqa: E111


def main() -> int:
  """Run all verification checks."""  # noqa: E111
  print("=" * 60)  # noqa: E111
  print("PawControl v1.0.1 Bug Fix Verification")  # noqa: E111
  print("=" * 60)  # noqa: E111
  print()  # noqa: E111

  results = {  # noqa: E111
    "Fix #1 (Duplicate pyright comment)": check_fix_1_duplicate_comment(),
    "Fix #2 (Type annotation)": check_fix_2_type_annotation(),
    "Fix #3 (Cache memory leak)": check_fix_3_cache_leak(),
    "Cache constants": check_cache_constants(),
    "Imports": verify_imports(),
  }

  print()  # noqa: E111
  print("=" * 60)  # noqa: E111
  print("VERIFICATION RESULTS")  # noqa: E111
  print("=" * 60)  # noqa: E111

  for check_name, passed in results.items():  # noqa: E111
    status = "✓ PASS" if passed else "❌ FAIL"
    print(f"{status}: {check_name}")

  print()  # noqa: E111

  passed_count = sum(results.values())  # noqa: E111
  total_count = len(results)  # noqa: E111

  if passed_count == total_count:  # noqa: E111
    print(f"✓ ALL CHECKS PASSED ({passed_count}/{total_count})")
    print()
    print("Next steps:")
    print("  1. Run: mypy --strict custom_components/pawcontrol")
    print("  2. Run: pytest -q --cov custom_components/pawcontrol")
    print("  3. Update CHANGELOG.md with v1.0.1 entry")
    print("  4. Commit changes and tag release")
    return 0
  else:  # noqa: E111
    print(f"❌ SOME CHECKS FAILED ({passed_count}/{total_count} passed)")
    print()
    print("Please review the failures above and apply fixes manually.")
    return 1


if __name__ == "__main__":
  sys.exit(main())  # noqa: E111
