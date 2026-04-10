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
            "custom_components/pawcontrol/services.py": ("0.93", "1"),
            "custom_components/pawcontrol/data_manager.py": ("0.92", "1"),
        },
    )

    overall, failures, notices = enforce_coverage_gates._evaluate_gates(
        report,
        tmp_path / "missing-exceptions.json",
        enforce_coverage_gates.DEFAULT_TOTAL_MINIMUM_PERCENT,
        enforce_coverage_gates.DEFAULT_CRITICAL_MODULE_MINIMUM_PERCENT,
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
        report,
        tmp_path / "missing-exceptions.json",
        enforce_coverage_gates.DEFAULT_TOTAL_MINIMUM_PERCENT,
        enforce_coverage_gates.DEFAULT_CRITICAL_MODULE_MINIMUM_PERCENT,
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
            report,
            tmp_path / "missing-exceptions.json",
            enforce_coverage_gates.DEFAULT_TOTAL_MINIMUM_PERCENT,
            enforce_coverage_gates.DEFAULT_CRITICAL_MODULE_MINIMUM_PERCENT,
        )


def test_evaluate_gates_uses_documented_branch_exception(tmp_path: Path) -> None:
    report = _write_coverage_xml(
        tmp_path,
        line_rate="0.90",
        class_rates={
            "custom_components/pawcontrol/coordinator.py": ("0.95", "0.85"),
            "custom_components/pawcontrol/config_flow.py": ("0.91", "1"),
            "custom_components/pawcontrol/services.py": ("0.91", "1"),
            "custom_components/pawcontrol/data_manager.py": ("0.92", "1"),
        },
    )
    exceptions_file = tmp_path / "exceptions.json"
    exceptions_file.write_text(
        '[{"path":"custom_components/pawcontrol/coordinator.py",'
        '"minimum_branch_percent":"80","rationale":"deterministic limits"}]',
        encoding="utf-8",
    )

    _, failures, notices = enforce_coverage_gates._evaluate_gates(
        report,
        exceptions_file,
        enforce_coverage_gates.DEFAULT_TOTAL_MINIMUM_PERCENT,
        enforce_coverage_gates.DEFAULT_CRITICAL_MODULE_MINIMUM_PERCENT,
    )

    assert failures == []
    assert any("exception applied" in notice for notice in notices)


def test_evaluate_gates_reports_critical_module_line_floor_failures(
    tmp_path: Path,
) -> None:
    report = _write_coverage_xml(
        tmp_path,
        line_rate="0.95",
        class_rates={
            "custom_components/pawcontrol/coordinator.py": ("0.89", "1"),
            "custom_components/pawcontrol/config_flow.py": ("0.95", "1"),
            "custom_components/pawcontrol/services.py": ("0.95", "1"),
            "custom_components/pawcontrol/data_manager.py": ("0.95", "1"),
        },
    )

    _, failures, _ = enforce_coverage_gates._evaluate_gates(
        report,
        tmp_path / "missing-exceptions.json",
        enforce_coverage_gates.DEFAULT_TOTAL_MINIMUM_PERCENT,
        enforce_coverage_gates.DEFAULT_CRITICAL_MODULE_MINIMUM_PERCENT,
    )

    assert any(
        "critical module line coverage gate failed" in failure for failure in failures
    )


def test_module_coverage_percent_accepts_normalized_filename(tmp_path: Path) -> None:
    report = _write_coverage_xml(
        tmp_path,
        line_rate="0.90",
        class_rates={
            "coordinator.py": ("0.95", "1"),
        },
    )

    root = enforce_coverage_gates._coverage_root(report)
    percent = enforce_coverage_gates._module_coverage_percent(
        root,
        "custom_components/pawcontrol/coordinator.py",
    )

    assert percent == Decimal("95.00")


def test_overall_coverage_percent_requires_line_rate_attribute(tmp_path: Path) -> None:
    report = tmp_path / "coverage.xml"
    report.write_text(
        '<?xml version="1.0" ?>\n'
        '<coverage branch-rate="0" version="7">\n'
        '<packages><package name="pawcontrol"><classes /></package></packages>\n'
        "</coverage>\n",
        encoding="utf-8",
    )

    root = enforce_coverage_gates._coverage_root(report)
    with pytest.raises(SystemExit, match="line-rate"):
        enforce_coverage_gates._overall_coverage_percent(root)


def test_module_branch_percent_requires_branch_rate_attribute(tmp_path: Path) -> None:
    report = tmp_path / "coverage.xml"
    report.write_text(
        '<?xml version="1.0" ?>\n'
        '<coverage line-rate="0.9" branch-rate="0" version="7">\n'
        '<packages><package name="pawcontrol" line-rate="0" branch-rate="0">\n'
        '<classes><class filename="custom_components/pawcontrol/coordinator.py" '
        'line-rate="0.95"><lines /></class></classes>\n'
        "</package></packages></coverage>\n",
        encoding="utf-8",
    )

    root = enforce_coverage_gates._coverage_root(report)
    with pytest.raises(SystemExit, match="missing branch-rate"):
        enforce_coverage_gates._module_branch_percent(
            root,
            "custom_components/pawcontrol/coordinator.py",
        )


def test_load_branch_exceptions_rejects_invalid_payload_types(tmp_path: Path) -> None:
    exceptions_file = tmp_path / "exceptions.json"
    exceptions_file.write_text('{"path":"bad"}', encoding="utf-8")

    with pytest.raises(SystemExit, match="JSON list"):
        enforce_coverage_gates._load_branch_exceptions(exceptions_file)


def test_load_branch_exceptions_rejects_missing_rationale(tmp_path: Path) -> None:
    exceptions_file = tmp_path / "exceptions.json"
    exceptions_file.write_text(
        '[{"path":"custom_components/pawcontrol/coordinator.py",'
        '"minimum_branch_percent":"90","rationale":"   "}]',
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="string values"):
        enforce_coverage_gates._load_branch_exceptions(exceptions_file)


def test_parse_percent_rejects_invalid_numeric_values() -> None:
    with pytest.raises(SystemExit, match="invalid numeric value"):
        enforce_coverage_gates._parse_percent("not-a-number")


def test_coverage_root_requires_existing_report(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="coverage report not found"):
        enforce_coverage_gates._coverage_root(tmp_path / "missing.xml")


def test_module_coverage_percent_requires_line_rate_attribute(tmp_path: Path) -> None:
    report = tmp_path / "coverage.xml"
    report.write_text(
        '<?xml version="1.0" ?>\n'
        '<coverage line-rate="0.9" branch-rate="0" version="7">\n'
        '<packages><package name="pawcontrol" line-rate="0" branch-rate="0">\n'
        '<classes><class filename="custom_components/pawcontrol/coordinator.py" '
        'branch-rate="1"><lines /></class></classes>\n'
        "</package></packages></coverage>\n",
        encoding="utf-8",
    )

    root = enforce_coverage_gates._coverage_root(report)
    with pytest.raises(SystemExit, match="missing line-rate"):
        enforce_coverage_gates._module_coverage_percent(
            root,
            "custom_components/pawcontrol/coordinator.py",
        )


def test_load_branch_exceptions_rejects_non_object_entries(tmp_path: Path) -> None:
    exceptions_file = tmp_path / "exceptions.json"
    exceptions_file.write_text('["bad-entry"]', encoding="utf-8")

    with pytest.raises(SystemExit, match="JSON objects"):
        enforce_coverage_gates._load_branch_exceptions(exceptions_file)


def test_evaluate_gates_fails_when_branch_exception_floor_is_not_met(
    tmp_path: Path,
) -> None:
    report = _write_coverage_xml(
        tmp_path,
        line_rate="0.95",
        class_rates={
            "custom_components/pawcontrol/coordinator.py": ("0.95", "0.70"),
            "custom_components/pawcontrol/config_flow.py": ("0.95", "1"),
            "custom_components/pawcontrol/services.py": ("0.95", "1"),
            "custom_components/pawcontrol/data_manager.py": ("0.95", "1"),
        },
    )
    exceptions_file = tmp_path / "exceptions.json"
    exceptions_file.write_text(
        '[{"path":"custom_components/pawcontrol/coordinator.py",'
        '"minimum_branch_percent":"80","rationale":"legacy path"}]',
        encoding="utf-8",
    )

    _, failures, notices = enforce_coverage_gates._evaluate_gates(
        report,
        exceptions_file,
        enforce_coverage_gates.DEFAULT_TOTAL_MINIMUM_PERCENT,
        enforce_coverage_gates.DEFAULT_CRITICAL_MODULE_MINIMUM_PERCENT,
    )

    assert notices == []
    assert any("exception floor failed" in failure for failure in failures)


def test_main_reports_passed_gates(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _write_coverage_xml(
        tmp_path,
        line_rate="0.92",
        class_rates={
            "custom_components/pawcontrol/coordinator.py": ("0.95", "1"),
            "custom_components/pawcontrol/config_flow.py": ("0.95", "1"),
            "custom_components/pawcontrol/services.py": ("0.95", "1"),
            "custom_components/pawcontrol/data_manager.py": ("0.95", "1"),
        },
    )

    from unittest.mock import patch

    with patch(
        "sys.argv",
        [
            "enforce_coverage_gates.py",
            "--coverage-xml",
            str(report),
            "--exceptions-file",
            str(tmp_path / "missing-exceptions.json"),
        ],
    ):
        result = enforce_coverage_gates.main()

    output = capsys.readouterr().out
    assert result == 0
    assert "Coverage gates passed." in output
