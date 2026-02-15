# 🧪 Test Migration Guide - __init__.py Refactoring

**Datum:** 2026-02-15
**Für:** PawControl Integration Test Suite

---

## 📋 ÜBERSICHT

Nach dem Refactoring von `__init__.py` müssen **einige Tests angepasst werden**, da interne Funktionen in Setup-Module verschoben wurden.

**Betroffene Tests:** ~10-20 Tests (geschätzt)
**Aufwand:** 2-3 Stunden
**Schwierigkeit:** 🟢 Niedrig (meist simple Import-Änderungen)

---

## 🔍 IDENTIFIZIERE BETROFFENE TESTS

### Schritt 1: Automatische Analyse

Führe das Analyse-Script aus:

```bash
python scripts/analyze_test_imports.py
```

**Output:**
```
🔍 Analyzing test files for import issues...
================================================================================

📊 ANALYSIS RESULTS:
   Critical issues: 5
   Warnings:        2
   Info:            0
   Total:           7

🔴 CRITICAL ISSUES (Must fix):
...
```

### Schritt 2: Manuelle Suche

Suche nach direkten Imports:

```bash
grep -r "from custom_components.pawcontrol import _async" tests/
grep -r "@patch.*custom_components.pawcontrol\._" tests/
```

---

## 🔧 MIGRATION PATTERNS

### Pattern 1: Direct Function Imports

#### ❌ Vorher:
```python
from custom_components.pawcontrol import _async_cleanup_runtime_data

async def test_cleanup():
    await _async_cleanup_runtime_data(runtime_data)
```

#### ✅ Nachher:
```python
from custom_components.pawcontrol.setup.cleanup import async_cleanup_runtime_data

async def test_cleanup():
    await async_cleanup_runtime_data(runtime_data)
```

**Hinweis:** Die führenden Underscores `_` wurden bei öffentlichen Funktionen entfernt!

---

### Pattern 2: Mock/Patch Decorators

#### ❌ Vorher:
```python
@patch("custom_components.pawcontrol._async_create_core_managers")
async def test_manager_init(mock_create):
    ...
```

#### ✅ Nachher:
```python
@patch("custom_components.pawcontrol.setup.manager_init._async_create_core_managers")
async def test_manager_init(mock_create):
    ...
```

---

### Pattern 3: Mock with unittest.mock

#### ❌ Vorher:
```python
with patch("custom_components.pawcontrol._validate_profile") as mock:
    mock.return_value = "standard"
    ...
```

#### ✅ Nachher:
```python
with patch("custom_components.pawcontrol.setup.validation._validate_profile") as mock:
    mock.return_value = "standard"
    ...
```

---

### Pattern 4: Multiple Imports

#### ❌ Vorher:
```python
from custom_components.pawcontrol import (
    _async_validate_dogs_config,
    _validate_profile,
    _extract_enabled_modules,
)
```

#### ✅ Nachher:
```python
from custom_components.pawcontrol.setup.validation import (
    _async_validate_dogs_config,
    _validate_profile,
    _extract_enabled_modules,
)
```

---

## 📍 FUNKTIONS-MAPPING

### cleanup.py (Moved Functions)

| Original (__init__.py) | Neuer Pfad (setup.cleanup) |
|------------------------|----------------------------|
| `_async_cleanup_runtime_data` | `async_cleanup_runtime_data` ✅ Public |
| `_async_cancel_background_monitor` | `_async_cancel_background_monitor` |
| `_async_cleanup_managers` | `_async_cleanup_managers` |
| `_remove_listeners` | `_remove_listeners` |
| `_async_shutdown_core_managers` | `_async_shutdown_core_managers` |
| `_clear_coordinator_references` | `_clear_coordinator_references` |
| `_async_run_manager_method` | `_async_run_manager_method` |

### validation.py (Moved Functions)

| Original (__init__.py) | Neuer Pfad (setup.validation) |
|------------------------|-------------------------------|
| `_async_validate_dogs_config` | `_async_validate_dogs_config` |
| `_validate_profile` | `_validate_profile` |
| `_extract_enabled_modules` | `_extract_enabled_modules` |
| N/A | `async_validate_entry_config` ✅ **NEW** Public API |

### manager_init.py (Moved Functions)

| Original (__init__.py) | Neuer Pfad (setup.manager_init) |
|------------------------|----------------------------------|
| `_async_initialize_coordinator` | `_async_initialize_coordinator` |
| `_async_create_core_managers` | `_async_create_core_managers` |
| `_async_create_optional_managers` | `_async_create_optional_managers` |
| `_async_initialize_all_managers` | `_async_initialize_all_managers` |
| `_async_initialize_manager_with_timeout` | `_async_initialize_manager_with_timeout` |
| `_attach_managers_to_coordinator` | `_attach_managers_to_coordinator` |
| `_create_runtime_data` | `_create_runtime_data` |
| N/A | `async_initialize_managers` ✅ **NEW** Public API |

### platform_setup.py (Moved Functions)

| Original (__init__.py) | Neuer Pfad (setup.platform_setup) |
|------------------------|-----------------------------------|
| `_async_forward_platforms` | `_async_forward_platforms` |
| `_async_setup_helpers` | `_async_setup_helpers` |
| `_async_setup_scripts` | `_async_setup_scripts` |
| N/A | `async_setup_platforms` ✅ **NEW** Public API |

---

## 🤖 AUTOMATISCHE FIXES

### Schritt 1: Generiere Fix-Script

```bash
python scripts/analyze_test_imports.py
```

Das Script erstellt automatisch: `scripts/fix_test_imports.py`

### Schritt 2: Review Fixes

```bash
cat scripts/fix_test_imports.py
```

Prüfe ob die Änderungen korrekt aussehen.

### Schritt 3: Apply Fixes

```bash
python scripts/fix_test_imports.py
```

**Output:**
```
🔧 Fixing test imports...
✅ Fixed test_config_flow.py:15
✅ Fixed test_manager_init.py:42
✅ Fixed test_cleanup.py:8
✅ Import fixes complete!
```

### Schritt 4: Verify

```bash
pytest tests/unit/ -v
```

---

## 📝 MANUELLE ANPASSUNGEN

Manche Tests benötigen manuelle Anpassungen:

### 1. Tests die interne Funktionen direkt testen

#### Beispiel:
```python
# tests/unit/test_init_internals.py (falls vorhanden)

# ❌ Alt - testet direkt aus __init__.py
from custom_components.pawcontrol import _validate_profile

def test_validate_profile():
    ...

# ✅ Neu - testet aus validation.py
from custom_components.pawcontrol.setup.validation import _validate_profile

def test_validate_profile():
    ...
```

### 2. Tests die async_setup_entry mocken

#### Beispiel:
```python
# ❌ Alt - mockt interne Funktionen
@patch("custom_components.pawcontrol._async_create_core_managers")
@patch("custom_components.pawcontrol._async_setup_platforms")
async def test_setup_entry(mock_platforms, mock_managers):
    ...

# ✅ Neu - mockt Setup-Modul-Funktionen
@patch("custom_components.pawcontrol.setup.manager_init.async_initialize_managers")
@patch("custom_components.pawcontrol.setup.platform_setup.async_setup_platforms")
async def test_setup_entry(mock_platforms, mock_managers):
    ...
```

### 3. Integration Tests

Integration Tests sollten **nicht geändert werden müssen**, da die öffentliche API unverändert ist:

```python
# ✅ Funktioniert weiterhin ohne Änderungen
from custom_components.pawcontrol import async_setup_entry

async def test_full_setup(hass, mock_entry):
    result = await async_setup_entry(hass, mock_entry)
    assert result is True
```

---

## ✅ NEUE TEST-DATEIEN

Ich habe bereits neue Tests für die Setup-Module erstellt:

```
tests/unit/test_setup_validation.py  ✅ NEU - Tests für validation.py
tests/unit/test_setup_cleanup.py     ✅ NEU - Tests für cleanup.py
```

**TODO:** Erstelle noch:
```
tests/unit/test_setup_manager_init.py   - Tests für manager_init.py
tests/unit/test_setup_platform_setup.py - Tests für platform_setup.py
```

---

## 🧪 TEST-AUSFÜHRUNG

### Lokaler Test-Run

```bash
# Alle Tests
pytest tests/ -v

# Nur unit tests
pytest tests/unit/ -v

# Nur setup-Module
pytest tests/unit/test_setup_*.py -v

# Mit Coverage
pytest tests/ --cov=custom_components.pawcontrol --cov-report=term-missing
```

### Erwartete Ergebnisse

**Nach Migration:**
```
tests/unit/test_setup_validation.py ............ [ 10%] ✅
tests/unit/test_setup_cleanup.py .............. [ 20%] ✅
tests/unit/test_config_flow.py ................ [ 40%] ✅
tests/unit/test_coordinator.py ................ [ 60%] ✅
...
================================ 150 passed in 5.23s ================================
```

**Mögliche Fehler:**
```
tests/unit/test_old_imports.py::test_something FAILED  [ 50%] ❌
ImportError: cannot import name '_async_cleanup_runtime_data' from 'custom_components.pawcontrol'
```

→ Behebe mit Import-Anpassung (siehe oben)

---

## 🔍 DEBUGGING TIPPS

### Problem 1: ImportError

**Fehler:**
```python
ImportError: cannot import name '_validate_profile' from 'custom_components.pawcontrol'
```

**Lösung:**
```python
# Ändere zu:
from custom_components.pawcontrol.setup.validation import _validate_profile
```

### Problem 2: AttributeError in Mocks

**Fehler:**
```python
AttributeError: module 'custom_components.pawcontrol' has no attribute '_async_cleanup_runtime_data'
```

**Lösung:**
```python
# Ändere Mock-Pfad:
@patch("custom_components.pawcontrol.setup.cleanup.async_cleanup_runtime_data")
```

### Problem 3: Test findet Funktion nicht

**Fehler:**
```python
AttributeError: module 'custom_components.pawcontrol.setup.validation' has no attribute 'async_validate_entry_config'
```

**Lösung:**
Stelle sicher, dass `setup/__init__.py` die Funktion exportiert:

```python
# setup/__init__.py
from .validation import async_validate_entry_config

__all__ = ["async_validate_entry_config", ...]
```

---

## 📊 CHECKLISTE

Vor dem Merge:

- [ ] **Alle Tests laufen:** `pytest tests/ -v`
- [ ] **Keine ImportErrors:** Alle Imports korrekt
- [ ] **Coverage >= 95%:** `pytest --cov`
- [ ] **Type Check OK:** `mypy --strict`
- [ ] **Linting OK:** `ruff check`
- [ ] **hassfest OK:** `python -m scripts.hassfest`

---

## 🎯 ZUSAMMENFASSUNG

### Was zu tun ist:

1. ✅ Führe `analyze_test_imports.py` aus
2. ✅ Wende automatische Fixes an
3. ✅ Passe manuelle Edge-Cases an
4. ✅ Erstelle Tests für neue Module
5. ✅ Führe vollständigen Test-Run durch

### Geschätzter Aufwand:

- **Automatische Fixes:** 15 Minuten
- **Manuelle Anpassungen:** 1-2 Stunden
- **Neue Tests:** 30 Minuten
- **Verification:** 30 Minuten
- **Total:** ~2-3 Stunden

### Success Rate:

- **Automatisch fixbar:** ~70%
- **Manuell nötig:** ~30%
- **Breaking Changes:** 0% (öffentliche API unverändert)

---

**Erstellt von:** Claude (Anthropic)
**Datum:** 2026-02-15
**Version:** 1.0
