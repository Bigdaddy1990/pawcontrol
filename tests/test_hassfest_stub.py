import json
from pathlib import Path

from scripts.hassfest import run


def _build_stub_integration(tmp_path: Path, *, domain: str = "demo") -> Path:
  integration_path = tmp_path / "custom_components" / domain  # noqa: E111
  integration_path.mkdir(parents=True)  # noqa: E111

  manifest = json.loads(  # noqa: E111
    Path("custom_components/pawcontrol/manifest.json").read_text(),
  )
  manifest["domain"] = domain  # noqa: E111
  manifest["loggers"] = [f"custom_components.{domain}"]  # noqa: E111
  manifest.setdefault("supported_by", None)  # noqa: E111
  (integration_path / "manifest.json").write_text(  # noqa: E111
    json.dumps(manifest),
    encoding="utf-8",
  )

  (integration_path / "strings.json").write_text("{}", encoding="utf-8")  # noqa: E111
  translations = integration_path / "translations"  # noqa: E111
  translations.mkdir()  # noqa: E111
  (translations / "en.json").write_text("{}", encoding="utf-8")  # noqa: E111

  return integration_path  # noqa: E111


def test_hassfest_stub_passes_for_valid_integration(tmp_path: Path) -> None:
  integration_path = _build_stub_integration(tmp_path)  # noqa: E111

  assert run(["--integration-path", str(integration_path)]) == 0  # noqa: E111


def test_hassfest_stub_reports_missing_translations(tmp_path: Path) -> None:
  integration_path = _build_stub_integration(tmp_path, domain="missing")  # noqa: E111
  (integration_path / "translations" / "en.json").unlink()  # noqa: E111

  assert run(["--integration-path", str(integration_path)]) == 1  # noqa: E111


def test_hassfest_stub_rejects_invalid_iot_class(tmp_path: Path) -> None:
  integration_path = _build_stub_integration(tmp_path, domain="invalid_iot")  # noqa: E111
  manifest_path = integration_path / "manifest.json"  # noqa: E111
  manifest = json.loads(manifest_path.read_text())  # noqa: E111
  manifest["iot_class"] = "invalid"  # noqa: E111
  manifest_path.write_text(json.dumps(manifest), encoding="utf-8")  # noqa: E111

  assert run(["--integration-path", str(integration_path)]) == 1  # noqa: E111


def test_hassfest_stub_rejects_non_object_translations(tmp_path: Path) -> None:
  integration_path = _build_stub_integration(  # noqa: E111
    tmp_path,
    domain="invalid_translation",
  )
  (integration_path / "strings.json").write_text("[]", encoding="utf-8")  # noqa: E111
  (integration_path / "translations" / "en.json").write_text("[]", encoding="utf-8")  # noqa: E111

  assert run(["--integration-path", str(integration_path)]) == 1  # noqa: E111
