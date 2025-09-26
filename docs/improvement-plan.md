# PawControl Verbesserungsplan - Platinum Compliance

## 🎯 Ziel: Vollständige Platinum-Level Compliance

## 📋 Sofort-Maßnahmen (Day 1)

### 1. Type System Improvements (2 Stunden)

#### A. Custom ConfigEntry Type definieren
**Datei: `custom_components/pawcontrol/types.py`**
```python
# Hinzufügen am Anfang:
from homeassistant.config_entries import ConfigEntry

@dataclass
class PawControlRuntimeData:
    """Runtime data for PawControl integration."""
    coordinator: PawControlCoordinator
    data_manager: PawControlDataManager
    notification_manager: PawControlNotificationManager
    feeding_manager: FeedingManager
    walk_manager: WalkManager
    entity_factory: EntityFactory
    entity_profile: str
    dogs: list[DogConfigData]

type PawControlConfigEntry = ConfigEntry[PawControlRuntimeData]
```

#### B. py.typed File erstellen
**Datei: `custom_components/pawcontrol/py.typed`**
```
# Leere Datei - zeigt PEP-561 Compliance an
```

### 2. Coordinator ConfigEntry Fix (30 Minuten)

**Datei: `custom_components/pawcontrol/coordinator.py`**
```python
class PawControlCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,  # Hinzufügen
    ) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=5),
            config_entry=config_entry,  # ✅ Übergeben
        )
```

### 3. Runtime Data Cleanup (45 Minuten)

**Datei: `custom_components/pawcontrol/__init__.py`**
```python
# Ändern von:
entry.runtime_data = runtime_data
hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime_data

# Zu:
entry.runtime_data = runtime_data  # NUR hier
# hass.data Zeile entfernen
```

## 🔧 Kritische Fixes (Day 2-3)

### 4. Exception Handling Refactoring (3 Stunden)

#### A. Spezifische Exceptions verwenden
```python
# Statt:
except Exception as err:

# Verwenden:
except (asyncio.TimeoutError, TimeoutException) as err:
    raise ConfigEntryNotReady(f"Timeout: {err}") from err
except AuthenticationError as err:
    raise ConfigEntryAuthFailed(f"Auth failed: {err}") from err
except ApiError as err:
    raise UpdateFailed(f"API error: {err}") from err
```

#### B. Try-Blöcke minimieren
```python
# ❌ Schlecht:
try:
    data = await client.get_data()
    processed = data.get("value", 0) * 100  # Nicht in try!
    self._attr_native_value = processed
except ClientError:
    _LOGGER.error("Failed")

# ✅ Gut:
try:
    data = await client.get_data()
except ClientError:
    _LOGGER.error("Failed")
    return

# Datenverarbeitung außerhalb
processed = data.get("value", 0) * 100
self._attr_native_value = processed
```

### 5. WebSession Injection (2 Stunden)

**Datei: `custom_components/pawcontrol/__init__.py`**
```python
from homeassistant.helpers.aiohttp_client import async_get_clientsession

async def async_setup_entry(hass: HomeAssistant, entry: PawControlConfigEntry) -> bool:
    """Set up with WebSession support."""
    session = async_get_clientsession(hass)

    # Wenn externe APIs verwendet werden:
    coordinator = PawControlCoordinator(hass, entry, session)
```

### 6. Reauthentication Flow (2 Stunden)

**Datei: `custom_components/pawcontrol/config_flow.py`**
```python
async def async_step_reauth(
    self, entry_data: Mapping[str, Any]
) -> ConfigFlowResult:
    """Handle reauthentication."""
    self.reauth_entry = self.hass.config_entries.async_get_entry(
        self.context["entry_id"]
    )
    return await self.async_step_reauth_confirm()

async def async_step_reauth_confirm(
    self, user_input: dict[str, Any] | None = None
) -> ConfigFlowResult:
    """Confirm reauthentication."""
    if user_input is None:
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
        )

    # Validate credentials
    await self.async_set_unique_id(self.reauth_entry.unique_id)
    self._abort_if_unique_id_mismatch(reason="wrong_account")

    return self.async_update_reload_and_abort(
        self.reauth_entry,
        data_updates=user_input,
    )
```

## 🧪 Test Coverage Improvements (Day 4-5)

### 7. Unit Test Expansion (1 Tag)

#### A. Config Flow Complete Coverage
```python
# test_config_flow.py erweitern:
- Test all error paths
- Test duplicate prevention
- Test discovery flows
- Test reauth flow
- Test reconfigure flow
```

#### B. Coordinator Tests
```python
# test_coordinator.py neu:
- Test update intervals
- Test error recovery
- Test data caching
- Test parallel updates
```

### 8. Integration Tests (1 Tag)

```python
# test_init.py erweitern:
- Test setup/unload
- Test platform forwarding
- Test service registration
- Test entity creation
```

## 📝 Documentation (Day 6)

### 9. Docstring Completion (4 Stunden)

```python
# Für ALLE Funktionen/Methoden:
async def async_setup_entry(
    hass: HomeAssistant,
    entry: PawControlConfigEntry
) -> bool:
    """Set up PawControl from a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry to set up

    Returns:
        True if setup successful

    Raises:
        ConfigEntryNotReady: If setup prerequisites not met
        ConfigEntryAuthFailed: If authentication fails
    """
```

### 10. Inline Comments (2 Stunden)

```python
# Erklären Sie das "Warum", nicht das "Was"
# ✅ Gut: Check auth before setup to avoid partial initialization
# ❌ Schlecht: Check if authenticated
```

## 🚀 Performance Optimizations (Optional - Day 7)

### 11. Advanced Caching
```python
class PawControlCoordinator:
    def __init__(self):
        self._cache_timeout = timedelta(seconds=30)
        self._last_fetch = None
        self._cached_data = None
```

### 12. Resource Optimization
```python
# __slots__ für Memory-Effizienz
class PawControlEntity:
    __slots__ = ("_attr_unique_id", "_attr_name", "_dog_id")
```

## 📊 Metriken & Monitoring

### Erfolgskriterien:
- [ ] Test Coverage > 95%
- [ ] Alle Platinum-Requirements erfüllt
- [ ] Keine deprecation warnings
- [ ] MyPy keine Fehler
- [ ] Ruff/PyLint clean
- [ ] hassfest passed

### Monitoring Tools:
```bash
# Coverage prüfen
pytest tests/components/pawcontrol \
    --cov=homeassistant.components.pawcontrol \
    --cov-report=term-missing

# Type checking
mypy homeassistant/components/pawcontrol

# Linting
ruff check custom_components/pawcontrol
pylint custom_components/pawcontrol

# Validation (CI)
# hassfest runs automatically via home-assistant/actions/hassfest@master
# Optional local run (requires hassfest installed):
#   python -m hassfest --integration-path custom_components/pawcontrol
```

## 🎁 Quick Wins Checkliste

- [ ] **5 Min:** py.typed File erstellen
- [ ] **10 Min:** ConfigEntry an Coordinator übergeben
- [ ] **15 Min:** Lazy Logging überall implementieren
- [ ] **20 Min:** Runtime data cleanup
- [ ] **30 Min:** Basic docstrings hinzufügen
- [ ] **45 Min:** Exceptions spezifizieren

## 📅 Zeitplan

| Woche 1 | Mo | Di | Mi | Do | Fr |
|---------|----|----|----|----|-----|
| **Fokus** | Type System | Exceptions | WebSession | Tests | Tests |
| **Stunden** | 4h | 5h | 4h | 8h | 8h |

| Woche 2 | Mo | Di | Mi | Do | Fr |
|---------|----|----|----|----|-----|
| **Fokus** | Docs | Performance | Review | Deploy | - |
| **Stunden** | 6h | 4h | 3h | 2h | - |

## 🏆 Erwartetes Ergebnis

Nach Implementierung dieses Plans:
- ✅ **100% Platinum Compliance**
- ✅ **>95% Test Coverage**
- ✅ **Vollständige Type Safety**
- ✅ **Production-Ready Code**
- ✅ **Home Assistant Core Contribution Ready**

## 💡 Pro-Tips

1. **Incremental Changes:** Jeden Fix einzeln testen
2. **Snapshot Tests:** Für Entity States verwenden
3. **Mock richtig:** Nie hass.data direkt testen
4. **Review früh:** Code Reviews nach jedem Major Change
5. **Dokumentation:** Änderungen in CHANGELOG.md

## 🚨 Risiken & Mitigationen

| Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|--------|-------------------|---------|------------|
| Breaking Changes | Mittel | Hoch | Feature Flags, Staged Rollout |
| Test Flakiness | Niedrig | Mittel | Proper Mocking, Async Handling |
| Performance Degradation | Niedrig | Hoch | Profiling, Load Tests |

## ✅ Definition of Done

Eine Aufgabe gilt als abgeschlossen wenn:
1. Code implementiert und getestet
2. Tests grün (>95% coverage)
3. Dokumentation aktualisiert
4. MyPy/Ruff/PyLint clean
5. Code Review passed
6. CHANGELOG.md updated

---

**Start:** Sofort mit Quick Wins beginnen!
**Ziel:** Platinum Compliance in 2 Wochen
**Support:** GitHub Issues für Fragen nutzen
