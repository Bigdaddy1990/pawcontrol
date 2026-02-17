"""Tests for the Home Assistant dependency synchroniser."""

import argparse
import json
from pathlib import Path
import tarfile

from packaging.version import Version
from scripts import sync_homeassistant_dependencies as module


def _write_requirements(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")  # noqa: E111


def _create_pyyaml_archive(root: Path, version: str) -> Path:
    source_root = root / f"PyYAML-{version}"  # noqa: E111
    yaml_dir = source_root / "yaml"  # noqa: E111
    yaml_dir.mkdir(parents=True)  # noqa: E111
    (yaml_dir / "__init__.py").write_text(  # noqa: E111
        f'__version__ = "{version}"\n', encoding="utf-8"
    )
    (source_root / "LICENSE").write_text("demo license", encoding="utf-8")  # noqa: E111
    archive_path = root / f"PyYAML-{version}.tar.gz"  # noqa: E111
    with tarfile.open(archive_path, "w:gz") as archive:  # noqa: E111
        archive.add(source_root, arcname=source_root.name)
    return archive_path  # noqa: E111


def test_sync_updates_dependency_files(tmp_path, monkeypatch) -> None:
    """The synchroniser aligns requirements, manifest, and vendor copies."""  # noqa: E111

    workdir = tmp_path / "workspace"  # noqa: E111
    manifest_path = workdir / "custom_components/pawcontrol/manifest.json"  # noqa: E111
    manifest_path.parent.mkdir(parents=True)  # noqa: E111
    manifest_path.write_text(  # noqa: E111
        json.dumps(
            {
                "domain": "pawcontrol",
                "name": "PawControl",
                "requirements": [
                    "aiofiles>=23.1.0",
                    "aiohttp>=3.12.0",
                    "jinja2>=3.0.0",
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    requirements_path = workdir / "requirements.txt"  # noqa: E111
    test_requirements_path = workdir / "requirements_test.txt"  # noqa: E111
    _write_requirements(  # noqa: E111
        requirements_path,
        [
            "aiohttp>=3.12.0",
            "voluptuous>=0.15.0",
        ],
    )
    _write_requirements(  # noqa: E111
        test_requirements_path,
        [
            "aiofiles>=23.1.0",
            "pytest-homeassistant-custom-component  # follows daily HA version",
        ],
    )

    vendor_package = workdir / "annotatedyaml/_vendor/yaml"  # noqa: E111
    vendor_package.mkdir(parents=True)  # noqa: E111
    (vendor_package / "__init__.py").write_text(
        '__version__ = "5.4"\n', encoding="utf-8"
    )  # noqa: E111
    (workdir / "annotatedyaml/_vendor/PyYAML_LICENSE").write_text(  # noqa: E111
        "old license", encoding="utf-8"
    )

    ha_root = tmp_path / "ha"  # noqa: E111
    ha_root.mkdir()  # noqa: E111
    (ha_root / "homeassistant").mkdir()  # noqa: E111
    (ha_root / module.HA_PACKAGE_CONSTRAINTS).write_text(  # noqa: E111
        "aiofiles>=24.1.0\nPyYAML==6.0.1\n",
        encoding="utf-8",
    )
    (ha_root / module.HA_REQUIREMENTS).write_text(  # noqa: E111
        "aiohttp==3.13.2\nvoluptuous==0.15.2\n",
        encoding="utf-8",
    )
    (ha_root / module.HA_REQUIREMENTS_TEST).write_text("# unused\n", encoding="utf-8")  # noqa: E111
    (ha_root / module.HA_PYPROJECT).write_text(  # noqa: E111
        """
[project]
dependencies = [
  "jinja2==3.1.4",
]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    archive_path = _create_pyyaml_archive(tmp_path, "6.0.1")  # noqa: E111

    metadata_path = workdir / "generated/vendor_pyyaml_status.json"  # noqa: E111

    stub_result = module.vendor_monitor.MonitoringResult(  # noqa: E111
        vendor_version=Version("6.0.1"),
        latest_release=Version("6.0.1"),
        latest_release_files=[],
        vulnerabilities=[],
        wheel_matches=[],
    )

    monkeypatch.chdir(workdir)  # noqa: E111
    monkeypatch.setattr(  # noqa: E111
        module.vendor_monitor,
        "load_vendor_version",
        lambda: Version("5.4"),
    )
    monkeypatch.setattr(  # noqa: E111
        module.vendor_monitor,
        "evaluate",
        lambda **kwargs: (stub_result, 0),
    )
    captured_metadata: dict[str, object] = {}  # noqa: E111

    def _capture_metadata(result):  # noqa: E111
        document = {"vendor_version": str(result.vendor_version)}
        captured_metadata["payload"] = document
        return document

    monkeypatch.setattr(  # noqa: E111
        module.vendor_monitor,
        "build_metadata_document",
        _capture_metadata,
    )

    namespace = argparse.Namespace(  # noqa: E111
        home_assistant_root=ha_root,
        reference_url=module.DEFAULT_REFERENCE_URL,
        manifest_path=manifest_path,
        requirements_file=[requirements_path, test_requirements_path],
        metadata_path=metadata_path,
        skip_pyyaml_sync=False,
        pyyaml_archive=archive_path,
        skip_pyyaml_metadata=False,
    )
    monkeypatch.setattr(module, "parse_arguments", lambda: namespace)  # noqa: E111

    exit_code = module.main()  # noqa: E111
    assert exit_code == 1  # noqa: E111

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))  # noqa: E111
    assert manifest["requirements"] == [  # noqa: E111
        "aiofiles>=24.1.0",
        "aiohttp==3.13.2",
        "jinja2==3.1.4",
    ]

    assert (  # noqa: E111
        requirements_path.read_text(encoding="utf-8")
        == "aiohttp==3.13.2\nvoluptuous==0.15.2\n"
    )
    assert (  # noqa: E111
        test_requirements_path.read_text(encoding="utf-8")
        == "aiofiles>=24.1.0\npytest-homeassistant-custom-component  # follows daily HA version\n"  # noqa: E501
    )

    vendor_version = (
        (vendor_package / "__init__.py").read_text(encoding="utf-8").strip()
    )  # noqa: E111
    assert vendor_version == '__version__ = "6.0.1"'  # noqa: E111
    assert (workdir / "annotatedyaml/_vendor/PyYAML_LICENSE").read_text(  # noqa: E111
        encoding="utf-8"
    ) == "demo license"
    assert json.loads(metadata_path.read_text(encoding="utf-8")) == {  # noqa: E111
        "vendor_version": "6.0.1"
    }
    assert captured_metadata["payload"] == {"vendor_version": "6.0.1"}  # noqa: E111
