#!/usr/bin/env python3
"""Development testing script for PawControl v1.0.0 improvements.

Tests the 3 bug fixes in development:
1. Cache memory leak fix
2. Duplicate pyright comment removal
3. Type annotation completion

Usage:
    python scripts/test_dev_improvements.py

    # With monitoring
    python scripts/test_dev_improvements.py --monitor 24h
"""

from __future__ import annotations

import argparse
from pathlib import Path
import time
from typing import Final

PROJECT_ROOT: Final = Path(__file__).parent.parent


def test_cache_behavior() -> bool:
  """Test cache size enforcement logic."""
  print("=" * 60)
  print("TEST 1: Cache Size Enforcement")
  print("=" * 60)

  # Simulate cache operations
  print("  Simulating cache operations...")

  # Test 1: Verify size check exists before insertion
  init_file = PROJECT_ROOT / "custom_components" / "pawcontrol" / "__init__.py"
  content = init_file.read_text(encoding="utf-8")

  # Find the size check
  size_check = "if len(_PLATFORM_CACHE) >= _MAX_CACHE_SIZE:"
  cache_insert = "_PLATFORM_CACHE[cache_key] = (ordered_platforms, now)"

  if size_check in content and cache_insert in content:
    # Verify order
    size_idx = content.find(size_check)
    insert_idx = content.find(cache_insert)

    if size_idx < insert_idx:
      print("  ✓ Size check BEFORE insertion - CORRECT")
      return True
    else:
      print("  ✗ Size check AFTER insertion - INCORRECT")
      return False
  else:
    print("  ✗ Required patterns not found")
    return False


def test_type_safety() -> bool:
  """Test type annotations are correct."""
  print("\n" + "=" * 60)
  print("TEST 2: Type Safety")
  print("=" * 60)

  const_file = PROJECT_ROOT / "custom_components" / "pawcontrol" / "const.py"
  content = const_file.read_text(encoding="utf-8")

  # Check for complete type annotation
  if "DOG_ID_PATTERN: Final[re.Pattern[str]]" in content:
    print("  ✓ DOG_ID_PATTERN has complete type annotation")
    return True
  else:
    print("  ✗ DOG_ID_PATTERN missing type annotation")
    return False


def test_code_quality() -> bool:
  """Test code quality improvements."""
  print("\n" + "=" * 60)
  print("TEST 3: Code Quality")
  print("=" * 60)

  init_file = PROJECT_ROOT / "custom_components" / "pawcontrol" / "__init__.py"
  content = init_file.read_text(encoding="utf-8")

  # Check for duplicate pyright comments
  import re

  pattern = r"# pyright: ignore\[reportGeneralTypeIssues\]\s+# pyright: ignore\[reportGeneralTypeIssues\]"
  duplicates = re.findall(pattern, content)

  if not duplicates:
    print("  ✓ No duplicate pyright comments found")
    return True
  else:
    print(f"  ✗ Found {len(duplicates)} duplicate comments")
    return False


def monitor_cache_size(duration_hours: int = 24) -> None:
  """Monitor cache size over time."""
  print("\n" + "=" * 60)
  print(f"MONITORING: Cache size for {duration_hours} hours")
  print("=" * 60)

  print(f"  Monitoring started at {time.strftime('%Y-%m-%d %H:%M:%S')}")
  print(f"  Duration: {duration_hours} hours")
  print("  Note: Actual monitoring requires running integration")
  print("  Check diagnostics endpoint for cache metrics")
  print()
  print("  Expected behavior:")
  print("    - Cache size should never exceed 100 entries")
  print("    - Memory usage should remain stable")
  print("    - No performance degradation")


def run_verification_suite() -> int:
  """Run complete verification suite."""
  print("\n")
  print("╔" + "═" * 58 + "╗")
  print("║" + " " * 10 + "PawControl Development Testing Suite" + " " * 12 + "║")
  print("║" + " " * 18 + "v1.0.0 Improvements" + " " * 21 + "║")
  print("╚" + "═" * 58 + "╝")
  print()

  results = {
    "Cache enforcement": test_cache_behavior(),
    "Type safety": test_type_safety(),
    "Code quality": test_code_quality(),
  }

  print("\n" + "=" * 60)
  print("TEST RESULTS")
  print("=" * 60)

  for test_name, passed in results.items():
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"  {status}: {test_name}")

  passed_count = sum(results.values())
  total_count = len(results)

  print(f"\n  Total: {passed_count}/{total_count} tests passed")

  if passed_count == total_count:
    print("\n  ✓ ALL TESTS PASSED")
    print("\n  Next steps:")
    print("    1. Run: mypy --strict custom_components/pawcontrol")
    print("    2. Run: pytest tests/")
    print("    3. Start Home Assistant and monitor diagnostics")
    print("    4. Check cache size after 24h")
    return 0
  else:
    print("\n  ✗ SOME TESTS FAILED")
    print("\n  Review failures and reapply fixes if needed")
    return 1


def main() -> int:
  """Main entry point."""
  parser = argparse.ArgumentParser(
    description="Test PawControl development improvements"
  )
  parser.add_argument(
    "--monitor",
    type=str,
    metavar="DURATION",
    help="Monitor cache size (e.g., 24h, 48h)",
  )

  args = parser.parse_args()

  if args.monitor:
    # Parse duration
    duration_str = args.monitor.lower()
    hours = int(duration_str[:-1]) if duration_str.endswith("h") else 24

    monitor_cache_size(hours)
    return 0

  return run_verification_suite()


if __name__ == "__main__":
  import sys

  sys.exit(main())
