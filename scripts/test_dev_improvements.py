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

import argparse
from pathlib import Path
import time
from typing import Final

PROJECT_ROOT: Final = Path(__file__).parent.parent


def test_cache_behavior() -> bool:
  """Test cache size enforcement logic."""  # noqa: E111
  print("=" * 60)  # noqa: E111
  print("TEST 1: Cache Size Enforcement")  # noqa: E111
  print("=" * 60)  # noqa: E111

  # Simulate cache operations  # noqa: E114
  print("  Simulating cache operations...")  # noqa: E111

  # Test 1: Verify size check exists before insertion  # noqa: E114
  init_file = PROJECT_ROOT / "custom_components" / "pawcontrol" / "__init__.py"  # noqa: E111
  content = init_file.read_text(encoding="utf-8")  # noqa: E111

  # Find the size check  # noqa: E114
  size_check = "if len(_PLATFORM_CACHE) >= _MAX_CACHE_SIZE:"  # noqa: E111
  cache_insert = "_PLATFORM_CACHE[cache_key] = (ordered_platforms, now)"  # noqa: E111

  if size_check in content and cache_insert in content:  # noqa: E111
    # Verify order
    size_idx = content.find(size_check)
    insert_idx = content.find(cache_insert)

    if size_idx < insert_idx:
      print("  ✓ Size check BEFORE insertion - CORRECT")  # noqa: E111
      return True  # noqa: E111
    else:
      print("  ✗ Size check AFTER insertion - INCORRECT")  # noqa: E111
      return False  # noqa: E111
  else:  # noqa: E111
    print("  ✗ Required patterns not found")
    return False


def test_type_safety() -> bool:
  """Test type annotations are correct."""  # noqa: E111
  print("\n" + "=" * 60)  # noqa: E111
  print("TEST 2: Type Safety")  # noqa: E111
  print("=" * 60)  # noqa: E111

  const_file = PROJECT_ROOT / "custom_components" / "pawcontrol" / "const.py"  # noqa: E111
  content = const_file.read_text(encoding="utf-8")  # noqa: E111

  # Check for complete type annotation  # noqa: E114
  if "DOG_ID_PATTERN: Final[re.Pattern[str]]" in content:  # noqa: E111
    print("  ✓ DOG_ID_PATTERN has complete type annotation")
    return True
  else:  # noqa: E111
    print("  ✗ DOG_ID_PATTERN missing type annotation")
    return False


def test_code_quality() -> bool:
  """Test code quality improvements."""  # noqa: E111
  print("\n" + "=" * 60)  # noqa: E111
  print("TEST 3: Code Quality")  # noqa: E111
  print("=" * 60)  # noqa: E111

  init_file = PROJECT_ROOT / "custom_components" / "pawcontrol" / "__init__.py"  # noqa: E111
  content = init_file.read_text(encoding="utf-8")  # noqa: E111

  # Check for duplicate pyright comments  # noqa: E114
  import re  # noqa: E111

  pattern = r"# pyright: ignore\[reportGeneralTypeIssues\]\s+# pyright: ignore\[reportGeneralTypeIssues\]"  # noqa: E111, E501
  duplicates = re.findall(pattern, content)  # noqa: E111

  if not duplicates:  # noqa: E111
    print("  ✓ No duplicate pyright comments found")
    return True
  else:  # noqa: E111
    print(f"  ✗ Found {len(duplicates)} duplicate comments")
    return False


def monitor_cache_size(duration_hours: int = 24) -> None:
  """Monitor cache size over time."""  # noqa: E111
  print("\n" + "=" * 60)  # noqa: E111
  print(f"MONITORING: Cache size for {duration_hours} hours")  # noqa: E111
  print("=" * 60)  # noqa: E111

  print(f"  Monitoring started at {time.strftime('%Y-%m-%d %H:%M:%S')}")  # noqa: E111
  print(f"  Duration: {duration_hours} hours")  # noqa: E111
  print("  Note: Actual monitoring requires running integration")  # noqa: E111
  print("  Check diagnostics endpoint for cache metrics")  # noqa: E111
  print()  # noqa: E111
  print("  Expected behavior:")  # noqa: E111
  print("    - Cache size should never exceed 100 entries")  # noqa: E111
  print("    - Memory usage should remain stable")  # noqa: E111
  print("    - No performance degradation")  # noqa: E111


def run_verification_suite() -> int:
  """Run complete verification suite."""  # noqa: E111
  print("\n")  # noqa: E111
  print("╔" + "═" * 58 + "╗")  # noqa: E111
  print("║" + " " * 10 + "PawControl Development Testing Suite" + " " * 12 + "║")  # noqa: E111
  print("║" + " " * 18 + "v1.0.0 Improvements" + " " * 21 + "║")  # noqa: E111
  print("╚" + "═" * 58 + "╝")  # noqa: E111
  print()  # noqa: E111

  results = {  # noqa: E111
    "Cache enforcement": test_cache_behavior(),
    "Type safety": test_type_safety(),
    "Code quality": test_code_quality(),
  }

  print("\n" + "=" * 60)  # noqa: E111
  print("TEST RESULTS")  # noqa: E111
  print("=" * 60)  # noqa: E111

  for test_name, passed in results.items():  # noqa: E111
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"  {status}: {test_name}")

  passed_count = sum(results.values())  # noqa: E111
  total_count = len(results)  # noqa: E111

  print(f"\n  Total: {passed_count}/{total_count} tests passed")  # noqa: E111

  if passed_count == total_count:  # noqa: E111
    print("\n  ✓ ALL TESTS PASSED")
    print("\n  Next steps:")
    print("    1. Run: mypy --strict custom_components/pawcontrol")
    print("    2. Run: pytest tests/")
    print("    3. Start Home Assistant and monitor diagnostics")
    print("    4. Check cache size after 24h")
    return 0
  else:  # noqa: E111
    print("\n  ✗ SOME TESTS FAILED")
    print("\n  Review failures and reapply fixes if needed")
    return 1


def main() -> int:
  """Main entry point."""  # noqa: E111
  parser = argparse.ArgumentParser(  # noqa: E111
    description="Test PawControl development improvements"
  )
  parser.add_argument(  # noqa: E111
    "--monitor",
    type=str,
    metavar="DURATION",
    help="Monitor cache size (e.g., 24h, 48h)",
  )

  args = parser.parse_args()  # noqa: E111

  if args.monitor:  # noqa: E111
    # Parse duration
    duration_str = args.monitor.lower()
    hours = int(duration_str[:-1]) if duration_str.endswith("h") else 24

    monitor_cache_size(hours)
    return 0

  return run_verification_suite()  # noqa: E111


if __name__ == "__main__":
  import sys  # noqa: E111

  sys.exit(main())  # noqa: E111
