"""Tests for scripts.enforce_coverage_gates."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from scripts import enforce_coverage_gates


def _write_coverage_xml(
    tmp_path: Path,
    *,
    line_rate: str,
    class_rates: dict[str, str],
) -> Path:
    class_xml = "\n".join(
        (
            f'<class filename="{path}" line-rate="{rate}" branch-rate="0">'
            "<lines /></class>"
        )
        for path, rate in class_rates.items()
    )
    payload = (
        '<?xml version="1.0" ?>\n'
        f'<coverage line-rate="{line_rate}" branch-rate="0" version="7">\n'
        '<packages><package name="pawcontrol" line-rate="0" branch-rate="0">\n'
        f"<classes>{class_xml}</classes>\n"
        "</package></packages></coverage>\n"
    )
    report = tmp_path / "coverage.xml"
    report.write_text(payload, encoding="utf-8")
    return report


def test_evaluate_gates_passes_when_all_thresholds_met(tmp_path: Path) -> None:
    report = _write_coverage_xml(
        tmp_path,
        line_rate="0.89",
        class_rates={
            "custom_components/pawcontrol/coordinator.py": "0.91",
            "custom_components/pawcontrol/config_flow.py": "0.95",
            "custom_components/pawcontrol/services.py": "0.83",
            "custom_components/pawcontrol/data_manager.py": "0.79",
        },
    )

    overall, failures = enforce_coverage_gates._evaluate_gates(report)

    assert overall == Decimal("89.00")
    assert failures == []


def test_evaluate_gates_reports_total_and_module_failures(tmp_path: Path) -> None:
    report = _write_coverage_xml(
        tmp_path,
        line_rate="0.70",
        class_rates={
            "custom_components/pawcontrol/coordinator.py": "0.79",
            "custom_components/pawcontrol/config_flow.py": "0.82",
            "custom_components/pawcontrol/services.py": "0.74",
            "custom_components/pawcontrol/data_manager.py": "0.70",
        },
    )

    _, failures = enforce_coverage_gates._evaluate_gates(report)

    assert any("overall coverage gate failed" in failure for failure in failures)
    assert any("coordinator.py" in failure for failure in failures)
    assert any("services.py" in failure for failure in failures)
    assert any("data_manager.py" in failure for failure in failures)


def test_evaluate_gates_fails_when_critical_module_is_missing(tmp_path: Path) -> None:
    report = _write_coverage_xml(
        tmp_path,
        line_rate="0.90",
        class_rates={
            "custom_components/pawcontrol/coordinator.py": "0.95",
            "custom_components/pawcontrol/config_flow.py": "0.91",
            "custom_components/pawcontrol/services.py": "0.88",
        },
    )

    with pytest.raises(SystemExit, match="critical module"):
        enforce_coverage_gates._evaluate_gates(report)
