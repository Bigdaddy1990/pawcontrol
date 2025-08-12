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


## Device Automations
Diese Integration stellt **Geräte-Trigger** bereit (Einstellungen → Automationen → Gerät auswählen):
- `gps_location_posted`
- `walk_started`
- `walk_ended`
- `geofence_alert`
Die Trigger werden über interne Events (`pawcontrol_<type>`) ausgelöst und enthalten `device_id`/`dog_id` im `event_data`.


## Geofence-Events & Device-Automations

Diese Integration feuert bei Geofence-Übergängen **Events** mit `device_id`:
- `pawcontrol_geofence_alert` mit `action` = `entered` | `exited`, `zone`, `distance_m`, `radius_m`
- Zusätzlich: `pawcontrol_safe_zone_entered` / `pawcontrol_safe_zone_left` (abwärtskompatibel)

In der Automations-UI stehen als **Geräte-Trigger** zur Verfügung:
- `geofence_alert`, `gps_location_posted`, `walk_started`, `walk_ended`

**Geräte-Conditions**:
- `is_home` – Hund ist laut Integration „zu Hause“
- `in_geofence` – Hund ist innerhalb des definierten Safe-Zone-Grenzbereichs (alias von `is_home`)

> Hinweis: Geofence-Alerts lassen sich per Service `pawcontrol.toggle_geofence_alerts` je Hund aktivieren/deaktivieren.


## Branding

Siehe [`docs/BRANDING.md`](docs/BRANDING.md) für die Schritte zum Einreichen der Logos/Icons im zentralen Brands-Repo.


## Repairs & Wartung

Diese Integration meldet Probleme im **Reparaturen**-Dashboard (Einstellungen → System → Reparaturen) und bietet **Fix-Flows** an:

- **`invalid_geofence`** – Geofence-Einstellungen sind ungültig. Der Fix-Flow fragt **Latitude**, **Longitude** und **Radius (m)** ab und aktualisiert die Optionen.
- **`stale_devices`** – Veraltete Geräte erkannt. Der Fix-Flow entfernt die verwaisten Geräte automatisch. Alternativ steht der Service `pawcontrol.prune_stale_devices` zur Verfügung (mit Option `auto: false` nur Hinweis ohne Löschen).

> Hintergrund: Repair-Issues/Fix-Flows folgen den offiziellen HA-Vorgaben. Issues werden automatisch entfernt, sobald der Fix-Flow erfolgreich war.


**Hinweis:** Der Fix-Flow für `invalid_geofence` **öffnet jetzt direkt den Options-Dialog** der Integration.
Dort kannst du `home_lat`, `home_lon` und `geofence_radius_m` setzen. Nach dem Speichern verschwindet der Hinweis automatisch.


### Options-Flow (mit Auto-Reload)

Der Options-Dialog nutzt **OptionsFlowWithReload**: Änderungen werden nach dem Speichern **automatisch neu geladen** – kein manueller Reload nötig.
Es gibt einen dedizierten **„Geofence“**-Step (Latitude/Longitude/Radius + Auto-Prune-Schalter).
