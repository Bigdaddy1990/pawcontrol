#!/usr/bin/env python3
"""Analyze test files and identify import changes needed after refactoring.

This script scans all test files for imports from custom_components.pawcontrol
that reference internal functions moved to setup modules.
"""


import re
from pathlib import Path
from typing import NamedTuple


class ImportIssue(NamedTuple):
    """Represents an import that needs to be fixed."""

    file_path: Path
    line_number: int
    old_import: str
    new_import: str
    severity: str  # 'critical', 'warning', 'info'


# Mapping of moved functions to their new locations
MOVED_FUNCTIONS = {
    "_async_run_manager_method": "setup.cleanup",
    "_async_cleanup_runtime_data": "setup.cleanup",
    "_async_cancel_background_monitor": "setup.cleanup",
    "_remove_listeners": "setup.cleanup",
    "_async_shutdown_core_managers": "setup.cleanup",
    "_clear_coordinator_references": "setup.cleanup",

    "_async_validate_dogs_config": "setup.validation",
    "_validate_profile": "setup.validation",
    "_extract_enabled_modules": "setup.validation",

    "_async_forward_platforms": "setup.platform_setup",
    "_async_setup_helpers": "setup.platform_setup",
    "_async_setup_scripts": "setup.platform_setup",

    "_async_initialize_coordinator": "setup.manager_init",
    "_async_create_core_managers": "setup.manager_init",
    "_async_create_optional_managers": "setup.manager_init",
    "_async_initialize_all_managers": "setup.manager_init",
    "_async_initialize_geofencing_manager": "setup.manager_init",
    "_async_initialize_manager_with_timeout": "setup.manager_init",
    "_attach_managers_to_coordinator": "setup.manager_init",
    "_create_runtime_data": "setup.manager_init",
    "_register_runtime_monitors": "setup.manager_init",
}


def analyze_test_file(test_file: Path) -> list[ImportIssue]:
    """Analyze a single test file for import issues.

    Args:
        test_file: Path to test file

    Returns:
        List of import issues found
    """
    issues: list[ImportIssue] = []

    try:
        content = test_file.read_text(encoding="utf-8")
        lines = content.splitlines()

        for line_num, line in enumerate(lines, start=1):
            # Check for direct imports from __init__
            if "from custom_components.pawcontrol import" in line:
                for func_name, new_module in MOVED_FUNCTIONS.items():
                    if func_name in line:
                        old_import = line.strip()
                        new_import = old_import.replace(
                            "from custom_components.pawcontrol import",
                            f"from custom_components.pawcontrol.{new_module} import",
                        )
                        issues.append(
                            ImportIssue(
                                file_path=test_file,
                                line_number=line_num,
                                old_import=old_import,
                                new_import=new_import,
                                severity="critical",
                            ),
                        )

            # Check for patch decorators
            if "@patch(" in line or "@mock.patch(" in line:
                for func_name, new_module in MOVED_FUNCTIONS.items():
                    pattern = f"custom_components\\.pawcontrol\\.{func_name}"
                    if re.search(pattern, line):
                        old_import = line.strip()
                        new_import = old_import.replace(
                            f"custom_components.pawcontrol.{func_name}",
                            f"custom_components.pawcontrol.{new_module}.{func_name}",
                        )
                        issues.append(
                            ImportIssue(
                                file_path=test_file,
                                line_number=line_num,
                                old_import=old_import,
                                new_import=new_import,
                                severity="critical",
                            ),
                        )

    except Exception as err:
        print(f"Error analyzing {test_file}: {err}")

    return issues


def main() -> None:
    """Main entry point."""
    project_root = Path(__file__).parent.parent
    tests_dir = project_root / "tests"

    if not tests_dir.exists():
        print(f"Tests directory not found: {tests_dir}")
        return

    print("🔍 Analyzing test files for import issues...")
    print("=" * 80)

    all_issues: list[ImportIssue] = []

    # Scan all test files
    for test_file in tests_dir.rglob("test_*.py"):
        issues = analyze_test_file(test_file)
        all_issues.extend(issues)

    # Group issues by severity
    critical_issues = [i for i in all_issues if i.severity == "critical"]
    warning_issues = [i for i in all_issues if i.severity == "warning"]
    info_issues = [i for i in all_issues if i.severity == "info"]

    # Report results
    print("\n📊 ANALYSIS RESULTS:")
    print(f"   Critical issues: {len(critical_issues)}")
    print(f"   Warnings:        {len(warning_issues)}")
    print(f"   Info:            {len(info_issues)}")
    print(f"   Total:           {len(all_issues)}")

    if critical_issues:
        print("\n🔴 CRITICAL ISSUES (Must fix):")
        print("-" * 80)
        for issue in critical_issues:
            print(f"\nFile: {issue.file_path.relative_to(project_root)}")
            print(f"Line {issue.line_number}:")
            print(f"  OLD: {issue.old_import}")
            print(f"  NEW: {issue.new_import}")

    if warning_issues:
        print("\n🟡 WARNINGS (Should fix):")
        print("-" * 80)
        for issue in warning_issues:
            print(f"\nFile: {issue.file_path.relative_to(project_root)}")
            print(f"Line {issue.line_number}: {issue.old_import}")

    # Generate fix script
    if all_issues:
        print("\n📝 Generating automated fix script...")
        fix_script_path = project_root / "scripts" / "fix_test_imports.py"
        generate_fix_script(fix_script_path, all_issues, project_root)
        print(f"   Fix script created: {fix_script_path}")
        print("\n   Run: python scripts/fix_test_imports.py")
    else:
        print("\n✅ No import issues found! Tests should work as-is.")


def generate_fix_script(
    output_path: Path,
    issues: list[ImportIssue],
    project_root: Path,
) -> None:
    """Generate a script to automatically fix import issues.

    Args:
        output_path: Where to save the fix script
        issues: List of issues to fix
        project_root: Project root directory
    """
    script_content = '''#!/usr/bin/env python3
"""Automatically fix test imports after refactoring.

This script was auto-generated by analyze_test_imports.py
"""

from __future__ import annotations

from pathlib import Path


def fix_imports() -> None:
    """Apply all import fixes."""
    project_root = Path(__file__).parent.parent

    fixes = [
'''

    # Add fixes
    for issue in issues:
        rel_path = issue.file_path.relative_to(project_root)
        script_content += f"""        (
            project_root / "{rel_path}",
            {issue.line_number},
            {repr(issue.old_import)},
            {repr(issue.new_import)},
        ),
"""

    script_content += """    ]

    for file_path, line_num, old_text, new_text in fixes:
        if not file_path.exists():
            print(f"⚠️  File not found: {file_path}")
            continue

        content = file_path.read_text(encoding="utf-8")
        lines = content.splitlines(keepends=True)

        if line_num - 1 < len(lines):
            if old_text.strip() in lines[line_num - 1]:
                lines[line_num - 1] = lines[line_num - 1].replace(old_text.strip(), new_text.strip())
                file_path.write_text("".join(lines), encoding="utf-8")
                print(f"✅ Fixed {file_path.name}:{line_num}")
            else:
                print(f"⚠️  Line {line_num} in {file_path.name} doesn't match expected content")
        else:
            print(f"⚠️  Line {line_num} out of range in {file_path.name}")


if __name__ == "__main__":
    print("🔧 Fixing test imports...")
    fix_imports()
    print("✅ Import fixes complete!")
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(script_content, encoding="utf-8")
    output_path.chmod(0o755)


if __name__ == "__main__":
    main()
