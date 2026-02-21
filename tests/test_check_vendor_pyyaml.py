"""Tests for the vendored PyYAML monitoring helper."""

import argparse

from pip._vendor.packaging.version import Version
import pytest
from scripts import check_vendor_pyyaml as module


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


def test_load_vendor_version_from_package_init(tmp_path, monkeypatch) -> None:
    """The monitor reads __version__ from the vendored package init file."""
    package_init = tmp_path / "annotatedyaml/_vendor/yaml/__init__.py"
    package_init.parent.mkdir(parents=True)
    package_init.write_text('__version__ = "6.0.1"\n', encoding="utf-8")

    monkeypatch.setattr(module, "ANNOTATEDYAML_INIT", package_init)
    monkeypatch.setattr(module, "ANNOTATEDYAML_MODULE", tmp_path / "missing.py")

    assert str(module.load_vendor_version()) == "6.0.1"


def test_load_vendor_version_falls_back_to_module_file(tmp_path, monkeypatch) -> None:
    """The monitor supports the single-file yaml.py vendor layout."""
    module_file = tmp_path / "annotatedyaml/_vendor/yaml.py"
    module_file.parent.mkdir(parents=True)
    module_file.write_text('__version__ = "6.0.2"\n', encoding="utf-8")

    monkeypatch.setattr(module, "ANNOTATEDYAML_INIT", tmp_path / "missing/__init__.py")
    monkeypatch.setattr(module, "ANNOTATEDYAML_MODULE", module_file)

    assert str(module.load_vendor_version()) == "6.0.2"


def test_load_vendor_version_ignores_commented_assignment(
    tmp_path, monkeypatch
) -> None:
    """Only real assignment statements should be parsed for ``__version__``."""
    module_file = tmp_path / "annotatedyaml/_vendor/yaml.py"
    module_file.parent.mkdir(parents=True)
    module_file.write_text(
        '# __version__ = "0.0.0"\n  __version__ = "6.0.3"\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "ANNOTATEDYAML_INIT", tmp_path / "missing/__init__.py")
    monkeypatch.setattr(module, "ANNOTATEDYAML_MODULE", module_file)

    assert str(module.load_vendor_version()) == "6.0.3"
