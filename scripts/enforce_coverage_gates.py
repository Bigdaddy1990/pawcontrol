"""Fail CI when coverage gates for PawControl are not met."""

import argparse
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import xml.etree.ElementTree as ET


@dataclass(frozen=True, slots=True)
class ModuleGate:
    """Coverage requirement for a critical module."""

    path: str


@dataclass(frozen=True, slots=True)
class BranchCoverageException:
    """Documented exception for critical module branch coverage."""

    path: str
    minimum_branch_percent: Decimal
    rationale: str


DEFAULT_TOTAL_MINIMUM_PERCENT = Decimal("85")
DEFAULT_CRITICAL_MODULE_MINIMUM_PERCENT = Decimal("90")
CRITICAL_MODULE_GATES: tuple[ModuleGate, ...] = (
    ModuleGate("custom_components/pawcontrol/coordinator.py"),
    ModuleGate("custom_components/pawcontrol/config_flow.py"),
    ModuleGate("custom_components/pawcontrol/services.py"),
    ModuleGate("custom_components/pawcontrol/data_manager.py"),
)
CRITICAL_BRANCH_TARGET_PERCENT = Decimal("100")
DEFAULT_EXCEPTION_FILE = Path("docs/coverage_critical_module_exceptions.json")

ALLOWED_NO_COVER_CATEGORIES: tuple[tuple[str, str], ...] = (
    (
        "Import/Version-Fallbacks",
        "Compatibility guards for optional Home Assistant symbols or runtime imports.",
    ),
    (
        "Defensive Logging",
        "Best-effort logging/cleanup branches that only execute on "
        "hard-to-reproduce runtime failures.",
    ),
    (
        "Type-Checking Branches",
        "TYPE_CHECKING-only blocks that cannot execute at runtime.",
    ),
)


def _parse_percent(raw_value: str) -> Decimal:
    try:
        return Decimal(raw_value)
    except InvalidOperation as exc:  # pragma: no cover - defensive input parsing
        raise SystemExit(f"invalid numeric value: {raw_value!r}") from exc


def _coverage_root(coverage_xml: Path) -> ET.Element:
    if not coverage_xml.is_file():
        raise SystemExit(f"coverage report not found: {coverage_xml}")
    return ET.parse(coverage_xml).getroot()


def _overall_coverage_percent(root: ET.Element) -> Decimal:
    line_rate = root.attrib.get("line-rate")
    if line_rate is None:
        raise SystemExit("coverage.xml is missing required 'line-rate' attribute")
    return (_parse_percent(line_rate) * Decimal("100")).quantize(Decimal("0.01"))


def _module_coverage_percent(root: ET.Element, module_path: str) -> Decimal:
    normalized_target = module_path.removeprefix("custom_components/pawcontrol/")
    for class_node in root.findall(".//class"):
        filename = class_node.attrib.get("filename")
        if filename not in {module_path, normalized_target}:
            continue
        line_rate = class_node.attrib.get("line-rate")
        if line_rate is None:
            raise SystemExit(
                f"coverage.xml class entry for {module_path!r} is missing line-rate"
            )
        return (_parse_percent(line_rate) * Decimal("100")).quantize(Decimal("0.01"))
    raise SystemExit(
        "coverage.xml does not include coverage data for critical module: "
        f"{module_path}"
    )


def _module_branch_percent(root: ET.Element, module_path: str) -> Decimal:
    normalized_target = module_path.removeprefix("custom_components/pawcontrol/")
    for class_node in root.findall(".//class"):
        filename = class_node.attrib.get("filename")
        if filename not in {module_path, normalized_target}:
            continue
        branch_rate = class_node.attrib.get("branch-rate")
        if branch_rate is None:
            raise SystemExit(
                f"coverage.xml class entry for {module_path!r} is missing branch-rate"
            )
        return (_parse_percent(branch_rate) * Decimal("100")).quantize(Decimal("0.01"))
    raise SystemExit(
        "coverage.xml does not include coverage data for critical module: "
        f"{module_path}"
    )


def _load_branch_exceptions(
    exceptions_file: Path,
) -> dict[str, BranchCoverageException]:
    if not exceptions_file.is_file():
        return {}

    raw_payload = json.loads(exceptions_file.read_text(encoding="utf-8"))
    if not isinstance(raw_payload, list):
        raise SystemExit("coverage exception file must contain a JSON list")

    exceptions: dict[str, BranchCoverageException] = {}
    for item in raw_payload:
        if not isinstance(item, dict):
            raise SystemExit("coverage exception entries must be JSON objects")
        path = item.get("path")
        minimum_branch_percent = item.get("minimum_branch_percent")
        rationale = item.get("rationale")
        if (
            not isinstance(path, str)
            or not isinstance(minimum_branch_percent, str)
            or not isinstance(rationale, str)
            or not rationale.strip()
        ):
            raise SystemExit(
                "each coverage exception must define string values for "
                "path, minimum_branch_percent, and rationale"
            )
        exceptions[path] = BranchCoverageException(
            path=path,
            minimum_branch_percent=_parse_percent(minimum_branch_percent),
            rationale=rationale.strip(),
        )
    return exceptions


def _evaluate_gates(
    coverage_xml: Path,
    exceptions_file: Path,
    total_minimum_percent: Decimal,
    critical_module_minimum_percent: Decimal,
) -> tuple[Decimal, list[str], list[str]]:
    root = _coverage_root(coverage_xml)
    branch_exceptions = _load_branch_exceptions(exceptions_file)
    failures: list[str] = []
    notices: list[str] = []

    overall_percent = _overall_coverage_percent(root)
    if overall_percent < total_minimum_percent:
        failures.append(
            "overall coverage gate failed: "
            f"{overall_percent}% < {total_minimum_percent}%"
        )

    for gate in CRITICAL_MODULE_GATES:
        module_line_percent = _module_coverage_percent(root, gate.path)
        if module_line_percent < critical_module_minimum_percent:
            failures.append(
                "critical module line coverage gate failed: "
                f"{gate.path} = {module_line_percent}% < "
                f"{critical_module_minimum_percent}%"
            )

        branch_percent = _module_branch_percent(root, gate.path)
        if branch_percent >= CRITICAL_BRANCH_TARGET_PERCENT:
            continue

        branch_exception = branch_exceptions.get(gate.path)
        if branch_exception is None:
            failures.append(
                "critical module branch coverage gate failed without documented "
                f"exception: {gate.path} = {branch_percent}% < "
                f"{CRITICAL_BRANCH_TARGET_PERCENT}%"
            )
            continue

        if branch_percent < branch_exception.minimum_branch_percent:
            failures.append(
                "critical module branch coverage exception floor failed: "
                f"{gate.path} = {branch_percent}% < "
                f"{branch_exception.minimum_branch_percent}%"
            )
            continue

        notices.append(
            "critical module branch coverage exception applied: "
            f"{gate.path} ({branch_percent}% < "
            f"{CRITICAL_BRANCH_TARGET_PERCENT}%) because "
            f"{branch_exception.rationale}"
        )

    return overall_percent, failures, notices


def main() -> int:  # noqa: D103
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--coverage-xml",
        default="coverage.xml",
        type=Path,
        help="path to the coverage.xml report",
    )
    parser.add_argument(
        "--exceptions-file",
        default=DEFAULT_EXCEPTION_FILE,
        type=Path,
        help=("JSON file that documents critical-module branch coverage exceptions"),
    )
    parser.add_argument(
        "--total-minimum-percent",
        default=DEFAULT_TOTAL_MINIMUM_PERCENT,
        type=Decimal,
        help="minimum overall line coverage percentage",
    )
    parser.add_argument(
        "--critical-module-minimum-percent",
        default=DEFAULT_CRITICAL_MODULE_MINIMUM_PERCENT,
        type=Decimal,
        help="minimum line coverage percentage for each critical module",
    )
    args = parser.parse_args()

    overall_percent, failures, notices = _evaluate_gates(
        args.coverage_xml,
        args.exceptions_file,
        args.total_minimum_percent,
        args.critical_module_minimum_percent,
    )
    print(
        f"Overall coverage: {overall_percent}% (minimum {args.total_minimum_percent}%)"
    )

    for gate in CRITICAL_MODULE_GATES:
        print(
            "Critical module line gate: "
            f"{gate.path} >= {args.critical_module_minimum_percent}%"
        )
        print(
            "Critical module branch gate: "
            f"{gate.path} >= {CRITICAL_BRANCH_TARGET_PERCENT}% "
            "(or documented exception)"
        )

    if args.exceptions_file.is_file():
        print(f"Branch coverage exceptions file: {args.exceptions_file}")
    else:
        print(f"Branch coverage exceptions file not found: {args.exceptions_file}")

    print("Allowed no-cover categories (must include a reason comment):")
    for name, reason in ALLOWED_NO_COVER_CATEGORIES:
        print(f"- {name}: {reason}")

    for notice in notices:
        print(f"NOTICE: {notice}")

    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        return 1

    print("Coverage gates passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
