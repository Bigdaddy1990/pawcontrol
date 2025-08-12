[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/Bigdaddy1990/pawcontrol/main.svg)](https://results.pre-commit.ci/latest/github/Bigdaddy1990/pawcontrol/main)

[![CI](https://github.com/Bigdaddy1990/pawcontrol/actions/workflows/ci.yml/badge.svg)](https://github.com/Bigdaddy1990/pawcontrol/actions/workflows/ci.yml)
[![hassfest](https://github.com/Bigdaddy1990/pawcontrol/actions/workflows/hassfest.yml/badge.svg)](https://github.com/Bigdaddy1990/pawcontrol/actions/workflows/hassfest.yml)
[![HACS validation](https://github.com/Bigdaddy1990/pawcontrol/actions/workflows/hacs.yml/badge.svg)](https://github.com/Bigdaddy1990/pawcontrol/actions/workflows/hacs.yml)
[![Release](https://img.shields.io/github/v/release/Bigdaddy1990/pawcontrol?sort=semver)](https://github.com/Bigdaddy1990/pawcontrol/releases)

[![CI](https://github.com/Bigdaddy1990/pawcontrol/actions/workflows/ci.yml/badge.svg)](https://github.com/Bigdaddy1990/pawcontrol/actions/workflows/ci.yml)

# Paw Control – Home Assistant Integration

**Purpose**: Track dog-related activities, GPS routes, geofence alerts, notifications & diagnostics.

## Installation
1. Copy `custom_components/pawcontrol/` into your HA `config/custom_components/` folder.
2. Restart Home Assistant.
3. Settings → Integrations → *Add Integration* → **Paw Control**.

## Features
- GPS walk tracking (start/stop/pause/resume; route export & diagnostics).
- Route history list/purge/export (events & storage).
- Geofence alerts toggle, medication/feeding logs, notifications.
- Diagnostics download with sensitive data redaction.
- Repair flows for common issues (e.g., storage corruption).

## Services
See `services.yaml` for the full list and field descriptions. All services accept optional `config_entry_id` to target a specific instance.

## Options & Reconfigure
Change history retention, geofence radius, notify target via **Reconfigure** in the integration settings.

## Devices & Entities
- Each dog/tracker is a **Device** (Device Registry).
- Entities have `unique_id`, `_attr_has_entity_name=True`, and use `translation_key` for naming.

## Icons & Translations
- Dynamic icons via `icons.json`.
- Localized strings in `translations/en.json` and `translations/de.json`.

## Diagnostics
Settings → Integrations → Paw Control → (⋮) → **Download diagnostics**.

## Development / Tests
- Tests under `tests/`; run with `pytest`.
- Target coverage ≥ 95% (Silver/Gold requirement).


## Developer tooling

### Pre-commit
```bash
pipx install pre-commit  # or: pip install pre-commit
pre-commit install
pre-commit run --all-files
```

### Lint & Format (CI mirrors these)
```bash
ruff check .
ruff format .
black .
```

### Releases
- Conventional commits → Release Please erstellt automatisch einen Release-PR.
- Merge → Tag wird erstellt → Workflow **Release (tag)** baut `dist/pawcontrol.zip` und veröffentlicht das Release.

> Hinweis: Aktiviere **pre-commit.ci** für dieses Repo, indem du das GitHub-App-Setup abschließt (Sign-in auf https://pre-commit.ci/ und Repo auswählen).


## Installation via HACS (Custom Repository)

[![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?category=integration&owner=Bigdaddy1990&repository=pawcontrol)

1. In Home Assistant → **HACS → Integrationen** (oben rechts **⋮**).
2. **Custom repositories** wählen → URL `https://github.com/Bigdaddy1990/pawcontrol` eintragen → **Type: Integration** → **ADD**.
3. Anschließend in HACS nach **Paw Control** suchen → **Download** → Home Assistant neu starten.
4. Integration in **Einstellungen → Geräte & Dienste → Integration hinzufügen → Paw Control** konfigurieren.

> Alternativ direkt über My Home Assistant: [https://my.home-assistant.io/redirect/hacs_repository/?category=integration&owner=Bigdaddy1990&repository=pawcontrol](https://my.home-assistant.io/redirect/hacs_repository/?category=integration&owner=Bigdaddy1990&repository=pawcontrol)
