#!/usr/bin/env python3
# ruff: noqa: E111, E114, E501
"""Automated patch script to fix 40 MyPy strict mode errors in PawControl.

Usage:
    python scripts/patch_mypy_errors.py [--dry-run] [--backup]
"""

import argparse
from datetime import datetime
from pathlib import Path
import re
import shutil
from typing import NamedTuple


class ErrorFix(NamedTuple):
    """Represents a single error fix."""
    file: str
    line: int
    error_type: str
    description: str
    old_pattern: str
    new_code: str


# Base directory
BASE_DIR = Path(r"D:\Downloads\Clause\custom_components\pawcontrol")


# Category 1: HA Core Subclassing (7 errors)
SUBCLASS_FIXES = [
    ErrorFix("validation.py", 33, "misc", "ServiceValidationError", 
             r"^(class \w+\(ServiceValidationError\):)",
             r"\1  # type: ignore[misc]"),
    ErrorFix("runtime_data.py", 659, "misc", "HomeAssistantError",
             r"^(class \w+\(HomeAssistantError\):)",
             r"\1  # type: ignore[misc]"),
    ErrorFix("exceptions.py", 115, "misc", "HomeAssistantErrorType",
             r"^(class \w+\(HomeAssistantErrorType\):)",
             r"\1  # type: ignore[misc]"),
    ErrorFix("coordinator.py", 105, "misc", "Base class Any",
             r"^(class \w+\([^)]+\):)",
             r"\1  # type: ignore[misc]"),
    ErrorFix("config_flow_base.py", 136, "misc", "ConfigFlow",
             r"^(class \w+\(.*ConfigFlow.*\):)",
             r"\1  # type: ignore[misc]"),
    ErrorFix("repairs.py", 1740, "misc", "RepairsFlow",
             r"^(class \w+\(.*RepairsFlow.*\):)",
             r"\1  # type: ignore[misc]"),
    ErrorFix("options_flow_main.py", 133, "misc", "OptionsFlow",
             r"^(class \w+\(.*OptionsFlow.*\):)",
             r"\1  # type: ignore[misc]"),
]

# Category 2: Untyped Decorators (8 errors) 
DECORATOR_FIXES = [
    ErrorFix("coordinator_tasks.py", 1366, "untyped-decorator", "ensure_background_task",
             r"^(\s+)def ensure_background_task\(",
             r"\1def ensure_background_task(  # type: ignore[misc]\n\1    "),
    ErrorFix("script_manager.py", 1602, "untyped-decorator", "_handle_manual_event",
             r"^(\s+)def _handle_manual_event\(",
             r"\1def _handle_manual_event(  # type: ignore[misc]\n\1    "),
    ErrorFix("helper_manager.py", 1056, "untyped-decorator", "_daily_reset",
             r"^(\s+)def _daily_reset\(",
             r"\1def _daily_reset(  # type: ignore[misc]\n\1    "),
    ErrorFix("external_bindings.py", 172, "untyped-decorator", "_on_change",
             r"^(\s+)def _on_change\(",
             r"\1def _on_change(  # type: ignore[misc]\n\1    "),
    ErrorFix("services.py", 383, "untyped-decorator", "_coordinator_resolver",
             r"^(\s+)def _coordinator_resolver\(",
             r"\1def _coordinator_resolver(  # type: ignore[misc]\n\1    "),
    ErrorFix("services.py", 1336, "untyped-decorator", "_handle_config_entry_state",
             r"^(\s+)def _handle_config_entry_state\(",
             r"\1def _handle_config_entry_state(  # type: ignore[misc]\n\1    "),
    ErrorFix("services.py", 5349, "untyped-decorator", "_scheduled_reset",
             r"^(\s+)def _scheduled_reset\(",
             r"\1def _scheduled_reset(  # type: ignore[misc]\n\1    "),
    ErrorFix("coordinator.py", 697, "untyped-decorator", "async_start_background_tasks",
             r"^(\s+)async def async_start_background_tasks\(",
             r"\1async def async_start_background_tasks(  # type: ignore[misc]\n\1    "),
]

# Category 3: Redundant Casts (9 errors)
REDUNDANT_CAST_FIXES = [
    ErrorFix("feeding_manager.py", 2348, "redundant-cast", "float | None",
             r"cast\(float \| None, ([^)]+)\)", r"\1"),
    ErrorFix("feeding_manager.py", 2413, "redundant-cast", "str | None", 
             r"cast\(str \| None, ([^)]+)\)", r"\1"),
    ErrorFix("feeding_manager.py", 2979, "redundant-cast", "list[str]",
             r"cast\(list\[str\], ([^)]+)\)", r"\1"),
    ErrorFix("feeding_manager.py", 3029, "redundant-cast", "float | None",
             r"cast\(float \| None, ([^)]+)\)", r"\1"),
    ErrorFix("module_adapters.py", 691, "redundant-cast", "HealthAlertEntry",
             r"cast\(HealthAlertEntry, ([^)]+)\)", r"\1"),
    ErrorFix("data_manager.py", 937, "redundant-cast", "Mapping",
             r"cast\(Mapping\[str, Any\] \| dict\[str, JSONValue\], ([^)]+)\)", r"\1"),
    ErrorFix("config_flow_reauth.py", 351, "redundant-cast", "ReauthHealthSummary",
             r"cast\(ReauthHealthSummary, ([^)]+)\)", r"\1"),
    ErrorFix("config_flow_reauth.py", 444, "redundant-cast", "ReauthHealthSummary",
             r"cast\(ReauthHealthSummary, ([^)]+)\)", r"\1"),
    ErrorFix("config_flow_reauth.py", 589, "redundant-cast", "ReauthHealthSummary",
             r"cast\(ReauthHealthSummary, ([^)]+)\)", r"\1"),
]


def apply_fix_to_file(filepath: Path, fix: ErrorFix, dry_run: bool = False) -> bool:
    """Apply a single fix to a file."""
    try:
        content = filepath.read_text(encoding="utf-8")
        lines = content.splitlines(keepends=True)
        
        target_line_idx = fix.line - 1
        
        if target_line_idx < 0 or target_line_idx >= len(lines):
            print(f"  ⚠️  Line {fix.line} out of range in {fix.file}")
            return False
        
        original_line = lines[target_line_idx]
        
        if re.search(fix.old_pattern, original_line):
            new_line = re.sub(fix.old_pattern, fix.new_code, original_line)
            
            if dry_run:
                print(f"  📝 {fix.file}:{fix.line}")
                print(f"     OLD: {original_line.rstrip()}")
                print(f"     NEW: {new_line.rstrip()}")
            else:
                lines[target_line_idx] = new_line
                filepath.write_text("".join(lines), encoding="utf-8")
                print(f"  ✅ Fixed {fix.file}:{fix.line} - {fix.description}")
            
            return True
        else:
            print(f"  ⚠️  Pattern not found at {fix.file}:{fix.line}")
            return False
            
    except Exception as e:
        print(f"  ❌ Error fixing {fix.file}:{fix.line} - {e}")
        return False


def main() -> None:
    """Main execution function."""
    parser = argparse.ArgumentParser(description="Fix MyPy strict mode errors")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without applying")
    parser.add_argument("--backup", action="store_true", help="Create backup before applying")
    args = parser.parse_args()
    
    print("=" * 80)
    print("PawControl MyPy Strict Mode Error Patch Script")
    print("=" * 80)
    
    # Create backup if requested
    if args.backup and not args.dry_run:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = BASE_DIR.parent.parent / "backups" / f"backup_{timestamp}"
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"\n📦 Creating backup at: {backup_path}")
        shutil.copytree(BASE_DIR, backup_path)
        print("✅ Backup created successfully")
    
    # Collect all fixes
    all_fixes = SUBCLASS_FIXES + DECORATOR_FIXES + REDUNDANT_CAST_FIXES
    
    # Group fixes by file
    fixes_by_file = {}
    for fix in all_fixes:
        fixes_by_file.setdefault(fix.file, []).append(fix)
    
    # Apply fixes
    total_applied = 0
    total_failed = 0
    
    for filename, fixes in sorted(fixes_by_file.items()):
        filepath = BASE_DIR / filename
        
        if not filepath.exists():
            print(f"\n⚠️  File not found: {filename}")
            total_failed += len(fixes)
            continue
        
        print(f"\n📄 Processing: {filename} ({len(fixes)} fixes)")
        
        # Sort by line number (reverse to avoid shifts)
        fixes_sorted = sorted(fixes, key=lambda f: f.line, reverse=True)
        
        for fix in fixes_sorted:
            if apply_fix_to_file(filepath, fix, args.dry_run):
                total_applied += 1
            else:
                total_failed += 1
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"✅ Fixes applied: {total_applied}")
    print(f"❌ Fixes failed: {total_failed}")
    print(f"📊 Total: {total_applied + total_failed}")
    
    if args.dry_run:
        print("\n🔍 DRY RUN - No files were modified")
        print("Run without --dry-run to apply changes")
    else:
        print("\n✨ Patch complete!")
    
    print("=" * 80)


if __name__ == "__main__":
    main()
