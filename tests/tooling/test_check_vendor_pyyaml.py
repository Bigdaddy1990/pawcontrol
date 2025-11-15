"""Tests for the vendored PyYAML monitoring helper."""

from __future__ import annotations

import argparse

import pytest
from pip._vendor.packaging.version import Version
from script import check_vendor_pyyaml as module


def _make_namespace(**overrides: object) -> argparse.Namespace:
    """Return a namespace emulating parsed CLI arguments."""

    base: dict[str, object] = {
        "fail_on_outdated": False,
        "fail_severity": "HIGH",
        "target_python_tag": None,
        "target_platform_fragment": None,
        "wheel_profile": [],
        "metadata_path": None,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def test_parse_wheel_profile() -> None:
    """Parsing wheel profile strings returns dataclass instances."""

    profile = module._parse_wheel_profile("cp313:musllinux")
    assert profile.python_tag == "cp313"
    assert profile.platform_fragment == "musllinux"


@pytest.mark.parametrize("raw", ["cp313", "cp313-", " :musllinux"])
def test_parse_wheel_profile_rejects_invalid(raw: str) -> None:
    """Invalid wheel profile strings raise an ``ArgumentTypeError``."""

    with pytest.raises(argparse.ArgumentTypeError):
        module._parse_wheel_profile(raw)


def test_normalise_wheel_profiles_defaults() -> None:
    """Without overrides the default manylinux and musllinux profiles are used."""

    namespace = _make_namespace()
    profiles = module._normalise_wheel_profiles(namespace)
    assert [
        (profile.python_tag, profile.platform_fragment) for profile in profiles
    ] == [
        (default.python_tag, default.platform_fragment)
        for default in module.DEFAULT_WHEEL_PROFILES
    ]


def test_normalise_wheel_profiles_legacy_flags() -> None:
    """Legacy target flags still map to a single profile."""

    namespace = _make_namespace(
        target_python_tag="cp311",
        target_platform_fragment="manylinux",
    )
    profiles = module._normalise_wheel_profiles(namespace)
    assert len(profiles) == 1
    assert profiles[0].python_tag == "cp311"
    assert profiles[0].platform_fragment == "manylinux"


def test_build_metadata_document_serialises_versions() -> None:
    """Metadata documents are JSON serialisable and contain string versions."""

    profile_manylinux = module.WheelProfile("cp313", "manylinux")
    profile_musllinux = module.WheelProfile("cp313", "musllinux")
    metadata = module.build_metadata_document(
        module.MonitoringResult(
            vendor_version=Version("6.0"),
            latest_release=Version("6.0.2"),
            latest_release_files=[],
            vulnerabilities=[
                module.VulnerabilityRecord(
                    identifier="CVE-0000-0000",
                    summary="demo",
                    severity="LOW",
                    affected_version_range="[6.0, 6.0.2)",
                    references=["https://example.invalid"],
                )
            ],
            wheel_matches=[
                module.WheelMatch(
                    profile=profile_manylinux,
                    release=Version("6.0.2"),
                    filename="PyYAML-6.0.2-cp313-manylinux.whl",
                    url="https://files.pythonhosted.org/demo",
                ),
                module.WheelMatch(
                    profile=profile_musllinux,
                    release=None,
                    filename="",
                    url="",
                ),
            ],
        )
    )

    assert metadata["vendor_version"] == "6.0"
    assert metadata["latest_release"] == "6.0.2"
    first_wheel = metadata["wheel_matches"][0]
    assert first_wheel["release"] == "6.0.2"
    assert first_wheel["url"] == "https://files.pythonhosted.org/demo"
    assert metadata["wheel_matches"][1]["release"] is None
