"""Executable entry point for the hassfest validation shim."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path

from .manifest import validate_version
from .model import Config, Integration


def _load_integration(path: Path, config: Config) -> Integration:
    """Return an Integration populated from ``path``."""

    manifest_path = path / "manifest.json"
    if not manifest_path.exists():
        integration = Integration(path=path, _config=config)
        integration.add_error("manifest", "manifest.json not found")
        return integration

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        integration = Integration(path=path, _config=config)
        integration.add_error("manifest", f"Invalid JSON: {err}")
        return integration

    integration = Integration(path=path, _config=config, _manifest=manifest)
    config.integrations[integration.domain] = integration
    return integration


def _validate_integrations(integration_paths: Iterable[Path], config: Config) -> int:
    """Run manifest validations and return the number of errors."""

    errors = 0
    for path in integration_paths:
        integration = _load_integration(path, config)
        validate_version(integration)
        errors += len(integration.errors)
    return errors


def main(argv: list[str] | None = None) -> int:
    """CLI entry point compatible with ``python -m script.hassfest``."""

    parser = argparse.ArgumentParser(description="Validate Home Assistant integrations")
    parser.add_argument(
        "--integration-path",
        dest="integration_paths",
        action="append",
        default=[],
        help="Path to a custom integration directory",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root for resolving relative integration paths",
    )
    parser.add_argument(
        "--skip-logo-check",
        action="store_true",
        help="Ignore Home Assistant brand asset validation when running Hassfest.",
    )
    args = parser.parse_args(argv)

    config = Config(root=args.root)

    if not args.integration_paths:
        parser.error("At least one --integration-path must be provided")

    if args.skip_logo_check:
        print("Skipping Hassfest logo validation as requested.")

    integration_dirs = [
        (args.root / Path(path)).resolve()
        if not Path(path).is_absolute()
        else Path(path)
        for path in args.integration_paths
    ]

    errors = _validate_integrations(integration_dirs, config)

    if errors:
        for integration in config.integrations.values():
            for error in integration.errors:
                print(f"{integration.domain}: {error.error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
