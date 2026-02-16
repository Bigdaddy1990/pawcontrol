"""Tests for the vendored PyYAML monitoring helper."""

from __future__ import annotations

import argparse

from pip._vendor.packaging.version import Version
import pytest
from scripts import check_vendor_pyyaml as module


def _make_namespace(**overrides: object) -> argparse.Namespace:
  """Return a namespace emulating parsed CLI arguments."""  # noqa: E111

  base: dict[str, object] = {  # noqa: E111
    "fail_on_outdated": False,
    "fail_severity": "HIGH",
    "target_python_tag": None,
    "target_platform_fragment": None,
    "wheel_profile": [],
    "metadata_path": None,
  }
  base.update(overrides)  # noqa: E111
  return argparse.Namespace(**base)  # noqa: E111


def test_parse_wheel_profile() -> None:
  """Parsing wheel profile strings returns dataclass instances."""  # noqa: E111

  profile = module._parse_wheel_profile("cp313:musllinux")  # noqa: E111
  assert profile.python_tag == "cp313"  # noqa: E111
  assert profile.platform_fragment == "musllinux"  # noqa: E111


@pytest.mark.parametrize("raw", ["cp313", "cp313-", " :musllinux"])
def test_parse_wheel_profile_rejects_invalid(raw: str) -> None:
  """Invalid wheel profile strings raise an ``ArgumentTypeError``."""  # noqa: E111

  with pytest.raises(argparse.ArgumentTypeError):  # noqa: E111
    module._parse_wheel_profile(raw)


def test_normalise_wheel_profiles_defaults() -> None:
  """Without overrides the default manylinux and musllinux profiles are used."""  # noqa: E111

  namespace = _make_namespace()  # noqa: E111
  profiles = module._normalise_wheel_profiles(namespace)  # noqa: E111
  assert [(profile.python_tag, profile.platform_fragment) for profile in profiles] == [  # noqa: E111
    (default.python_tag, default.platform_fragment)
    for default in module.DEFAULT_WHEEL_PROFILES
  ]


def test_normalise_wheel_profiles_legacy_flags() -> None:
  """Legacy target flags still map to a single profile."""  # noqa: E111

  namespace = _make_namespace(  # noqa: E111
    target_python_tag="cp311",
    target_platform_fragment="manylinux",
  )
  profiles = module._normalise_wheel_profiles(namespace)  # noqa: E111
  assert len(profiles) == 1  # noqa: E111
  assert profiles[0].python_tag == "cp311"  # noqa: E111
  assert profiles[0].platform_fragment == "manylinux"  # noqa: E111


def test_build_metadata_document_serialises_versions() -> None:
  """Metadata documents are JSON serialisable and contain string versions."""  # noqa: E111

  profile_manylinux = module.WheelProfile("cp313", "manylinux")  # noqa: E111
  profile_musllinux = module.WheelProfile("cp313", "musllinux")  # noqa: E111
  metadata = module.build_metadata_document(  # noqa: E111
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

  assert metadata["vendor_version"] == "6.0"  # noqa: E111
  assert metadata["latest_release"] == "6.0.2"  # noqa: E111
  first_wheel = metadata["wheel_matches"][0]  # noqa: E111
  assert first_wheel["release"] == "6.0.2"  # noqa: E111
  assert first_wheel["url"] == "https://files.pythonhosted.org/demo"  # noqa: E111
  assert metadata["wheel_matches"][1]["release"] is None  # noqa: E111
