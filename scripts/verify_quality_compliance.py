#!/usr/bin/env python3
"""Verify PawControl quality compliance according to copilot-instructions.md.

This script checks:
1. JSON serialization in entity extra_state_attributes
2. MyPy strict mode compliance
3. Validation centralization
4. Coordinator-based architecture (no direct client access)
5. Type hint completeness

Quality Scale: Platinum
Python: 3.14+
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import logging
from pathlib import Path
import re
import subprocess
import sys
from typing import Final

_LOGGER = logging.getLogger(__name__)

# Integration root directory
INTEGRATION_ROOT: Final[Path] = (
  Path(__file__).parent.parent / "custom_components" / "pawcontrol"
)

# Entity platform files to check
ENTITY_PLATFORMS: Final[tuple[str, ...]] = (
  "sensor.py",
  "binary_sensor.py",
  "button.py",
  "switch.py",
  "select.py",
  "number.py",
  "text.py",
  "date.py",
  "datetime.py",
  "device_tracker.py",
)


@dataclass
class ComplianceIssue:
  """Represents a quality compliance issue."""

  file: str
  line: int | None
  issue_type: str
  description: str
  severity: str  # ERROR, WARNING, INFO


class QualityVerifier:
  """Verifies code quality compliance."""

  def __init__(self) -> None:
    """Initialize the quality verifier."""
    self.issues: list[ComplianceIssue] = []

  def verify_json_serialization(self) -> None:
    """Verify all entity platforms use JSON serialization for extra_state_attributes."""
    _LOGGER.info("Checking JSON serialization in entity platforms...")

    for platform_file in ENTITY_PLATFORMS:
      file_path = INTEGRATION_ROOT / platform_file
      if not file_path.exists():
        continue

      content = file_path.read_text(encoding="utf-8")

      # Check if normalise_entity_attributes or _normalise_attributes is used
      uses_normalise = (
        "normalise_entity_attributes" in content or "_normalise_attributes" in content
      )

      # Check if there's an extra_state_attributes property
      has_extra_attrs = "@property" in content and "extra_state_attributes" in content

      if has_extra_attrs and not uses_normalise:
        self.issues.append(
          ComplianceIssue(
            file=platform_file,
            line=None,
            issue_type="JSON_SERIALIZATION",
            description="Entity platform has extra_state_attributes but doesn't use normalise_entity_attributes()",
            severity="ERROR",
          )
        )

      # Check for potential non-JSON-serializable returns
      if has_extra_attrs:  # noqa: SIM102
        # Look for direct datetime/timedelta returns without serialization
        if re.search(r"return\s+(?!_normalise|normalise).*datetime|timedelta", content):
          self.issues.append(
            ComplianceIssue(
              file=platform_file,
              line=None,
              issue_type="JSON_SERIALIZATION",
              description="Potential non-serialized datetime/timedelta in extra_state_attributes",
              severity="WARNING",
            )
          )

  def verify_mypy_compliance(self) -> None:
    """Verify MyPy strict mode compliance."""
    _LOGGER.info("Checking MyPy strict mode compliance...")

    try:
      result = subprocess.run(
        ["mypy", "--strict", str(INTEGRATION_ROOT)],
        capture_output=True,
        text=True,
        timeout=60,
      )

      if result.returncode != 0:
        # Parse MyPy output for errors
        for line in result.stdout.splitlines():
          if "error:" in line.lower():
            # Extract file and line number
            match = re.match(r"(.+?):(\d+): error: (.+)", line)
            if match:
              file_path, line_no, error_msg = match.groups()
              self.issues.append(
                ComplianceIssue(
                  file=Path(file_path).name,
                  line=int(line_no),
                  issue_type="MYPY_ERROR",
                  description=error_msg,
                  severity="ERROR",
                )
              )
            else:
              self.issues.append(
                ComplianceIssue(
                  file="unknown",
                  line=None,
                  issue_type="MYPY_ERROR",
                  description=line,
                  severity="ERROR",
                )
              )

    except FileNotFoundError:
      self.issues.append(
        ComplianceIssue(
          file="mypy",
          line=None,
          issue_type="TOOL_MISSING",
          description="MyPy not installed - run: pip install mypy",
          severity="WARNING",
        )
      )
    except subprocess.TimeoutExpired:
      self.issues.append(
        ComplianceIssue(
          file="mypy",
          line=None,
          issue_type="TIMEOUT",
          description="MyPy check timed out",
          severity="WARNING",
        )
      )

  def verify_validation_centralization(self) -> None:
    """Verify validation logic is centralized in validation.py."""
    _LOGGER.info("Checking validation centralization...")

    validation_keywords = [
      "validator",
      "validate_",
      "is_valid_",
      "check_valid",
    ]

    for py_file in INTEGRATION_ROOT.glob("*.py"):
      if py_file.name in (
        "validation.py",
        "flow_validation.py",
        "validation_helpers.py",
      ):
        continue

      content = py_file.read_text(encoding="utf-8")

      # Check for validation functions outside validation modules
      for keyword in validation_keywords:
        if keyword in content:  # noqa: SIM102
          # Check if it's using centralized validation or implementing its own
          if not (
            "from .validation import" in content
            or "from .flow_validation import" in content
          ):
            matches = re.finditer(rf"def {keyword}\w+\(", content)
            for match in matches:
              line_no = content[: match.start()].count("\n") + 1
              self.issues.append(
                ComplianceIssue(
                  file=py_file.name,
                  line=line_no,
                  issue_type="VALIDATION_DECENTRALIZED",
                  description=f"Validation function {match.group()} should be in validation.py",
                  severity="WARNING",
                )
              )

  def verify_coordinator_architecture(self) -> None:
    """Verify entities use coordinator-based architecture (no direct client access)."""
    _LOGGER.info("Checking coordinator-based architecture...")

    # Patterns that indicate direct client access
    bad_patterns = [
      r"\.client\.",
      r"\.api\.",
      r"async def.*\n.*requests\.",
      r"async def.*\n.*aiohttp\.",
    ]

    for platform_file in ENTITY_PLATFORMS:
      file_path = INTEGRATION_ROOT / platform_file
      if not file_path.exists():
        continue

      content = file_path.read_text(encoding="utf-8")

      for pattern in bad_patterns:
        matches = re.finditer(pattern, content)
        for match in matches:
          line_no = content[: match.start()].count("\n") + 1
          # Exclude if it's accessing coordinator
          context = content[max(0, match.start() - 100) : match.end() + 100]
          if "coordinator" not in context.lower():
            self.issues.append(
              ComplianceIssue(
                file=platform_file,
                line=line_no,
                issue_type="DIRECT_CLIENT_ACCESS",
                description=f"Potential direct client/API access detected: {match.group()}",
                severity="ERROR",
              )
            )

  def verify_type_hints(self) -> None:
    """Verify type hint completeness."""
    _LOGGER.info("Checking type hint completeness...")

    for py_file in INTEGRATION_ROOT.glob("*.py"):
      if py_file.name.startswith("__"):
        continue

      try:
        content = py_file.read_text(encoding="utf-8")
        tree = ast.parse(content)

        for node in ast.walk(tree):
          if isinstance(node, ast.FunctionDef):
            # Check for return type annotation
            if node.returns is None and node.name not in ("__init__", "__post_init__"):
              self.issues.append(
                ComplianceIssue(
                  file=py_file.name,
                  line=node.lineno,
                  issue_type="MISSING_RETURN_TYPE",
                  description=f"Function {node.name} missing return type annotation",
                  severity="WARNING",
                )
              )

            # Check for parameter type annotations
            for arg in node.args.args:
              if arg.annotation is None and arg.arg not in ("self", "cls"):
                self.issues.append(
                  ComplianceIssue(
                    file=py_file.name,
                    line=node.lineno,
                    issue_type="MISSING_PARAM_TYPE",
                    description=f"Parameter {arg.arg} in {node.name} missing type annotation",
                    severity="WARNING",
                  )
                )

      except SyntaxError as e:
        self.issues.append(
          ComplianceIssue(
            file=py_file.name,
            line=e.lineno,
            issue_type="SYNTAX_ERROR",
            description=f"Syntax error: {e.msg}",
            severity="ERROR",
          )
        )

  def generate_report(self) -> str:
    """Generate a comprehensive compliance report."""
    report_lines = [
      "=" * 80,
      "PAWCONTROL QUALITY COMPLIANCE REPORT",
      "=" * 80,
      "",
      f"Total Issues Found: {len(self.issues)}",
      "",
    ]

    # Group by severity
    errors = [i for i in self.issues if i.severity == "ERROR"]
    warnings = [i for i in self.issues if i.severity == "WARNING"]
    info = [i for i in self.issues if i.severity == "INFO"]

    report_lines.append(f"❌ ERRORS: {len(errors)}")
    report_lines.append(f"⚠️  WARNINGS: {len(warnings)}")
    report_lines.append(f"ℹ️  INFO: {len(info)}")
    report_lines.append("")

    # Report errors first
    if errors:
      report_lines.append("=" * 80)
      report_lines.append("ERRORS (must be fixed)")
      report_lines.append("=" * 80)
      for issue in errors:
        location = f"{issue.file}:{issue.line}" if issue.line else issue.file
        report_lines.append(f"\n[{issue.issue_type}] {location}")
        report_lines.append(f"  → {issue.description}")

    # Then warnings
    if warnings:
      report_lines.append("")
      report_lines.append("=" * 80)
      report_lines.append("WARNINGS (should be addressed)")
      report_lines.append("=" * 80)
      for issue in warnings:
        location = f"{issue.file}:{issue.line}" if issue.line else issue.file
        report_lines.append(f"\n[{issue.issue_type}] {location}")
        report_lines.append(f"  → {issue.description}")

    # Finally info
    if info:
      report_lines.append("")
      report_lines.append("=" * 80)
      report_lines.append("INFO (optional improvements)")
      report_lines.append("=" * 80)
      for issue in info:
        location = f"{issue.file}:{issue.line}" if issue.line else issue.file
        report_lines.append(f"\n[{issue.issue_type}] {location}")
        report_lines.append(f"  → {issue.description}")

    report_lines.append("")
    report_lines.append("=" * 80)
    if len(errors) == 0:
      report_lines.append("✅ COMPLIANCE STATUS: PASS")
    else:
      report_lines.append("❌ COMPLIANCE STATUS: FAIL")
    report_lines.append("=" * 80)

    return "\n".join(report_lines)


def main() -> int:
  """Run quality compliance verification."""
  logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
  )

  verifier = QualityVerifier()

  # Run all checks
  verifier.verify_json_serialization()
  verifier.verify_mypy_compliance()
  verifier.verify_validation_centralization()
  verifier.verify_coordinator_architecture()
  verifier.verify_type_hints()

  # Generate and print report
  report = verifier.generate_report()
  print(report)

  # Save report to file
  report_file = Path(__file__).parent.parent / "docs" / "QUALITY_COMPLIANCE_REPORT.md"
  report_file.write_text(report, encoding="utf-8")
  print(f"\n📄 Report saved to: {report_file}")

  # Return exit code
  return 1 if any(i.severity == "ERROR" for i in verifier.issues) else 0


if __name__ == "__main__":
  sys.exit(main())
