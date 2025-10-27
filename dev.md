# Development plan

## Workflow overview
- Verwende eine lokale virtuelle Umgebung (`python -m venv .venv`), installiere
  danach `requirements_test.txt` und `requirements.txt`, und exportiere
  `PYTHONPATH=$(pwd)`, damit die Home-Assistant-Shims unter `pytest_asyncio/`,
  `pytest_cov/` sowie die Hilfsskripte unter `script/` gefunden werden.【F:requirements_test.txt†L1-L25】【F:sitecustomize.py†L1-L175】
- Führe vor jedem Commit `ruff format`, `ruff check`, `pytest -q`,
  `mypy custom_components/pawcontrol` und
  `python -m script.hassfest --integration-path custom_components/pawcontrol`
  aus, damit die Platinum-Gates aus `pyproject.toml` eingehalten werden.【F:pyproject.toml†L7-L72】【F:.github/copilot-instructions.md†L27-L46】
- Aktualisiere nach Änderungen an Beitragsrichtlinien oder Übersetzungen die
  Spiegeldateien über `python -m script.sync_contributor_guides` bzw.
  `python -m script.sync_localization_flags` und führe die Wächter unter
  `scripts/` aus, wenn Diagnostik oder Guard-Metriken betroffen sind.【F:script/sync_contributor_guides.py†L1-L121】【F:script/sync_localization_flags.py†L1-L129】

## Validated tool snapshot (2025-02-15)
- ✅ `ruff check`
- ✅ `pytest -q`
- ✅ `mypy custom_components/pawcontrol`
- ✅ `python -m script.hassfest --integration-path custom_components/pawcontrol`

Die Läufe spiegeln den aktuellen Stand ohne neue Warnungen wider und halten die
Branch-Coverage-Anforderungen aus `pyproject.toml` ein.【F:pyproject.toml†L7-L62】

## Fehlerliste
1. *Keine bekannten Fehlerstände* – Laufende Checks und Tests passierten zuletzt
   ohne Abweichungen.

## Verbesserungsmöglichkeiten
- Performance der Coverage-Läufe weiter optimieren; Ziel bleibt eine Laufzeit
  unter 20 Minuten trotz aktiviertem Branch-Tracing für das komplette Paket.
- Beobachte Übersetzungs- und Dokumentations-Syncs nach Schemaänderungen in den
  Diagnostics, damit `setup_flags_panel_*`-Schlüssel konsistent bleiben.【F:custom_components/pawcontrol/diagnostics.py†L688-L867】【F:custom_components/pawcontrol/strings.json†L1396-L1405】
- Evaluiere zusätzliche Plattform-spezifische Regressionstests für neue Entity-
  Typen, sobald weitere Home-Assistant-Plattformen integriert werden sollen, um
  die Coordinator-Schnittstellen weiterhin abzudecken.【F:tests/components/pawcontrol/test_all_platforms.py†L1451-L1494】【F:tests/unit/test_runtime_manager_container_usage.py†L82-L374】
