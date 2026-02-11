from __future__ import annotations

import json
from pathlib import Path

from scripts.hassfest import run


def _build_stub_integration(tmp_path: Path, *, domain: str = "demo") -> Path:
  integration_path = tmp_path / "custom_components" / domain
  integration_path.mkdir(parents=True)

  manifest = json.loads(
    Path("custom_components/pawcontrol/manifest.json").read_text(),
  )
  manifest["domain"] = domain
  manifest["loggers"] = [f"custom_components.{domain}"]
  manifest.setdefault("supported_by", None)
  (integration_path / "manifest.json").write_text(
    json.dumps(manifest),
    encoding="utf-8",
  )

  (integration_path / "strings.json").write_text("{}", encoding="utf-8")
  translations = integration_path / "translations"
  translations.mkdir()
  (translations / "en.json").write_text("{}", encoding="utf-8")

  return integration_path


def test_hassfest_stub_passes_for_valid_integration(tmp_path: Path) -> None:
  integration_path = _build_stub_integration(tmp_path)

  assert run(["--integration-path", str(integration_path)]) == 0


def test_hassfest_stub_reports_missing_translations(tmp_path: Path) -> None:
  integration_path = _build_stub_integration(tmp_path, domain="missing")
  (integration_path / "translations" / "en.json").unlink()

  assert run(["--integration-path", str(integration_path)]) == 1


def test_hassfest_stub_rejects_invalid_iot_class(tmp_path: Path) -> None:
  integration_path = _build_stub_integration(tmp_path, domain="invalid_iot")
  manifest_path = integration_path / "manifest.json"
  manifest = json.loads(manifest_path.read_text())
  manifest["iot_class"] = "invalid"
  manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

  assert run(["--integration-path", str(integration_path)]) == 1


def test_hassfest_stub_rejects_non_object_translations(tmp_path: Path) -> None:
  integration_path = _build_stub_integration(
    tmp_path,
    domain="invalid_translation",
  )
  (integration_path / "strings.json").write_text("[]", encoding="utf-8")
  (integration_path / "translations" / "en.json").write_text("[]", encoding="utf-8")

  assert run(["--integration-path", str(integration_path)]) == 1
