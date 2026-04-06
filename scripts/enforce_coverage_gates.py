"""Fail CI when coverage gates for PawControl are not met."""

import argparse
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
import xml.etree.ElementTree as ET


@dataclass(frozen=True, slots=True)
class ModuleGate:
    """Coverage requirement for a critical module."""

    path: str
    minimum_percent: Decimal


TOTAL_MINIMUM_PERCENT = Decimal("75")
CRITICAL_MODULE_GATES: tuple[ModuleGate, ...] = (
    ModuleGate("custom_components/pawcontrol/coordinator.py", Decimal("80")),
    ModuleGate("custom_components/pawcontrol/config_flow.py", Decimal("80")),
    ModuleGate("custom_components/pawcontrol/services.py", Decimal("75")),
    ModuleGate("custom_components/pawcontrol/data_manager.py", Decimal("75")),
)

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
    for class_node in root.findall(".//class"):
        if class_node.attrib.get("filename") != module_path:
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


def _evaluate_gates(coverage_xml: Path) -> tuple[Decimal, list[str]]:
    root = _coverage_root(coverage_xml)
    failures: list[str] = []

    overall_percent = _overall_coverage_percent(root)
    if overall_percent < TOTAL_MINIMUM_PERCENT:
        failures.append(
            "overall coverage gate failed: "
            f"{overall_percent}% < {TOTAL_MINIMUM_PERCENT}%"
        )

    for gate in CRITICAL_MODULE_GATES:
        module_percent = _module_coverage_percent(root, gate.path)
        if module_percent < gate.minimum_percent:
            failures.append(
                "critical module coverage gate failed: "
                f"{gate.path} = {module_percent}% < {gate.minimum_percent}%"
            )

    return overall_percent, failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--coverage-xml",
        default="coverage.xml",
        type=Path,
        help="path to the coverage.xml report",
    )
    args = parser.parse_args()

    overall_percent, failures = _evaluate_gates(args.coverage_xml)
    print(f"Overall coverage: {overall_percent}% (minimum {TOTAL_MINIMUM_PERCENT}%)")

    for gate in CRITICAL_MODULE_GATES:
        print(f"Critical module gate: {gate.path} >= {gate.minimum_percent}%")

    print("Allowed no-cover categories (must include a reason comment):")
    for name, reason in ALLOWED_NO_COVER_CATEGORIES:
        print(f"- {name}: {reason}")

    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        return 1

    print("Coverage gates passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
