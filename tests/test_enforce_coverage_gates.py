"""Tests for scripts.enforce_coverage_gates."""

from decimal import Decimal
from pathlib import Path

import pytest
from scripts import enforce_coverage_gates


def _write_coverage_xml(
    tmp_path: Path,
    *,
    line_rate: str,
    class_rates: dict[str, tuple[str, str]],
) -> Path:
    class_xml = "\n".join(
        (
            f'<class filename="{path}" line-rate="{line}" branch-rate="{branch}">'
            "<lines /></class>"
        )
        for path, (line, branch) in class_rates.items()
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
            "custom_components/pawcontrol/coordinator.py": ("0.91", "1"),
            "custom_components/pawcontrol/config_flow.py": ("0.95", "1"),
            "custom_components/pawcontrol/services.py": ("0.83", "1"),
            "custom_components/pawcontrol/data_manager.py": ("0.79", "1"),
        },
    )

    overall, failures, notices = enforce_coverage_gates._evaluate_gates(
        report, tmp_path / "missing-exceptions.json"
    )

    assert overall == Decimal("89.00")
    assert failures == []
    assert notices == []


def test_evaluate_gates_reports_total_and_module_failures(tmp_path: Path) -> None:
    report = _write_coverage_xml(
        tmp_path,
        line_rate="0.70",
        class_rates={
            "custom_components/pawcontrol/coordinator.py": ("0.79", "0.79"),
            "custom_components/pawcontrol/config_flow.py": ("0.82", "0.82"),
            "custom_components/pawcontrol/services.py": ("0.74", "0.74"),
            "custom_components/pawcontrol/data_manager.py": ("0.70", "0.70"),
        },
    )

    _, failures, _ = enforce_coverage_gates._evaluate_gates(
        report, tmp_path / "missing-exceptions.json"
    )

    assert any("overall coverage gate failed" in failure for failure in failures)
    assert any("without documented exception" in failure for failure in failures)


def test_evaluate_gates_fails_when_critical_module_is_missing(tmp_path: Path) -> None:
    report = _write_coverage_xml(
        tmp_path,
        line_rate="0.90",
        class_rates={
            "custom_components/pawcontrol/coordinator.py": ("0.95", "1"),
            "custom_components/pawcontrol/config_flow.py": ("0.91", "1"),
            "custom_components/pawcontrol/services.py": ("0.88", "1"),
        },
    )

    with pytest.raises(SystemExit, match="critical module"):
        enforce_coverage_gates._evaluate_gates(
            report, tmp_path / "missing-exceptions.json"
        )


def test_evaluate_gates_uses_documented_branch_exception(tmp_path: Path) -> None:
    report = _write_coverage_xml(
        tmp_path,
        line_rate="0.90",
        class_rates={
            "custom_components/pawcontrol/coordinator.py": ("0.95", "0.85"),
            "custom_components/pawcontrol/config_flow.py": ("0.91", "1"),
            "custom_components/pawcontrol/services.py": ("0.88", "1"),
            "custom_components/pawcontrol/data_manager.py": ("0.89", "1"),
        },
    )
    exceptions_file = tmp_path / "exceptions.json"
    exceptions_file.write_text(
        '[{"path":"custom_components/pawcontrol/coordinator.py",'
        '"minimum_branch_percent":"80","rationale":"deterministic limits"}]',
        encoding="utf-8",
    )

    _, failures, notices = enforce_coverage_gates._evaluate_gates(
        report, exceptions_file
    )

    assert failures == []
    assert any("exception applied" in notice for notice in notices)
