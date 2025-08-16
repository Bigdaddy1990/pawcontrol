# GitHub Scripts

Dieses Verzeichnis enthält Hilfsskripte für die Automatisierung von Home Assistant-konformen Entwicklungsaufgaben.

## 📁 Scripts

### `generate_requirements.py`
**Zweck:** Automatische Generierung von `requirements_test.txt` aus `pyproject.toml`

```bash
# Manuell ausführen:
python .github/scripts/generate_requirements.py

# Output: requirements_test.txt (im Root)
```

**Features:**
- ✅ Liest Test-Dependencies aus `pyproject.toml`
- ✅ Fügt Home Assistant-spezifische Requirements hinzu
- ✅ Sortiert und dedupliziert Dependencies
- ✅ Automatisch auf Home Assistant 2025.8.2 abgestimmt

### `ha_fix.py`
**Zweck:** Home Assistant-konforme Code-Quality Tools ausführen

```bash
# Auto-Fix (empfohlen):
python .github/scripts/ha_fix.py

# Nur prüfen (ohne Änderungen):
python .github/scripts/ha_fix.py --check
```

**Features:**
- ✅ pyupgrade (Python 3.13+)
- ✅ black formatting
- ✅ ruff linting + auto-fix
- ✅ ruff formatting
- ✅ pre-commit hooks
- ✅ Vollständig HA-Standards-konform

### `ruff_migrate.sh`
**Zweck:** Migration von anderen Linting-Tools zu Ruff

```bash
# Ausführen:
chmod +x .github/scripts/ruff_migrate.sh
./.github/scripts/ruff_migrate.sh
```

## 🔄 Workflow-Integration

### Main CI (`main-ci.yml`)
- **Generate Requirements:** Automatisch bei jedem Build
- **Code Quality:** Verwendet `ha_fix.py` für alle Auto-Fixes
- **Fallback:** Einzelne Tools falls Script fehlschlägt

### Maintenance (`maintenance.yml`)
- **Manual Trigger:** Über GitHub Actions UI
- **Actions:**
  - `generate-requirements`: Nur Requirements neu generieren
  - `fix-code-quality`: Nur Code-Quality ausführen  
  - `update-dependencies`: Beides kombiniert
  - `hassfest`: Nur Hassfest-Validation

## 🚀 Verwendung

### Lokal entwickeln:
```bash
# 1. Requirements aktualisieren
python .github/scripts/generate_requirements.py

# 2. Code-Quality prüfen
python .github/scripts/ha_fix.py --check

# 3. Auto-Fixes anwenden
python .github/scripts/ha_fix.py

# 4. Tests ausführen  
pip install -r requirements_test.txt
pytest tests/
```

### In CI/CD:
- **Automatisch:** Läuft bei jedem Push/PR
- **Manuell:** Über GitHub Actions → "HA Maintenance Tasks"

## 📊 Home Assistant Konformität

Alle Scripts entsprechen den [Home Assistant Development Standards](https://developers.home-assistant.io/):

- ✅ **Python 3.13+** (pyupgrade --py313-plus)
- ✅ **Home Assistant 2025.8.2** kompatibel
- ✅ **Ruff** für Linting (HA Standard)
- ✅ **Black** für Formatting (HA Standard)  
- ✅ **Pre-commit** Hooks eingebunden
- ✅ **Hassfest** Validation integriert

## 🛠️ Entwicklung

Alle Scripts sind:
- **Fehlerresistent:** Funktionieren auch bei Tool-Fehlern
- **Validiert:** Prüfen Output und Dependencies
- **Dokumentiert:** Klare Ausgaben und Logs
- **Pfad-unabhängig:** Funktionieren von jedem Verzeichnis

## 🔍 Troubleshooting

**Script schlägt fehl:**
```bash
# Einzelne Tools testen:
pyupgrade --py313-plus custom_components/pawcontrol/*.py
black --check custom_components tests
ruff check custom_components tests
```

**Requirements-Generation fehlschlägt:**
```bash
# Pyproject.toml validieren:
python -c "import tomllib; print(tomllib.loads(open('pyproject.toml').read()))"
```

**Path-Probleme:**
- Scripts laufen vom Repository-Root aus
- Verwenden absolute Pfade über `pathlib`
- Automatische Root-Detection eingebaut
