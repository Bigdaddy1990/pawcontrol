# Development plan

## Qualitäts-Gate-Erwartungen
- Run `ruff check`, `pytest -q`, `mypy custom_components/pawcontrol`, and `python -m script.hassfest --integration-path custom_components/pawcontrol` before opening a pull request so the Platinum guardrails stay enforced.【F:.github/copilot-instructions.md†L29-L64】
- Target Python 3.13+ features and reuse the coordinator/manager helpers so runtime data remains fully typed and compatible with Home Assistant expectations.【F:.github/copilot-instructions.md†L45-L118】

## Aktueller Qualitätsstatus
- ✅ `ruff check` – lint passes after wiring the annotatedyaml fallback.【632c4e†L1-L2】
- ✅ `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=$(pwd) pytest -q` – 1 064 Tests grün, 1 nightly-only Integrationslauf übersprungen.【d74759†L1-L6】
- ✅ `mypy custom_components/pawcontrol` – strikt typisierte Oberfläche bleibt fehlerfrei.【8e24f8†L1-L2】
- ✅ `python -m script.hassfest --integration-path custom_components/pawcontrol` – Manifest- und String-Validierung laufen ohne Beanstandung durch.【56a36d†L1-L1】

## Erledigte Arbeiten
- `annotatedyaml` lädt jetzt automatisch den vendored Build, fällt aber ohne System-Paket auf das lokal gebündelte Stub-Modul zurück, sodass `script.hassfest` und die Hassfest-Tests auch in Minimalumgebungen funktionieren.【F:annotatedyaml/__init__.py†L1-L74】
- Die Test-Blueprints erhalten mit `pyyaml` eine deklarierte Abhängigkeit, womit Resilience-E2E-Läufe das YAML-Schema einlesen können.【F:requirements_test.txt†L3-L11】

## Fehlerliste
- Keine offenen Gate-Blocker nach dem AnnotatedYAML-Fallback; nächste Arbeiten konzentrieren sich auf langfristige Wartbarkeit des Stubs.

## Verbesserungsplan
1. **Vendor-Pfad beobachten.** Bei kommenden Home-Assistant-Releases prüfen, ob der echte `annotatedyaml` Build verfügbar ist und das Fallback nachgelagert aufräumen.【F:annotatedyaml/__init__.py†L28-L74】
2. **Automatisches Requirements-Audit.** Ein kleines Guard-Skript ergänzen, das sicherstellt, dass alle Tests die im Code verwendeten Third-Party-Pakete (z. B. `pyyaml`) deklarieren, damit künftige Modulimporte nicht wieder überraschend scheitern.【F:requirements_test.txt†L3-L11】
3. **Stub-Abdeckung erweitern.** Für den `annotatedyaml`-Fallback gezielte Tests ergänzen, damit der Abzweig bei künftigen Refactorings nicht versehentlich bricht.【F:annotatedyaml/__init__.py†L1-L74】

## Monitoring & Rhythmus
- Durchlaufe monatlich die Aufgaben aus `docs/MAINTENANCE.md`, damit Lokalisierungen, Diagnostik und Qualitätsnachweise aktuell bleiben.【F:docs/MAINTENANCE.md†L1-L40】
- Aktualisiere nach Feature-Änderungen die Contributor-Guides per `python -m script.sync_contributor_guides`, damit alle Assistenten dieselben Richtlinien ausliefern.【F:script/sync_contributor_guides.py†L1-L92】
