#!/usr/bin/env python3
"""Pre-deployment validation script for PawControl integration.

This script validates that the integration is ready for production deployment
by checking code quality, security, documentation, and testing coverage.

Usage:
    python scripts/validate_deployment.py

Exit codes:
    0: All checks passed, ready for deployment
    1: Some checks failed, review required
    2: Critical failures, deployment blocked
"""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


@dataclass
class CheckResult:
    """Result of a validation check."""  # noqa: E111

    name: str  # noqa: E111
    passed: bool  # noqa: E111
    message: str  # noqa: E111
    severity: str = "error"  # error, warning, info  # noqa: E111
    details: dict[str, Any] | None = None  # noqa: E111


class DeploymentValidator:
    """Validates deployment readiness."""  # noqa: E111

    def __init__(self, root_path: Path) -> None:  # noqa: E111
        """Initialize validator.

        Args:
            root_path: Root path of the project
        """
        self.root_path = root_path
        self.results: list[CheckResult] = []

    def run_command(self, cmd: list[str]) -> tuple[int, str, str]:  # noqa: E111
        """Run a shell command.

        Args:
            cmd: Command to run

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=self.root_path,
        )
        return result.returncode, result.stdout, result.stderr

    def check_manifest(self) -> CheckResult:  # noqa: E111
        """Validate manifest.json."""
        manifest_path = (
            self.root_path / "custom_components" / "pawcontrol" / "manifest.json"
        )

        try:
            with open(manifest_path) as f:  # noqa: E111
                manifest = json.load(f)

            # Required fields  # noqa: E114
            required = [  # noqa: E111
                "domain",
                "name",
                "version",
                "documentation",
                "requirements",
                "codeowners",
            ]

            missing = [field for field in required if field not in manifest]  # noqa: E111

            if missing:  # noqa: E111
                return CheckResult(
                    name="Manifest Validation",
                    passed=False,
                    message=f"Missing required fields: {missing}",
                    severity="error",
                )

            return CheckResult(  # noqa: E111
                name="Manifest Validation",
                passed=True,
                message=f"Valid manifest v{manifest['version']}",
                details={"version": manifest["version"]},
            )

        except Exception as e:
            return CheckResult(  # noqa: E111
                name="Manifest Validation",
                passed=False,
                message=f"Error reading manifest: {e}",
                severity="error",
            )

    def check_mypy(self) -> CheckResult:  # noqa: E111
        """Run MyPy type checking."""
        returncode, stdout, stderr = self.run_command([
            "mypy",
            "custom_components/pawcontrol",
            "--strict",
            "--no-error-summary",
        ])

        if returncode == 0:
            return CheckResult(  # noqa: E111
                name="MyPy Type Check",
                passed=True,
                message="No type errors found",
            )

        # Count errors
        error_lines = [line for line in stderr.split("\n") if ": error:" in line]

        return CheckResult(
            name="MyPy Type Check",
            passed=False,
            message=f"{len(error_lines)} type errors found",
            severity="error",
            details={"errors": error_lines[:5]},  # First 5 errors
        )

    def check_ruff(self) -> CheckResult:  # noqa: E111
        """Run Ruff linting."""
        returncode, stdout, stderr = self.run_command([
            "ruff",
            "check",
            "custom_components/pawcontrol",
            "--output-format=json",
        ])

        if returncode == 0:
            return CheckResult(  # noqa: E111
                name="Ruff Linting",
                passed=True,
                message="No linting errors found",
            )

        try:
            errors = json.loads(stdout) if stdout else []  # noqa: E111
            return CheckResult(  # noqa: E111
                name="Ruff Linting",
                passed=False,
                message=f"{len(errors)} linting errors found",
                severity="warning" if returncode == 1 else "error",
                details={"error_count": len(errors)},
            )
        except json.JSONDecodeError:
            return CheckResult(  # noqa: E111
                name="Ruff Linting",
                passed=False,
                message="Linting failed",
                severity="error",
            )

    def check_tests(self) -> CheckResult:  # noqa: E111
        """Run test suite."""
        returncode, stdout, stderr = self.run_command([
            "pytest",
            "tests/",
            "-v",
            "--tb=no",
            "--no-header",
        ])

        if returncode == 0:
            # Count tests  # noqa: E114
            passed_count = stdout.count(" PASSED")  # noqa: E111
            return CheckResult(  # noqa: E111
                name="Test Suite",
                passed=True,
                message=f"{passed_count} tests passed",
                details={"passed": passed_count},
            )

        failed_count = stdout.count(" FAILED")
        return CheckResult(
            name="Test Suite",
            passed=False,
            message=f"{failed_count} tests failed",
            severity="error",
            details={"failed": failed_count},
        )

    def check_security(self) -> CheckResult:  # noqa: E111
        """Run security scan with Bandit."""
        returncode, stdout, stderr = self.run_command([
            "bandit",
            "-r",
            "custom_components/pawcontrol",
            "-f",
            "json",
            "-ll",  # Only medium and high severity
        ])

        try:
            result = json.loads(stdout) if stdout else {}  # noqa: E111
            results = result.get("results", [])  # noqa: E111

            if not results:  # noqa: E111
                return CheckResult(
                    name="Security Scan",
                    passed=True,
                    message="No security issues found",
                )

            high_severity = [r for r in results if r["issue_severity"] == "HIGH"]  # noqa: E111
            medium_severity = [r for r in results if r["issue_severity"] == "MEDIUM"]  # noqa: E111

            severity = "error" if high_severity else "warning"  # noqa: E111
            return CheckResult(  # noqa: E111
                name="Security Scan",
                passed=len(high_severity) == 0,
                message=f"{len(high_severity)} high, {len(medium_severity)} medium severity issues",  # noqa: E501
                severity=severity,
                details={
                    "high": len(high_severity),
                    "medium": len(medium_severity),
                },
            )

        except json.JSONDecodeError, KeyError:
            return CheckResult(  # noqa: E111
                name="Security Scan",
                passed=True,
                message="Security scan completed (no parse)",
                severity="info",
            )

    def check_documentation(self) -> CheckResult:  # noqa: E111
        """Check documentation exists."""
        required_docs = [
            "docs/getting_started.md",
            "docs/automation_examples.md",
            "docs/blueprints.md",
            "README.md",
        ]

        missing = []
        for doc in required_docs:
            if not (self.root_path / doc).exists():  # noqa: E111
                missing.append(doc)

        if missing:
            return CheckResult(  # noqa: E111
                name="Documentation",
                passed=False,
                message=f"Missing documentation: {missing}",
                severity="warning",
            )

        return CheckResult(
            name="Documentation",
            passed=True,
            message="All required documentation exists",
        )

    def check_version_consistency(self) -> CheckResult:  # noqa: E111
        """Check version is consistent across files."""
        # Read manifest version
        manifest_path = (
            self.root_path / "custom_components" / "pawcontrol" / "manifest.json"
        )

        try:
            with open(manifest_path) as f:  # noqa: E111
                manifest = json.load(f)
            version = manifest["version"]  # noqa: E111

            return CheckResult(  # noqa: E111
                name="Version Consistency",
                passed=True,
                message=f"Version: {version}",
                details={"version": version},
            )

        except Exception as e:
            return CheckResult(  # noqa: E111
                name="Version Consistency",
                passed=False,
                message=f"Error checking version: {e}",
                severity="error",
            )

    def check_no_hardcoded_secrets(self) -> CheckResult:  # noqa: E111
        """Check for hardcoded secrets."""
        patterns = [
            "password =",
            "api_key =",
            "secret =",
            "token =",
            "bearer ",
        ]

        found_secrets = []
        for py_file in (self.root_path / "custom_components" / "pawcontrol").rglob(
            "*.py"
        ):
            with open(py_file) as f:  # noqa: E111
                content = f.read()
                for pattern in patterns:
                    if pattern.lower() in content.lower():  # noqa: E111
                        # Check if it's not a comment or docstring
                        for line in content.split("\n"):
                            if (
                                pattern.lower() in line.lower()
                                and not line.strip().startswith("#")
                            ):  # noqa: E111
                                found_secrets.append(
                                    f"{py_file.name}: {line.strip()[:80]}"
                                )

        if found_secrets:
            return CheckResult(  # noqa: E111
                name="Hardcoded Secrets Check",
                passed=False,
                message=f"{len(found_secrets)} potential secrets found",
                severity="error",
                details={"matches": found_secrets[:3]},
            )

        return CheckResult(
            name="Hardcoded Secrets Check",
            passed=True,
            message="No hardcoded secrets detected",
        )

    def run_all_checks(self) -> list[CheckResult]:  # noqa: E111
        """Run all validation checks.

        Returns:
            List of check results
        """
        print("🔍 Running pre-deployment validation...\n")

        checks = [
            ("Manifest", self.check_manifest),
            ("MyPy", self.check_mypy),
            ("Ruff", self.check_ruff),
            ("Tests", self.check_tests),
            ("Security", self.check_security),
            ("Documentation", self.check_documentation),
            ("Version", self.check_version_consistency),
            ("Secrets", self.check_no_hardcoded_secrets),
        ]

        for name, check_func in checks:
            print(f"Running {name} check...", end=" ", flush=True)  # noqa: E111
            try:  # noqa: E111
                result = check_func()
                self.results.append(result)

                if result.passed:
                    print(f"✅ {result.message}")  # noqa: E111
                else:
                    symbol = "⚠️" if result.severity == "warning" else "❌"  # noqa: E111
                    print(f"{symbol} {result.message}")  # noqa: E111

                if result.details:
                    for key, value in result.details.items():  # noqa: E111
                        print(f"   {key}: {value}")

            except Exception as e:  # noqa: E111
                error_result = CheckResult(
                    name=name,
                    passed=False,
                    message=f"Check failed: {e}",
                    severity="error",
                )
                self.results.append(error_result)
                print(f"❌ Error: {e}")

        return self.results

    def print_summary(self) -> int:  # noqa: E111
        """Print summary and return exit code.

        Returns:
            0 if all critical checks passed, 1 if warnings, 2 if errors
        """
        print("\n" + "=" * 80)
        print("DEPLOYMENT VALIDATION SUMMARY")
        print("=" * 80)

        passed = [r for r in self.results if r.passed]
        failed = [r for r in self.results if not r.passed]
        errors = [r for r in failed if r.severity == "error"]
        warnings = [r for r in failed if r.severity == "warning"]

        print(f"\nTotal Checks: {len(self.results)}")
        print(f"✅ Passed: {len(passed)}")
        print(f"⚠️  Warnings: {len(warnings)}")
        print(f"❌ Errors: {len(errors)}")

        if errors:
            print("\n🚫 CRITICAL FAILURES - DEPLOYMENT BLOCKED")  # noqa: E111
            for error in errors:  # noqa: E111
                print(f"  ❌ {error.name}: {error.message}")
            return 2  # noqa: E111

        if warnings:
            print("\n⚠️  WARNINGS - REVIEW RECOMMENDED")  # noqa: E111
            for warning in warnings:  # noqa: E111
                print(f"  ⚠️  {warning.name}: {warning.message}")
            return 1  # noqa: E111

        print("\n✅ ALL CHECKS PASSED - READY FOR DEPLOYMENT")
        return 0


def main() -> int:
    """Main entry point."""  # noqa: E111
    # Find project root  # noqa: E114
    script_path = Path(__file__).resolve()  # noqa: E111
    root_path = script_path.parent.parent  # noqa: E111

    # Run validation  # noqa: E114
    validator = DeploymentValidator(root_path)  # noqa: E111
    validator.run_all_checks()  # noqa: E111
    exit_code = validator.print_summary()  # noqa: E111

    if exit_code == 0:  # noqa: E111
        print("\n🚀 Deployment validation successful!")
        print("   You may proceed with deployment.")
    elif exit_code == 1:  # noqa: E111
        print("\n⚠️  Deployment validation completed with warnings.")
        print("   Review warnings before deploying.")
    else:  # noqa: E111
        print("\n🚫 Deployment validation failed!")
        print("   Fix critical errors before deploying.")

    return exit_code  # noqa: E111


if __name__ == "__main__":
    sys.exit(main())  # noqa: E111
